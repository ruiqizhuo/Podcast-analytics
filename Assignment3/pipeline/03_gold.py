#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_gold.py
==========
Assignment 3, Part 1b - Gold layer: three curated summary tables built from Silver.
作业 3 第 1b 部分 - Gold 层:基于 Silver 生成三张汇总表。

Tables / 表
  gold_category_overview  (choice A / 选择 A)
      One row per A2 top-level category (+ 'Unmapped' for API-only rows).
      A2 side: shows, sessions, listening hours, completion rate.
      API side: charted podcasts, average episode count, share scheduled in the future.
      每个 A2 一级类目一行(外加只在 API 里出现的 'Unmapped')。
      A2 一侧:节目数、会话数、收听小时、完播率。API 一侧:上榜节目数、平均集数、预约未来更新占比。
  gold_plan_retention     (choice D / 选择 D)
      One row per creator plan tier: 30-day retention of subscriptions (A2 data only).
      每个创作者套餐一行:订阅的 30 天留存(只用 A2 数据)。
  gold_category_retention (added after review / 评审后新增)
      One row per A2 top-level category: A2 30-day retention next to API chart coverage (charted podcasts, share,
      average chart rank). Each side is aggregated on its own first and only then joined on the category, so
      no A2 record is counted twice. This is the second Gold table that combines A2 records with API enrichment.
      每个 A2 一级类目一行:A2 的 30 天留存与 API 榜单覆盖(上榜节目数、占比、平均榜单名次)并列。两侧先各自聚合,
      再按类目连接,因此不会重复计算 A2 记录。这是第二张把 A2 记录与 API 数据结合的 Gold 表。

Retention definition (fixed before looking at results) / 留存口径(先定义、后看结果)
  A subscription (listener, show) is RETAINED if the listener has >= 1 session on that show within the
  30 days AFTER subscribed_on (day 0 included, day 30 excluded).
  Only subscriptions up to 2026-08-31 (complete months) are analysed. This is a deliberate month-end cutoff: a subscription on
  2026-09-01 would also have a full 30-day window (data ends 2026-09-30; 39 such subscriptions), but it is left out.
  Newer subscriptions are reported separately as 'not_yet_observable'.
  订阅(听众, 节目)若在 subscribed_on 之后的 30 天内(含第 0 天,不含第 30 天)对该节目至少有 1 次会话,则算"留存"。
  只分析截至 2026-08-31(完整月份)的订阅。这是有意选的月末截止日:9 月 1 日的订阅(39 条)其实也有完整的 30 天窗口(数据到 2026-09-30),但没有纳入;更新的订阅单独列为 not_yet_observable。
  Caveat: the data is synthetic and sessions can precede subscribed_on (A2 report, section 1.6).
  说明:数据是合成的,会话可能早于 subscribed_on(A2 报告 1.6 节)。

