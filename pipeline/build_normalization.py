#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_normalization.py
======================
Assignment 3 (re-created; the Assignment 2 original was lost) - flat table -> 11 normalized tables.
作业 3(重新编写;作业 2 的原文件已丢失)- 宽表 -> 11 张规范化表。

Rules follow the Assignment 2 report (Part 2) / 规则来自作业 2 报告第 2 部分:
  1NF : drop exact duplicate rows, standardize spelling/casing/coding, split guests into rows.
        去掉完全重复行,统一拼写/大小写/编码,把嘉宾拆成多行。
  2NF/3NF : one table per entity; latest non-null e-mail (by session time) is the current one.
        每个实体一张表;邮箱取按会话时间最新的非空值。

Usage / 用法:
    python build_normalization.py                       # build + compare with the A2 CSVs
    python build_normalization.py --out data/normalized_rebuilt
    python build_normalization.py --no-check            # skip the comparison

No credentials are used. / 不使用任何密钥。
"""

import argparse
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # repo root / 仓库根目录
DEFAULT_FLAT = os.path.join(ROOT, "data", "podcast_sessions_flat.csv")
DEFAULT_OUT = os.path.join(ROOT, "data", "normalized_rebuilt")
# Optional: the A2 CSVs, only used for the comparison; set A2_CSV_DIR or pass --ref.
# 可选:作业 2 的 CSV,仅用于对照;可设置环境变量 A2_CSV_DIR 或传 --ref。
A2_CSV_DIR = os.environ.get("A2_CSV_DIR", os.path.join(os.path.dirname(ROOT), "作业2终稿", "Data", "normalized"))

TABLES = ["country", "plan", "category", "creator", "podcast_show", "episode", "guest",
          "episode_guest", "listener", "subscription", "listening_session"]
DEVICES = {"mobile": "Mobile", "desktop": "Desktop", "tablet": "Tablet", "smartspeaker": "Smart Speaker"}


# ----------------------------------------------------------------------------
# Helpers / 辅助函数
# ----------------------------------------------------------------------------
def tidy_person(name):
    """Trim, collapse spaces, turn 'Last, First' into 'First Last'.
    去首尾空格、合并多余空格,把 '姓, 名' 改成 '名 姓'。"""
    if pd.isna(name):
        return name
    s = re.sub(r"\s+", " ", str(name)).strip()
    if ", " in s:
        last, first = s.split(", ", 1)
        s = f"{first} {last}"
    return s


def canonical_by_key(keys, values):
    """For each key pick the most common value that is NOT all-lower / all-UPPER
    (those are the injected casing errors); fall back to Title Case.
    每个 key 取"最常见且不是全小写/全大写"的写法(全小写/全大写是注入的错误);否则退回 Title Case。"""
    df = pd.DataFrame({"k": keys.to_numpy(), "v": values.to_numpy()})
    good = df[(df.v != df.v.str.lower()) & (df.v != df.v.str.upper())]
    # tie-safe mode: highest count, then alphabetical / 并列时按字母序取第一个
    mode = good.groupby("k")["v"].agg(lambda s: s.value_counts().sort_index().idxmax())
    fallback = df.groupby("k")["v"].agg(lambda s: s.iloc[0].title())
    return keys.map(mode).fillna(keys.map(fallback))


def latest_non_null(df, key, col):
    """Value of `col` on the most recent row (by session time) where it is not null.
    按会话时间,取最近一条非空的值。"""
    d = df.dropna(subset=[col]).sort_values("session_started_at", kind="mergesort")
    return d.groupby(key)[col].last()


def first_non_null(df, key, col):
    """First non-null value per key. / 每个 key 的第一个非空值。"""
    return df.dropna(subset=[col]).groupby(key)[col].first()


# ----------------------------------------------------------------------------
# Main build / 主流程
# ----------------------------------------------------------------------------
def build(flat_path):
    raw = pd.read_csv(flat_path, dtype=str, keep_default_na=True)
    stats = {"raw_rows": len(raw)}

    # ---- 1NF: exact duplicates / 完全重复行 ----
    df = raw.drop_duplicates(keep="first").reset_index(drop=True)
    stats["after_dedup"] = len(df)

    for c in ("listened_seconds", "listener_id", "episode_id", "episode_duration_sec",
              "show_id", "creator_id", "creator_plan_price_usd"):
        df[c] = df[c].astype(int)

    # ---- 1NF: standardize values / 统一取值 ----
    df["listener_name"] = canonical_by_key(df["listener_id"], df["listener_name"].map(tidy_person))
    df["creator_name"] = canonical_by_key(df["creator_id"], df["creator_name"].map(tidy_person))
    df["category_name"] = canonical_by_key(df["category_name"].str.casefold(), df["category_name"])
    cn = df["listener_country_code"]
    df["listener_country_name"] = cn.map(df.groupby("listener_country_code")["listener_country_name"]
                                         .agg(lambda s: s.value_counts().sort_index().idxmax()))
    df["device_type"] = df["device_type"].str.casefold().str.replace(r"[\s_]", "", regex=True).map(DEVICES)
    df["completed"] = df["completed"].str.casefold().map(
        {"y": "Y", "yes": "Y", "1": "Y", "n": "N", "no": "N", "0": "N"})
    assert df["device_type"].notna().all() and df["completed"].notna().all()

    # the natural key must now be unique / 自然键此时应当唯一
    key = ["listener_id", "episode_id", "session_started_at"]
    assert not df.duplicated(key).any(), "natural key not unique"

    out = {}
    # ---- small lookup tables / 小型查找表 ----
    out["country"] = (df[["listener_country_code", "listener_country_name"]].drop_duplicates()
                      .rename(columns={"listener_country_code": "country_code", "listener_country_name": "country_name"})
                      .sort_values("country_code").reset_index(drop=True))
    out["plan"] = (df[["creator_plan_tier", "creator_plan_price_usd"]].drop_duplicates()
                   .rename(columns={"creator_plan_tier": "plan_tier", "creator_plan_price_usd": "monthly_price_usd"})
                   .sort_values("monthly_price_usd").reset_index(drop=True))

    # ---- category (self-reference): top-level A-Z first, then children A-Z ----
    # 类目(自引用):先一级类目按字母序,再二级类目按字母序
    child = df.dropna(subset=["parent_category_name"])[["category_name", "parent_category_name"]].drop_duplicates()
    tops = sorted(set(child["parent_category_name"]) | set(
        df.loc[df["parent_category_name"].isna(), "category_name"]))
    kids = sorted(set(child["category_name"]) - set(tops))
    names = tops + kids
    cat_id = {n: i + 1 for i, n in enumerate(names)}
    parent_of = dict(zip(child["category_name"], child["parent_category_name"]))
    out["category"] = pd.DataFrame({
        "category_id": [cat_id[n] for n in names], "category_name": names,
        "parent_category_id": [cat_id[parent_of[n]] if n in parent_of and n not in tops else pd.NA for n in names]})

    # ---- creator (latest non-null e-mail wins) / 创作者(邮箱取最新非空) ----
    cr = df.groupby("creator_id").agg(creator_name=("creator_name", "first"),
                                      plan_tier=("creator_plan_tier", "first")).reset_index()
    cr["creator_email"] = cr["creator_id"].map(latest_non_null(df, "creator_id", "creator_email"))
    out["creator"] = cr[["creator_id", "creator_name", "creator_email", "plan_tier"]]

    # ---- show / episode / guest ----
    sh = df.groupby("show_id").agg(show_title=("show_title", "first"), creator_id=("creator_id", "first"),
                                   category_name=("category_name", "first")).reset_index()
    sh["category_id"] = sh["category_name"].map(cat_id)
    out["podcast_show"] = sh[["show_id", "show_title", "creator_id", "category_id"]]

    ep = df.groupby("episode_id").agg(show_id=("show_id", "first"), episode_title=("episode_title", "first"),
                                      episode_duration_sec=("episode_duration_sec", "first"),
                                      episode_publish_date=("episode_publish_date", "first")).reset_index()
    out["episode"] = ep

    # guests: split the multi-valued cell on ';' or ',' (1NF) / 嘉宾:按 ';' 或 ',' 拆开
    g = ep[["episode_id"]].merge(df[["episode_id", "episode_guests"]].dropna().drop_duplicates("episode_id"),
                                 on="episode_id")
    g["guest_name"] = g["episode_guests"].str.split(r"\s*[;,]\s*", regex=True)
    g = g.explode("guest_name")
    g["guest_name"] = g["guest_name"].str.strip()
    g = g[g["guest_name"] != ""].drop_duplicates(["episode_id", "guest_name"])
    guest_names = sorted(g["guest_name"].unique())
    gid = {n: i + 1 for i, n in enumerate(guest_names)}
    out["guest"] = pd.DataFrame({"guest_id": list(gid.values()), "guest_name": guest_names})
    out["episode_guest"] = (pd.DataFrame({"episode_id": g["episode_id"], "guest_id": g["guest_name"].map(gid)})
                            .sort_values(["episode_id", "guest_id"]).reset_index(drop=True))

    # ---- listener (latest non-null e-mail; city = first non-null) ----
    li = df.groupby("listener_id").agg(listener_name=("listener_name", "first"),
                                       country_code=("listener_country_code", "first")).reset_index()
    li["listener_email"] = li["listener_id"].map(latest_non_null(df, "listener_id", "listener_email"))
    li["listener_city"] = li["listener_id"].map(first_non_null(df, "listener_id", "listener_city"))
    out["listener"] = li[["listener_id", "listener_name", "listener_email", "listener_city", "country_code"]]

    # ---- subscription: a row exists iff the listener is subscribed / 订阅:当且仅当订阅了才有这一行 ----
    sub = (df[df["is_subscribed"] == "Y"][["listener_id", "show_id", "subscribed_on"]].drop_duplicates()
           .sort_values(["listener_id", "show_id"]).reset_index(drop=True))
    out["subscription"] = sub

    # ---- listening_session: surrogate key in time order / 会话表:按时间顺序生成代理键 ----
    # ties on the same second are broken by listener_id, episode_id (matches the A2 load order)
    # 同一秒的并列,按 listener_id、episode_id 排(与作业 2 的加载顺序一致)
    ls = df.sort_values(["session_started_at", "listener_id", "episode_id"]).reset_index(drop=True)
    ls.insert(0, "session_id", range(1, len(ls) + 1))
    out["listening_session"] = ls[["session_id", "listener_id", "episode_id", "session_started_at",
                                   "listened_seconds", "completed", "device_type"]]
    return out, stats


def compare(tables, ref_dir):
    """Compare each rebuilt table with the Assignment 2 CSV (as text, order-insensitive).
    把每张重建的表与作业 2 的 CSV 比较(按文本、不看行顺序)。"""
    rows = []
    for t in TABLES:
        ref = pd.read_csv(os.path.join(ref_dir, f"{t}.csv"), dtype=str).fillna("")
        new = tables[t].astype(str).replace({"<NA>": "", "nan": "", "None": ""}).fillna("")
        new.columns = list(ref.columns)
        # whole floats like '7.0' -> '7' / 形如 '7.0' 的整数浮点转成 '7'
        new = new.apply(lambda s: s.str.replace(r"\.0$", "", regex=True))
        a = ref.sort_values(list(ref.columns)).reset_index(drop=True)
        b = new.sort_values(list(ref.columns)).reset_index(drop=True)
        same_shape = a.shape == b.shape
        diff = int((a.ne(b)).any(axis=1).sum()) if same_shape else -1
        rows.append((t, len(ref), len(new), "OK" if same_shape and diff == 0 else
                     (f"{diff} rows differ" if same_shape else "shape differs")))
    return rows


def main():
    ap = argparse.ArgumentParser(description="Flat table -> 11 normalized tables.")
    ap.add_argument("--flat", default=DEFAULT_FLAT, help="flat CSV / 宽表 CSV")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output folder / 输出文件夹")
    ap.add_argument("--ref", default=A2_CSV_DIR, help="A2 CSV folder to compare with / 用来对照的作业 2 CSV 文件夹")
    ap.add_argument("--no-check", action="store_true", help="skip the comparison / 跳过对照")
    args = ap.parse_args()

    tables, stats = build(args.flat)
    os.makedirs(args.out, exist_ok=True)
    for t in TABLES:
        tables[t].to_csv(os.path.join(args.out, f"{t}.csv"), index=False, encoding="utf-8")
    print(f"raw rows {stats['raw_rows']:,} -> after dedup {stats['after_dedup']:,}; "
          f"{len(TABLES)} tables, {sum(len(v) for v in tables.values()):,} rows -> {args.out}")

    if not args.no_check and not os.path.isdir(args.ref):
        print(f"\nA2 CSV folder not found, comparison skipped: {args.ref}\n"
              "未找到作业 2 的 CSV 文件夹,已跳过对照。")
    elif not args.no_check:
        print(f"\n{'table':<18}{'A2 rows':>9}{'rebuilt':>9}  result")
        for t, a, b, r in compare(tables, args.ref):
            print(f"{t:<18}{a:>9,}{b:>9,}  {r}")


if __name__ == "__main__":
    main()
