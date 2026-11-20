#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04_star_schema.py
=================
Assignment 3, Part 2 - build the star schema (CSV files) from Silver, ready to load into Snowflake.
作业 3 第 2 部分 - 从 Silver 生成星型模型(CSV),之后加载到 Snowflake。

Facts / 事实表
  fact_listening_session  grain: ONE listening session (one listener, one episode)   粒度:一次收听会话
  fact_subscription       grain: ONE subscription (one listener subscribes one show) 粒度:一条订阅
Dimensions / 维度表
  dim_date, dim_listener, dim_episode, dim_show, dim_creator (SCD Type 2 on plan_tier)

SCD2 on dim_creator / dim_creator 的 SCD2
  A2 only stores the CURRENT plan_tier, so the plan history below is SIMULATED (assumption, seed fixed).
  A2 只有"当前套餐",所以下面的套餐历史是**模拟**的(假设,固定随机种子)。
  Rules (all assumptions, tune with the constants below) / 规则(均为假设,可改下面的常量):
    * about 30% of creators change plan 1-2 times / 约 30% 的创作者变更 1-2 次
    * first change >= 30 days after the data start; >= 30 days between changes (one billing cycle)
      第一次变更不早于数据起点后 30 天;两次变更间隔 >= 30 天(约一个计费周期)
    * upgrades are more common than downgrades (80/20); no two downgrades in a row
      升级多于降级(80/20);不连续降级
    * the LAST plan always equals the plan in A2 / 最后一个套餐必须等于 A2 里的当前套餐
  The data start is used as the "onboarding date" of every creator (A2 has no onboarding date).
  A2 没有创作者开通日期,用数据起点代替。

Fact rows pick the creator version valid ON the event date (session date / subscription date).
事实表中的 creator_sk 取事件发生当天有效的那个创作者版本。

