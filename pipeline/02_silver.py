#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_silver.py
============
Assignment 3, Part 1b - Silver layer: clean, type-cast, quarantine, link, and mask PII.
作业 3 第 1b 部分 - Silver 层:清洗、类型转换、隔离坏数据、关联、PII 脱敏。

Inputs / 输入
    data/staging/api_records.csv, api_chart_ranks.csv   (from 01_ingest_api.py / 来自 01_ingest_api.py)
    data/podcast_sessions_flat.csv                      (A2 raw flat table = A2 Bronze / A2 原始宽表)
    pipeline/seed/genre_to_a2_top_category.csv          (hand-made mapping table / 手工对照表)

Outputs / 输出 (data/silver/)
    silver_api_podcast, silver_api_chart_rank, quarantine_api_podcast
    silver_<11 A2 tables> (PII masked), quarantine_a2_session_duplicates
    silver_run_report.json

Decisions taken by the user / 用户已做的决定
    1. Category link  : Apple genre -> one of the 8 A2 TOP-LEVEL categories (seed table; 'Unmapped' if none).
       类目关联:Apple 类目 -> A2 的 8 个一级类目之一(对照表;对不上标 Unmapped)。
    2. Failed rows    : quarantine rows WITHOUT feedUrl (or unparsable date, etc.); rows whose latest episode is
                        scheduled in the FUTURE are KEPT and flagged is_scheduled_future.
       未通过检查的行:隔离没有 feedUrl 的行(以及日期无法解析等);"最新一集预约在未来"的行保留并加标记。
    3. PII masking    : e-mail -> <hash>@<domain>, names -> hash, city column dropped (country kept).
       脱敏:邮箱 -> <哈希>@<域名>,姓名 -> 哈希,城市列直接丢弃(保留国家)。

PII technique / 脱敏技术
    HMAC-SHA256 (a salted SHA-256: the secret salt is the HMAC key), first 16 hex characters kept.
    HMAC-SHA256(加盐的 SHA-256:密钥盐作为 HMAC 的 key),保留前 16 位十六进制。
    * irreversible; the same input always gives the same token, so JOIN / DISTINCT still work
      不可逆;同一输入永远得到同一令牌,所以 JOIN / 去重仍然可用
    * the salt is read from the environment variable PII_SALT only - never stored in a file
      盐只从环境变量 PII_SALT 读取,不写进任何文件
    Not masked: the API's artistName (a public publisher/brand name, not personal data of our users).
    不脱敏:API 里的 artistName(公开的出品方/品牌名,不是我们用户的个人数据)。

Usage / 用法 (PowerShell):
    $env:PII_SALT = "<your-own-secret-string>"
    python pipeline/02_silver.py