Usage / 用法:  python pipeline/03_gold.py      (needs data/silver from 02_silver.py / 需要先跑 02_silver.py)
No credentials needed. / 不需要凭据。
"""

import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SILVER = os.path.join(ROOT, "data", "silver")
GOLD = os.path.join(ROOT, "data", "gold")
DATA_END = pd.Timestamp("2026-09-30")          # last day of A2 data / A2 数据最后一天
WINDOW_DAYS = 30                               # retention window / 留存窗口(天)
LAST_FULL_SUB_DATE = DATA_END - pd.Timedelta(days=WINDOW_DAYS)   # 2026-08-31: month-end cutoff (2026-09-01 would also fit) / 月末截止日


def read(name, **kw):
    """Read one Silver CSV. / 读取一张 Silver CSV。"""
    return pd.read_csv(os.path.join(SILVER, f"silver_{name}.csv"), **kw)


def top_category_map():
    """Top-level category name of every category id (a top-level category is its own top level).
    每个类目的一级类目名(一级类目的一级就是它自己)。"""
    cat = read("category")
    top_name = cat.set_index("category_id")["category_name"]
    parent = cat.set_index("category_id")["parent_category_id"]
    return {cid: top_name[int(parent[cid])] if pd.notna(parent[cid]) else top_name[cid] for cid in cat["category_id"]}


def category_overview():
    """Gold A: A2 listening activity next to API chart presence, joined on top-level category.
    Gold A:按一级类目,把 A2 收听情况与 API 上榜情况放在一起。"""
    top_of = top_category_map()

    show = read("podcast_show")
    show["a2_top_category"] = show["category_id"].map(top_of)
    ep = read("episode")[["episode_id", "show_id", "episode_duration_sec"]]
    ses = read("listening_session")[["episode_id", "listened_seconds", "completed"]]
    ses = ses.merge(ep, on="episode_id").merge(show[["show_id", "a2_top_category"]], on="show_id")

    a2 = ses.groupby("a2_top_category").agg(
        sessions=("completed", "size"), listening_hours=("listened_seconds", lambda s: round(s.sum() / 3600, 1)),
        completion_rate_pct=("completed", lambda s: round(100 * (s == "Y").mean(), 1))).reset_index()
    a2 = a2.merge(show.groupby("a2_top_category").size().rename("a2_shows").reset_index(), on="a2_top_category")

    api = read("api_podcast", dtype={"podcast_id": str})
    api_g = api.groupby("a2_top_category").agg(
        api_charted_podcasts=("podcast_id", "nunique"), api_avg_episode_count=("track_count", lambda s: round(s.mean(), 1)),
        api_scheduled_future_pct=("is_scheduled_future", lambda s: round(100 * s.mean(), 1))).reset_index()

    out = a2.merge(api_g, on="a2_top_category", how="outer")      # outer: keep 'Unmapped' and any gaps / 外连接
    out["listening_hours_share_pct"] = (100 * out["listening_hours"] / out["listening_hours"].sum()).round(1)
    out["api_chart_share_pct"] = (100 * out["api_charted_podcasts"] / out["api_charted_podcasts"].sum()).round(1)
    cols = ["a2_top_category", "a2_shows", "sessions", "listening_hours", "listening_hours_share_pct",
            "completion_rate_pct", "api_charted_podcasts", "api_chart_share_pct", "api_avg_episode_count",
            "api_scheduled_future_pct"]
    out = out[cols].sort_values("listening_hours", ascending=False, na_position="last").reset_index(drop=True)
    for c in ("a2_shows", "sessions", "api_charted_podcasts"):      # whole numbers stay integers / 整数保持整数
        out[c] = out[c].astype("Int64")
    return out


def subscription_flags():
    """One row per subscription with its 30-day `retained` flag and `observable` flag (shared by two Gold tables).
    每条订阅一行,带 30 天 `retained` 与 `observable` 标记(两张 Gold 表共用)。"""
    sub = read("subscription", parse_dates=["subscribed_on"])
    show = read("podcast_show")[["show_id", "creator_id"]]
    cr = read("creator")[["creator_id", "plan_tier"]]
    sub = sub.merge(show, on="show_id").merge(cr, on="creator_id")

    ses = read("listening_session", parse_dates=["session_started_at"])[["listener_key", "episode_id", "session_started_at"]]
    ses = ses.merge(read("episode")[["episode_id", "show_id"]], on="episode_id")[["listener_key", "show_id", "session_started_at"]]

    # one pass: attach every session of the same (listener, show) to the subscription, then test the window
    # 一次性:把同一(听众, 节目)的所有会话接到订阅上,再判断是否落在窗口内
    m = sub.merge(ses, on=["listener_key", "show_id"], how="left")
    days = (m["session_started_at"].dt.normalize() - m["subscribed_on"]).dt.days
    m["in_window"] = days.ge(0) & days.lt(WINDOW_DAYS)
    flag = m.groupby(["listener_key", "show_id"])["in_window"].any().rename("retained").reset_index()
    sub = sub.merge(flag, on=["listener_key", "show_id"], how="left")
    sub["observable"] = sub["subscribed_on"] <= LAST_FULL_SUB_DATE
    return sub


def plan_retention():
    """Gold D: 30-day retention of subscriptions by creator plan tier.
    Gold D:按创作者套餐统计订阅的 30 天留存。"""
    sub = subscription_flags()
    rows = []
    for tier, g in sub.groupby("plan_tier"):
        obs = g[g["observable"]]
        rows.append({"plan_tier": tier, "subscriptions": len(g), "observable_subscriptions": len(obs),
                     "retained_30d": int(obs["retained"].sum()),
                     "retention_30d_pct": round(100 * obs["retained"].mean(), 1),
                     "not_yet_observable": int((~g["observable"]).sum())})
    out = pd.DataFrame(rows)
    out["plan_tier"] = pd.Categorical(out["plan_tier"], ["Free", "Standard", "Pro"], ordered=True)
    total = {"plan_tier": "ALL", "subscriptions": out["subscriptions"].sum(),
             "observable_subscriptions": out["observable_subscriptions"].sum(),
             "retained_30d": out["retained_30d"].sum(),
             "retention_30d_pct": round(100 * out["retained_30d"].sum() / out["observable_subscriptions"].sum(), 1),
             "not_yet_observable": out["not_yet_observable"].sum()}
    return pd.concat([out.sort_values("plan_tier").astype({"plan_tier": str}), pd.DataFrame([total])], ignore_index=True)


def category_retention():
    """Gold E: A2 30-day retention per top-level category next to API chart coverage (each side aggregated first).
    Gold E:按一级类目并列 A2 的 30 天留存与 API 榜单覆盖(两侧先各自聚合再连接)。"""
    top_of = top_category_map()
    sub = subscription_flags().merge(read("podcast_show")[["show_id", "category_id"]], on="show_id")
    sub["a2_top_category"] = sub["category_id"].map(top_of)
    sub["retained_obs"] = sub["retained"] & sub["observable"]
    a2 = sub.groupby("a2_top_category").agg(
        a2_subscriptions=("retained", "size"), observable_subscriptions=("observable", "sum"),
        retained_30d=("retained_obs", "sum")).reset_index()
    a2["retention_30d_pct"] = (100 * a2["retained_30d"] / a2["observable_subscriptions"]).round(1)

    api = read("api_podcast", dtype={"podcast_id": str})
    rank = read("api_chart_rank", dtype={"podcast_id": str}).merge(api[["podcast_id", "a2_top_category"]], on="podcast_id")
    api_g = api.groupby("a2_top_category").agg(api_charted_podcasts=("podcast_id", "nunique")).reset_index()
    api_g = api_g.merge(rank.groupby("a2_top_category")["chart_rank"].mean().round(1).rename("api_avg_chart_rank").reset_index(),
                        on="a2_top_category", how="left")

    out = a2.merge(api_g, on="a2_top_category", how="outer")         # keep 'Unmapped' / 保留 'Unmapped'
    out["api_chart_share_pct"] = (100 * out["api_charted_podcasts"] / out["api_charted_podcasts"].sum()).round(1)
    has_a2 = out["a2_subscriptions"].notna()                          # ranks only among A2 categories / 只在 A2 类目之间排名
    out["retention_rank"] = out.loc[has_a2, "retention_30d_pct"].rank(method="min", ascending=False)
    out["chart_share_rank"] = out.loc[has_a2, "api_chart_share_pct"].rank(method="min", ascending=False)
    cols = ["a2_top_category", "a2_subscriptions", "observable_subscriptions", "retained_30d", "retention_30d_pct",
            "api_charted_podcasts", "api_chart_share_pct", "api_avg_chart_rank", "retention_rank", "chart_share_rank"]
    out = out[cols].sort_values("retention_30d_pct", ascending=False, na_position="last").reset_index(drop=True)
    for c in ("a2_subscriptions", "observable_subscriptions", "retained_30d", "api_charted_podcasts", "retention_rank", "chart_share_rank"):
        out[c] = out[c].astype("Int64")
    return out


def main():
    if not os.path.isdir(SILVER):
        raise SystemExit("data/silver not found: run pipeline/02_silver.py first. / 未找到 data/silver,请先运行 02_silver.py")
    os.makedirs(GOLD, exist_ok=True)
    a, d, e = category_overview(), plan_retention(), category_retention()
    a.to_csv(os.path.join(GOLD, "gold_category_overview.csv"), index=False, encoding="utf-8")
    d.to_csv(os.path.join(GOLD, "gold_plan_retention.csv"), index=False, encoding="utf-8")
    e.to_csv(os.path.join(GOLD, "gold_category_retention.csv"), index=False, encoding="utf-8")
    with open(os.path.join(GOLD, "gold_run_report.json"), "w", encoding="utf-8") as f:
        json.dump({"retention_window_days": WINDOW_DAYS, "last_full_window_subscription_date": str(LAST_FULL_SUB_DATE.date()),
                   "category_rows": len(a), "plan_rows": len(d), "category_retention_rows": len(e)}, f, indent=2)
    pd.set_option("display.width", 200)
    print("gold_category_overview / 类目概览\n", a.to_string(index=False))
    print("\ngold_plan_retention / 套餐留存\n", d.to_string(index=False))
    print("\ngold_category_retention / 类目留存与榜单覆盖\n", e.to_string(index=False))
    print(f"\nFiles: data{os.sep}gold{os.sep}")


if __name__ == "__main__":
    main()