Usage / 用法:  python pipeline/04_star_schema.py      (needs data/silver / 需要先跑 02_silver.py)
No credentials needed. / 不需要凭据。
"""

import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SILVER = os.path.join(ROOT, "data", "silver")
OUT = os.path.join(ROOT, "data", "star")

SEED = 42                      # fixed seed -> same history every run / 固定种子,每次结果一致
P_CHANGE = 0.30                # share of creators that ever change plan / 发生变更的创作者比例
P_TWO_CHANGES = 0.30           # among changers, share with 2 changes / 变更者中变更 2 次的比例
P_UPGRADE = 0.80               # chance a change is an upgrade / 一次变更是升级的概率
MIN_FIRST_DAYS = 30            # first change at least this many days after data start / 第一次变更距数据起点至少天数
MIN_GAP_DAYS = 30              # min days between two changes / 两次变更最小间隔天数
TIERS = ["Free", "Standard", "Pro"]
RANK = {t: i for i, t in enumerate(TIERS)}
OPEN_END = pd.Timestamp("9999-12-31")   # valid_to of the current version / 当前版本的 valid_to


def read(name, **kw):
    """Read one Silver CSV. / 读取一张 Silver CSV。"""
    return pd.read_csv(os.path.join(SILVER, f"silver_{name}.csv"), **kw)


def previous_tier(cur, rng, forbid_downgrade_into=False):
    """Pick the plan held BEFORE `cur`: lower tier = an upgrade happened, higher tier = a downgrade happened.
    选出 `cur` 之前的套餐:更低 = 发生过升级,更高 = 发生过降级。"""
    lower = [t for t in TIERS if RANK[t] < RANK[cur]]
    higher = [t for t in TIERS if RANK[t] > RANK[cur]]
    if forbid_downgrade_into:                 # avoid two downgrades in a row / 避免连续降级
        higher = []
    if lower and higher:
        pool = lower if rng.random() < P_UPGRADE else higher
    else:
        pool = lower or higher
    return pool[int(rng.integers(len(pool)))]


def change_dates(n, start, end, rng):
    """Draw n sorted change dates respecting the minimum first offset and gap (rejection sampling).
    抽 n 个排序后的变更日期,满足最早偏移和最小间隔(拒绝采样)。"""
    lo, hi = MIN_FIRST_DAYS, (end - start).days - 1
    while True:
        offs = np.sort(rng.integers(lo, hi + 1, size=n))
        if n == 1 or np.all(np.diff(offs) >= MIN_GAP_DAYS):
            return [start + pd.Timedelta(days=int(o)) for o in offs]


def build_dim_creator(creator, start, end):
    """SCD2 creator dimension with simulated plan history. / 带模拟套餐历史的 SCD2 创作者维度。"""
    rng = np.random.default_rng(SEED)
    rows = []
    for r in creator.sort_values("creator_id").itertuples(index=False):
        tiers = [r.plan_tier]                                   # built backwards from the current plan / 从当前套餐往回推
        if rng.random() < P_CHANGE:
            n = 2 if rng.random() < P_TWO_CHANGES else 1
            t1 = previous_tier(r.plan_tier, rng)
            tiers.insert(0, t1)
            if n == 2:
                t0 = previous_tier(t1, rng, forbid_downgrade_into=RANK[t1] > RANK[r.plan_tier])
                tiers.insert(0, t0)
        starts = [start] + change_dates(len(tiers) - 1, start, end, rng) if len(tiers) > 1 else [start]
        for i, (t, s) in enumerate(zip(tiers, starts)):
            last = i == len(tiers) - 1
            rows.append({"creator_id": r.creator_id, "creator_name_hash": r.creator_name_hash,
                         "creator_email_masked": r.creator_email_masked, "plan_tier": t,
                         "valid_from": s, "valid_to": OPEN_END if last else starts[i + 1] - pd.Timedelta(days=1),
                         "is_current": last})
    d = pd.DataFrame(rows).sort_values(["creator_id", "valid_from"]).reset_index(drop=True)
    d.insert(0, "creator_sk", np.arange(1, len(d) + 1))
    return d


def build_dim_date(start, end):
    """Calendar dimension for [start, end]. / 日历维度。"""
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"date_key": days.strftime("%Y%m%d").astype(int), "full_date": days,
                         "year": days.year, "quarter": days.quarter, "month": days.month,
                         "month_name": days.strftime("%B"), "week_of_year": days.isocalendar().week.astype(int).values,
                         "day_of_week": days.day_of_week + 1, "day_name": days.strftime("%A"),
                         "is_weekend": days.day_of_week >= 5})


def attach_creator_sk(fact, dim_creator, date_col):
    """Attach the creator version valid on `date_col` (point-in-time lookup).
    按事件日期匹配当时有效的创作者版本(时点查找)。"""
    left = fact.sort_values(date_col)
    right = dim_creator[["creator_sk", "creator_id", "valid_from"]].sort_values("valid_from")
    out = pd.merge_asof(left, right, left_on=date_col, right_on="valid_from", by="creator_id", direction="backward")
    return out.drop(columns=["valid_from"])


def main():
    if not os.path.isdir(SILVER):
        raise SystemExit("data/silver not found: run 02_silver.py first. / 未找到 data/silver,请先运行 02_silver.py")
    os.makedirs(OUT, exist_ok=True)

    ses = read("listening_session", parse_dates=["session_started_at"])
    sub = read("subscription", parse_dates=["subscribed_on"])
    ses["event_date"] = ses["session_started_at"].dt.normalize()
    start = min(ses["event_date"].min(), sub["subscribed_on"].min())
    end = max(ses["event_date"].max(), sub["subscribed_on"].max())

    # ---- dimensions / 维度 ----
    dim_date = build_dim_date(start, end)
    lst = read("listener").sort_values("listener_key").reset_index(drop=True)
    dim_listener = lst[["listener_key", "listener_name_hash", "listener_email_masked", "country_code"]].copy()
    dim_listener.insert(0, "listener_sk", np.arange(1, len(dim_listener) + 1))

    cat = read("category").set_index("category_id")
    top = {c: int(cat.at[c, "parent_category_id"]) if pd.notna(cat.at[c, "parent_category_id"]) else c for c in cat.index}
    show = read("podcast_show").sort_values("show_id").reset_index(drop=True)
    dim_show = show.assign(category_name=show["category_id"].map(cat["category_name"]),
                           top_category_name=show["category_id"].map(lambda c: cat.at[top[c], "category_name"]))
    dim_show = dim_show[["show_id", "show_title", "category_id", "category_name", "top_category_name", "creator_id"]]
    dim_show.insert(0, "show_sk", np.arange(1, len(dim_show) + 1))

    ep = read("episode", parse_dates=["episode_publish_date"]).sort_values("episode_id").reset_index(drop=True)
    dim_episode = ep[["episode_id", "episode_title", "episode_duration_sec", "episode_publish_date"]].copy()
    dim_episode.insert(0, "episode_sk", np.arange(1, len(dim_episode) + 1))

    dim_creator = build_dim_creator(read("creator"), start, end)

    # ---- facts / 事实表 ----
    ep_show = ep[["episode_id", "show_id"]]
    f = ses.merge(ep_show, on="episode_id").merge(dim_show[["show_id", "show_sk", "creator_id"]], on="show_id")
    f = attach_creator_sk(f, dim_creator, "event_date")
    f = (f.merge(dim_listener[["listener_key", "listener_sk"]], on="listener_key")
          .merge(dim_episode[["episode_id", "episode_sk"]], on="episode_id"))
    f["date_key"] = f["event_date"].dt.strftime("%Y%m%d").astype(int)
    fact_session = f[["date_key", "listener_sk", "episode_sk", "show_sk", "creator_sk", "device_type",
                      "session_id", "listened_seconds", "completed"]].sort_values("session_id").reset_index(drop=True)

    s = sub.merge(dim_show[["show_id", "show_sk", "creator_id"]], on="show_id")
    s = attach_creator_sk(s, dim_creator, "subscribed_on")
    s = s.merge(dim_listener[["listener_key", "listener_sk"]], on="listener_key")
    s["date_key"] = s["subscribed_on"].dt.strftime("%Y%m%d").astype(int)
    s["subscription_count"] = 1
    fact_sub = s[["date_key", "listener_sk", "show_sk", "creator_sk", "subscription_count"]] \
        .sort_values(["date_key", "listener_sk", "show_sk"]).reset_index(drop=True)

    tables = {"dim_date": dim_date, "dim_listener": dim_listener, "dim_episode": dim_episode, "dim_show": dim_show,
              "dim_creator": dim_creator, "fact_listening_session": fact_session, "fact_subscription": fact_sub}

    # ---- integrity checks / 完整性检查 ----
    cur = dim_creator[dim_creator["is_current"]].set_index("creator_id")["plan_tier"]
    a2 = read("creator").set_index("creator_id")["plan_tier"]
    dc = dim_creator.sort_values(["creator_id", "valid_from"])
    nxt = dc.groupby("creator_id")["valid_from"].shift(-1)
    checks = {
        "session rows kept (49,500 in Silver)": len(fact_session) == len(ses),
        "subscription rows kept (11,052 in Silver)": len(fact_sub) == len(sub),
        "no missing foreign keys": bool(fact_session.notna().all().all() and fact_sub.notna().all().all()),
        "session_id unique": bool(fact_session["session_id"].is_unique),
        "one current version per creator": bool(dim_creator.groupby("creator_id")["is_current"].sum().eq(1).all()),
        "current plan equals A2 plan": bool((cur.sort_index() == a2.sort_index()).all()),
        "no gaps/overlaps between versions": bool(((nxt - dc["valid_to"]).dropna() == pd.Timedelta(days=1)).all()),
        "all fact dates inside dim_date": bool(fact_session["date_key"].isin(dim_date["date_key"]).all()
                                               and fact_sub["date_key"].isin(dim_date["date_key"]).all()),
    }
    for name, df in tables.items():
        df.to_csv(os.path.join(OUT, f"{name}.csv"), index=False, encoding="utf-8")

    n_changed = int((dim_creator.groupby("creator_id").size() > 1).sum())
    report = {"data_start": str(start.date()), "data_end": str(end.date()), "seed": SEED,
              "rows": {k: len(v) for k, v in tables.items()}, "creators_with_plan_change": n_changed,
              "checks": checks}
    with open(os.path.join(OUT, "star_run_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"Date range / 日期范围: {start.date()} -> {end.date()}")
    print("\nRows / 行数")
    for k, v in tables.items():
        print(f"  {k:<24}{len(v):>8,}")
    print(f"\nCreators with a plan change / 发生套餐变更的创作者: {n_changed} of {dim_creator['creator_id'].nunique()}")
    print("\nChecks / 检查")
    for k, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {k}")


if __name__ == "__main__":
    main()