"""

import hashlib
import hmac
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from build_normalization import TABLES, build   # reuse the A2 normalization / 复用 A2 规范化逻辑

STAGING = os.path.join(ROOT, "data", "staging")
SILVER = os.path.join(ROOT, "data", "silver")
FLAT = os.path.join(ROOT, "data", "podcast_sessions_flat.csv")
SEED = os.path.join(HERE, "seed", "genre_to_a2_top_category.csv")
TOKEN_LEN = 16   # hex characters kept / 保留的十六进制位数


# ----------------------------------------------------------------------------
# PII masking helpers / 脱敏函数
# ----------------------------------------------------------------------------
def get_salt():
    """Read the secret salt from the environment; stop if missing. / 从环境变量读盐,缺失就停止。"""
    salt = os.environ.get("PII_SALT")
    if not salt:
        sys.exit("Environment variable PII_SALT is not set.\n"
                 "未设置环境变量 PII_SALT。 PowerShell:  $env:PII_SALT = \"<your-own-secret-string>\"")
    return salt.encode("utf-8")


def token(value, salt):
    """HMAC-SHA256 token of a normalized string (None stays None). / 规范化字符串的 HMAC-SHA256 令牌。"""
    if pd.isna(value) or str(value).strip() == "":
        return None
    msg = str(value).strip().lower().encode("utf-8")
    return hmac.new(salt, msg, hashlib.sha256).hexdigest()[:TOKEN_LEN]


def mask_email(email, salt):
    """'jane.doe1@gmail.com' -> '<token>@gmail.com' (domain kept for analysis).
    邮箱 -> '<令牌>@域名'(保留域名,便于分析)。"""
    if pd.isna(email) or "@" not in str(email):
        return None
    domain = str(email).rsplit("@", 1)[1].strip().lower()
    return f"{token(email, salt)}@{domain}"


def listener_key(listener_id, salt):
    """Hashed surrogate key replacing the integer listener_id (user decision: option 3).
    用哈希替代键取代整数 listener_id(用户决定:选项 3)。"""
    return token(f"listener:{int(listener_id)}", salt)


def mask_tables(t, salt):
    """Return masked copies of the A2 tables that hold personal data. / 返回含个人数据的 A2 表的脱敏副本。"""
    out = dict(t)
    # listener_id -> listener_key in every table that has it / 所有含 listener_id 的表都换成 listener_key
    for name in ("listener", "subscription", "listening_session"):
        d = t[name].copy()
        d.insert(0, "listener_key", d["listener_id"].map(lambda v: listener_key(v, salt)))
        t = {**t, name: d.drop(columns=["listener_id"])}
    out.update({n: t[n] for n in ("listener", "subscription", "listening_session")})
    li = t["listener"].copy()
    li["listener_name_hash"] = li["listener_name"].map(lambda v: token(v, salt))
    li["listener_email_masked"] = li["listener_email"].map(lambda v: mask_email(v, salt))
    out["listener"] = li[["listener_key", "listener_name_hash", "listener_email_masked", "country_code"]]  # city dropped

    cr = t["creator"].copy()
    cr["creator_name_hash"] = cr["creator_name"].map(lambda v: token(v, salt))
    cr["creator_email_masked"] = cr["creator_email"].map(lambda v: mask_email(v, salt))
    out["creator"] = cr[["creator_id", "creator_name_hash", "creator_email_masked", "plan_tier"]]

    g = t["guest"].copy()
    g["guest_name_hash"] = g["guest_name"].map(lambda v: token(v, salt))
    out["guest"] = g[["guest_id", "guest_name_hash"]]
    return out


def mask_flat_rows(df, salt):
    """Mask PII in rows of the raw flat table (used for the quarantine file: Silver must hold no raw PII).
    对原始宽表的行做脱敏(用于隔离文件:Silver 里不能有原始个人信息)。"""
    out = df.copy()
    out["listener_id"] = out["listener_id"].map(lambda v: listener_key(v, salt))
    out["listener_name"] = out["listener_name"].map(lambda v: token(tidy(v), salt))
    out["creator_name"] = out["creator_name"].map(lambda v: token(tidy(v), salt))
    out["listener_email"] = out["listener_email"].map(lambda v: mask_email(v, salt))
    out["creator_email"] = out["creator_email"].map(lambda v: mask_email(v, salt))
    out = out.drop(columns=["listener_city", "episode_guests"])          # city and guest names dropped / 丢弃城市和嘉宾名
    return out.rename(columns={"listener_id": "listener_key", "listener_name": "listener_name_hash", "creator_name": "creator_name_hash",
                               "listener_email": "listener_email_masked", "creator_email": "creator_email_masked"})


def tidy(v):
    """Light normalization before hashing (spacing only). / 哈希前的轻度规范化(只处理空格)。"""
    return None if pd.isna(v) else " ".join(str(v).split())


def pii_leak_check(raw, masked):
    """Confirm no raw name / e-mail / city value survives in the masked tables. Returns (passed, details).
    确认脱敏后的表里没有残留原始姓名/邮箱/城市。返回 (是否通过, 明细)。"""
    details = {}
    for tbl, col, outcol in (("listener", "listener_name", None), ("listener", "listener_email", None),
                             ("creator", "creator_name", None), ("creator", "creator_email", None),
                             ("guest", "guest_name", None)):
        raw_vals = set(raw[tbl][col].dropna().astype(str))
        found = 0
        for c in masked[tbl].columns:
            found += masked[tbl][c].astype(str).isin(raw_vals).sum()
        details[f"{tbl}.{col}"] = int(found)
    if "listener_city" in masked["listener"].columns:
        details["listener.listener_city_column_present"] = 1
    return all(v == 0 for v in details.values()), details


# ----------------------------------------------------------------------------
# API side / API 一侧
# ----------------------------------------------------------------------------
def silver_api():
    """Type-cast, quarantine, link to A2 categories. / 类型转换、隔离、关联 A2 类目。"""
    df = pd.read_csv(os.path.join(STAGING, "api_records.csv"), dtype={"collectionId": str})
    ranks = pd.read_csv(os.path.join(STAGING, "api_chart_ranks.csv"), dtype={"podcast_id": str})
    seed = pd.read_csv(SEED)
    rep = {"api_rows_in": len(df)}

    now = pd.Timestamp.now(tz="UTC")
    release = pd.to_datetime(df["releaseDate"], errors="coerce", utc=True)
    df["is_scheduled_future"] = release.notna() & (release > now)

    # Quarantine rule (user decision #2): any failed check EXCEPT 'future date', plus unparsable dates.
    # 隔离规则(用户决定 #2):除"未来日期"外任一检查失败,另加日期无法解析。
    hard = ["chk_id_not_null", "chk_id_unique", "chk_trackcount_range", "chk_genre_not_null", "chk_feed_url_format"]
    reasons = pd.Series("", index=df.index)
    for c in hard:
        reasons = reasons.where(df[c], reasons + c + ";")
    reasons = reasons.where(release.notna(), reasons + "release_date_unparsable;")
    bad = reasons != ""
    quarantine = df[bad].assign(rejection_reason=reasons[bad].str.rstrip(";"))
    good = df[~bad].copy()
    rep.update(api_quarantined=int(bad.sum()), api_silver_rows=len(good),
               api_kept_but_scheduled_future=int(good["is_scheduled_future"].sum()))

    # Type-cast and rename / 类型转换并重命名
    s = pd.DataFrame({
        "podcast_id": good["collectionId"].astype("int64"),
        "podcast_name": good["collectionName"].str.strip(),
        "artist_name": good["artistName"].str.strip(),
        "primary_genre": good["primaryGenreName"].str.strip(),
        "all_genres": good["genres"],
        "track_count": good["trackCount"].astype("int64"),
        "latest_release_at": pd.to_datetime(good["releaseDate"], utc=True).dt.tz_localize(None),
        "is_scheduled_future": good["is_scheduled_future"],
        "feed_url": good["feedUrl"],
        "store_country": good.get("country"),
        "content_rating": good.get("contentAdvisoryRating"),
        "explicitness": good.get("collectionExplicitness"),
        "ingested_at": good["ingested_at"],
        "source_name": good["source_name"],
    })
    # Link to Assignment 2 (user decision #1) / 关联 A2(用户决定 #1)
    m = dict(zip(seed["apple_genre"], seed["a2_top_category"]))
    s["a2_top_category"] = s["primary_genre"].map(m).fillna("Unmapped")
    rep["api_genres_missing_from_seed"] = int((~s["primary_genre"].isin(m)).sum())
    rep["api_mapped_to_a2_top_category"] = int((s["a2_top_category"] != "Unmapped").sum())

    # Chart ranks, only for podcasts that survived / 榜单名次,只保留未被隔离的节目
    r = ranks.assign(podcast_id=ranks["podcast_id"].astype("int64"))
    r = r[r["podcast_id"].isin(s["podcast_id"])].reset_index(drop=True)
    return s, r, quarantine, rep


# ----------------------------------------------------------------------------
# Main / 入口
# ----------------------------------------------------------------------------
def main():
    salt = get_salt()
    os.makedirs(SILVER, exist_ok=True)
    report = {}

    # ---- API -> Silver ----
    api, ranks, api_q, rep = silver_api()
    report.update(rep)
    api.to_csv(os.path.join(SILVER, "silver_api_podcast.csv"), index=False, encoding="utf-8")
    ranks.to_csv(os.path.join(SILVER, "silver_api_chart_rank.csv"), index=False, encoding="utf-8")
    api_q.to_csv(os.path.join(SILVER, "quarantine_api_podcast.csv"), index=False, encoding="utf-8")

    # ---- A2 raw flat -> normalized -> masked -> Silver ----
    raw_flat = pd.read_csv(FLAT, dtype=str)
    dups = mask_flat_rows(raw_flat[raw_flat.duplicated(keep="first")], salt)   # rejected rows, masked too / 被拒绝的行也要脱敏
    dups.to_csv(os.path.join(SILVER, "quarantine_a2_session_duplicates.csv"), index=False, encoding="utf-8")
    tables, stats = build(FLAT)
    masked = mask_tables(tables, salt)
    for name in TABLES:
        masked[name].to_csv(os.path.join(SILVER, f"silver_{name}.csv"), index=False, encoding="utf-8")
    report.update(a2_raw_rows=stats["raw_rows"], a2_duplicate_rows_quarantined=len(dups),
                  a2_silver_session_rows=len(masked["listening_session"]))

    # ---- Checks on the Silver output / 对 Silver 输出的检查 ----
    ok_pii, leak = pii_leak_check(tables, masked)
    tok_unique = {
        "listener_name_hash": bool(masked["listener"]["listener_name_hash"].dropna().is_unique) or "shared by namesakes",
        "listener_email_masked": bool(masked["listener"]["listener_email_masked"].dropna().is_unique) or "shared e-mail (A2 assumption 9)",
    }
    fk_ok = (masked["listening_session"]["listener_key"].isin(masked["listener"]["listener_key"]).all()
             and masked["subscription"]["listener_key"].isin(masked["listener"]["listener_key"]).all()
             and masked["listening_session"]["episode_id"].isin(masked["episode"]["episode_id"]).all())
    # hashed key must be unique and must not contain the integer id column / 哈希键必须唯一,且不能保留整数 id 列
    key_unique = bool(masked["listener"]["listener_key"].is_unique)
    no_raw_id = all("listener_id" not in masked[n].columns for n in ("listener", "subscription", "listening_session"))
    report.update(listener_key_unique=key_unique, listener_id_column_removed=no_raw_id,
                  listener_count=len(masked["listener"]))
    report.update(pii_leak_check_passed=bool(ok_pii), pii_leak_counts=leak,
                  token_uniqueness_note=tok_unique, session_foreign_keys_ok=bool(fk_ok))
    with open(os.path.join(SILVER, "silver_run_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    # ---- Short console summary / 简短的控制台摘要 ----
    print("Silver layer built / Silver 层已生成\n")
    print(f"{'API podcasts in':<38}{report['api_rows_in']:>8,}")
    print(f"{'  quarantined (no feedUrl etc.)':<38}{report['api_quarantined']:>8,}")
    print(f"{'  Silver rows':<38}{report['api_silver_rows']:>8,}")
    print(f"{'    kept, scheduled in the future':<38}{report['api_kept_but_scheduled_future']:>8,}")
    print(f"{'    mapped to an A2 top-level category':<38}{report['api_mapped_to_a2_top_category']:>8,}")
    print(f"{'A2 raw rows':<38}{report['a2_raw_rows']:>8,}")
    print(f"{'  duplicate rows quarantined':<38}{report['a2_duplicate_rows_quarantined']:>8,}")
    print(f"{'  Silver session rows':<38}{report['a2_silver_session_rows']:>8,}")
    print(f"{'PII leak check (raw values left)':<38}{'PASS' if ok_pii else 'FAIL':>8}")
    print(f"{'session foreign keys':<38}{'PASS' if fk_ok else 'FAIL':>8}")
    print(f"{'listener_key unique (' + format(report['listener_count'], ',') + ')':<38}{'PASS' if key_unique else 'FAIL':>8}")
    print(f"{'integer listener_id removed':<38}{'PASS' if no_raw_id else 'FAIL':>8}")
    print(f"\nFiles: {os.path.relpath(SILVER, ROOT)}{os.sep}")


if __name__ == "__main__":
    main()
