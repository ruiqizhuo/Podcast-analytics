#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_ingest_api.py
================
Assignment 3, Part 1a - live API ingestion (Bronze) + data-quality checks.
作业 3 第 1a 部分 - 实时 API 采集(Bronze 层)+ 数据质量检查。

What this script does / 这个脚本做什么
--------------------------------------
Step 1  Chart pull / 取榜单
        For each country, call the Apple RSS "top podcasts" chart. One call -> up to 100 podcasts
        (only id, name, artist, genres, url). Gives us WHO is on the chart and at WHAT rank.
        对每个国家调用 Apple RSS 榜单接口,一次最多 100 个节目(只有 id、名字、作者、类目、链接)。
        告诉我们"谁上榜、排第几"。
Step 2  Lookup / 按 id 补全
        Send the podcast ids to the iTunes Lookup API in batches of 100 (this is our "pagination":
        the id list is cut into pages and we loop until every page is done). Each id returns ~30
        fields (feedUrl, trackCount, releaseDate, primaryGenreName, ...).
        把 id 列表切成每批 100 个发给 iTunes Lookup 接口(这就是我们的"分页":把列表切成页,循环到全部处理完)。
        每个 id 返回约 30 个字段(feedUrl、trackCount、releaseDate、primaryGenreName 等)。
Step 3  Bronze / 原始层
        Every raw JSON response is stored untouched, with audit columns ingested_at and source_name.
        每个原始 JSON 响应原样保存,并附加审计字段 ingested_at 和 source_name。
Step 4  Quality checks / 质量检查
        6 automatic checks; pass/fail counts are logged; row-level flags are saved for Silver.
        6 项自动检查,记录通过/失败行数;逐行标记保存下来,供 Silver 使用。

Why not "offset" paging? / 为什么不用 offset 翻页?
        We tested it: the iTunes search endpoint ignores `offset` (same rows for offset 0/50/100).
        实测 iTunes 搜索接口忽略 offset(offset 为 0/50/100 返回同一批数据),所以改用上面的方式。

No API key is needed and no credential is read or written.
不需要 API 密钥,也不读写任何凭据。

Usage / 用法:
    python pipeline/01_ingest_api.py                 # defaults: target 650 ids
    python pipeline/01_ingest_api.py --target 700
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests

# ----------------------------------------------------------------------------
# 1) Configuration / 配置
# ----------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RSS_URL = "https://rss.marketingtools.apple.com/api/v2/{country}/podcasts/top/{limit}/podcasts.json"
LOOKUP_URL = "https://itunes.apple.com/lookup"
SOURCE_CHART = "apple_rss_top_podcasts"
SOURCE_LOOKUP = "itunes_lookup"

# Countries tried in order until we have enough unique ids. (Some may fail: that is handled.)
# 按顺序尝试这些国家,直到去重后的 id 数量足够。(个别国家可能失败,代码会处理。)
COUNTRIES = ["us", "gb", "ca", "au", "de", "fr", "jp", "br", "in", "mx", "es", "nl"]
CHART_LIMIT = 100          # the chart endpoint worked with 100 (200 returned HTTP 500 in our test)
                           # 实测 100 可用(200 返回过 HTTP 500)
BATCH_SIZE = 100           # ids per lookup call (200 also worked in our test) / 每次 lookup 的 id 数
MIN_RECORDS = 500          # assignment minimum / 作业要求的最少记录数

MIN_INTERVAL = 3.0         # seconds between ANY two calls: iTunes allows roughly 20 calls/min (our belief,
                           # not verified in the docs) -> 3 s = 20/min.
                           # 任意两次请求之间至少间隔 3 秒:约每分钟 20 次(我们的理解,没在官方文档核实)。
MAX_RETRIES = 5            # attempts per call / 每次请求最多尝试次数
TIMEOUT = 20               # seconds to wait for the server / 等待服务器的秒数
RETRY_STATUS = {403, 429, 500, 502, 503, 504}   # worth retrying (403 is how iTunes can signal throttling)
                                                # 值得重试的状态码(iTunes 可能用 403 表示限流)
HEADERS = {"User-Agent": "cloud-data-eng-assignment3/1.0"}   # generic client name / 通用客户端名

log = logging.getLogger("ingest")


# ----------------------------------------------------------------------------
# 2) A polite, robust HTTP caller / 礼貌且健壮的请求函数
# ----------------------------------------------------------------------------
class Caller:
    """Wraps requests.get with throttling, retries, backoff and Retry-After handling.
    给 requests.get 加上限速、重试、退避和 Retry-After 处理。"""

    def __init__(self):
        self.session = requests.Session()         # reuse the connection / 复用连接
        self.session.headers.update(HEADERS)
        self._last_call = 0.0
        self.stats = {"calls": 0, "ok": 0, "retries": 0, "failed": 0, "bad_payload": 0}

    def _throttle(self):
        """Sleep so that calls are at least MIN_INTERVAL apart. / 保证相邻请求间隔不少于 MIN_INTERVAL。"""
        wait = MIN_INTERVAL - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def get_json(self, url, params=None):
        """Return (payload_dict, http_status) or (None, last_status) after all retries failed.
        成功返回 (字典, 状态码);重试用完仍失败返回 (None, 最后一次状态码)。"""
        status = None
        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            self.stats["calls"] += 1
            retry_after = None
            try:
                r = self.session.get(url, params=params, timeout=TIMEOUT)
                status = r.status_code
                if status == 200:
                    try:
                        payload = r.json()
                    except ValueError:                       # 200 but not JSON / 200 但不是 JSON
                        self.stats["bad_payload"] += 1
                        log.warning("   attempt %d: HTTP 200 but body is not JSON", attempt)
                        payload = None
                    if isinstance(payload, dict) and payload:  # non-empty JSON object / 非空 JSON 对象
                        self.stats["ok"] += 1
                        return payload, status
                    if payload is not None:                   # empty payload / 空数据
                        self.stats["bad_payload"] += 1
                        log.warning("   attempt %d: HTTP 200 but empty payload", attempt)
                elif status in RETRY_STATUS:
                    retry_after = r.headers.get("Retry-After")
                    log.warning("   attempt %d: HTTP %s (retryable)", attempt, status)
                else:                                         # e.g. 404: retrying will not help / 如 404:重试没用
                    log.error("   HTTP %s (not retryable) for %s", status, r.url)
                    self.stats["failed"] += 1
                    return None, status
            except (requests.Timeout, requests.ConnectionError) as exc:
                status = None
                log.warning("   attempt %d: %s", attempt, type(exc).__name__)

            if attempt < MAX_RETRIES:
                self.stats["retries"] += 1
                # Prefer the server's Retry-After (seconds); else exponential backoff 2,4,8,16 s + jitter.
                # 优先听服务器的 Retry-After(秒);否则指数退避 2、4、8、16 秒 + 随机抖动。
                if retry_after and str(retry_after).isdigit():
                    delay = int(retry_after)
                else:
                    delay = min(60, 2 ** attempt) + random.uniform(0, 1)
                log.info("   waiting %.1f s before retry", delay)
                time.sleep(delay)
        self.stats["failed"] += 1
        log.error("   giving up after %d attempts: %s", MAX_RETRIES, url)
        return None, status


# ----------------------------------------------------------------------------
# 3) Bronze writer / Bronze 写入
# ----------------------------------------------------------------------------
def write_bronze(fh, source_name, url, params, status, payload):
    """Append ONE raw response as ONE JSON line, with audit metadata. No cleaning at all.
    把一个原始响应作为一行 JSON 追加写入,附带审计信息。不做任何清洗。"""
    record = {
        "source_name": source_name,                                   # audit: where it came from / 来源
        "ingested_at": datetime.now(timezone.utc).isoformat(),        # audit: when / 采集时间(UTC)
        "request_url": url, "request_params": params, "http_status": status,
        "raw_payload": payload,                                       # the untouched response / 原样响应
    }
    fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ----------------------------------------------------------------------------
# 4) Step 1 - charts / 第 1 步:榜单
# ----------------------------------------------------------------------------
def pull_charts(caller, bronze_fh, target_ids):
    """Fetch country charts until we hold >= target_ids unique podcast ids.
    逐个国家取榜单,直到去重后的 id 数量 >= target_ids。
    Returns chart rows [{id, country, rank}] and the ordered unique id list."""
    chart_rows, seen = [], []
    seen_set = set()
    for country in COUNTRIES:
        if len(seen_set) >= target_ids:
            break
        url = RSS_URL.format(country=country, limit=CHART_LIMIT)
        log.info("chart %-2s ...", country)
        payload, status = caller.get_json(url)
        if payload is None:
            log.warning("chart %-2s skipped (HTTP %s)", country, status)
            continue
        write_bronze(bronze_fh, SOURCE_CHART, url, None, status, payload)
        # Defensive parsing: a missing key must not crash the run / 防御式解析:缺键不能让程序崩溃
        results = (payload.get("feed") or {}).get("results")
        if not results:
            log.warning("chart %-2s: no 'feed.results' in payload, skipped", country)
            continue
        new = 0
        for rank, item in enumerate(results, start=1):
            pid = item.get("id")
            if not pid:
                continue
            chart_rows.append({"podcast_id": str(pid), "chart_country": country, "chart_rank": rank})
            if pid not in seen_set:
                seen_set.add(pid)
                seen.append(str(pid))
                new += 1
        log.info("chart %-2s: %d rows, %d new ids, %d unique so far", country, len(results), new, len(seen_set))
    return chart_rows, seen


# ----------------------------------------------------------------------------
# 5) Step 2 - lookup in batches ("pages") / 第 2 步:分批(分页)lookup
# ----------------------------------------------------------------------------
def lookup_all(caller, bronze_fh, ids):
    """Cut `ids` into pages of BATCH_SIZE and look each page up. Missing ids are counted, not fatal.
    把 ids 切成每页 BATCH_SIZE 个,逐页 lookup。查不到的 id 只计数,不会让程序崩溃。"""
    records = []
    pages = [ids[i:i + BATCH_SIZE] for i in range(0, len(ids), BATCH_SIZE)]
    for n, page in enumerate(pages, start=1):
        params = {"id": ",".join(page), "entity": "podcast"}
        log.info("lookup page %d/%d (%d ids) ...", n, len(pages), len(page))
        payload, status = caller.get_json(LOOKUP_URL, params)
        if payload is None:
            log.warning("lookup page %d skipped (HTTP %s)", n, status)
            continue
        write_bronze(bronze_fh, SOURCE_LOOKUP, LOOKUP_URL, params, status, payload)
        results = payload.get("results")
        if not isinstance(results, list) or not results:      # missing key / empty list / 缺键或空列表
            log.warning("lookup page %d: 'results' missing or empty", n)
            continue
        log.info("lookup page %d: asked %d, got %d", n, len(page), len(results))
        records.extend(results)
    return records


# ----------------------------------------------------------------------------
# 6) Step 4 - quality checks / 第 4 步:质量检查
# ----------------------------------------------------------------------------
def to_dt(value):
    """Parse an ISO-8601 date or return NaT. / 解析 ISO-8601 日期,失败返回 NaT。"""
    return pd.to_datetime(value, errors="coerce", utc=True)


def run_quality_checks(df):
    """Run 6 row-level checks. Adds one boolean column per check (True = passed).
    执行 6 项逐行检查,每项新增一列布尔值(True = 通过)。"""
    now = pd.Timestamp.now(tz="UTC")
    track = pd.to_numeric(df["trackCount"], errors="coerce")
    release = df["releaseDate"].map(to_dt)

    checks = {
        # 1 null check / 空值检查
        "chk_id_not_null": df["collectionId"].notna(),
        # 2 duplicate detection: every repeat after the first is a fail / 重复检测:第二次及以后出现的算失败
        "chk_id_unique": ~df["collectionId"].duplicated(keep="first") | df["collectionId"].isna(),
        # 3 range check: episode count is a whole number in [0, 20000] (20000 = our assumption)
        #   范围检查:集数是 [0, 20000] 的整数(20000 是我们的假设上限)
        "chk_trackcount_range": track.between(0, 20000) & (track % 1 == 0),
        # 4 format check: releaseDate parses and is not in the future / 格式检查:发布日期可解析且不在未来
        "chk_release_date_valid": release.notna() & (release <= now),
        # 5 null check on the field we need to link to Assignment 2 categories / 与 A2 类目关联所需字段不能为空
        "chk_genre_not_null": df["primaryGenreName"].notna() & (df["primaryGenreName"].astype(str).str.strip() != ""),
        # 6 format check: feedUrl looks like a URL / 格式检查:feedUrl 像一个网址
        "chk_feed_url_format": df["feedUrl"].astype(str).str.match(r"^https?://", na=False),
    }
    out = df.copy()
    for name, ok in checks.items():
        out[name] = ok.fillna(False).astype(bool)
    flag_cols = list(checks)
    out["qc_passed"] = out[flag_cols].all(axis=1)
    return out, flag_cols


# ----------------------------------------------------------------------------
# 7) Main / 入口
# ----------------------------------------------------------------------------
def setup_logging(log_path):
    """Console: short messages. File: timestamped. / 控制台:简短;文件:带时间戳。"""
    log.setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(message)s"))
    logfile = logging.FileHandler(log_path, encoding="utf-8")
    logfile.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.handlers[:] = [console, logfile]


def main():
    ap = argparse.ArgumentParser(description="Live API ingestion (Bronze) + quality checks.")
    ap.add_argument("--target", type=int, default=650,
                    help="unique ids to collect before lookup (buffer above 500) / 查询前要凑够的去重 id 数")
    args = ap.parse_args()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bronze_dir = os.path.join(ROOT, "data", "bronze")
    staging_dir = os.path.join(ROOT, "data", "staging")
    log_dir = os.path.join(ROOT, "logs")
    for d in (bronze_dir, staging_dir, log_dir):
        os.makedirs(d, exist_ok=True)
    setup_logging(os.path.join(log_dir, f"ingest_{run_id}.log"))

    caller = Caller()
    bronze_path = os.path.join(bronze_dir, f"api_raw_{run_id}.jsonl")
    with open(bronze_path, "w", encoding="utf-8") as fh:
        chart_rows, ids = pull_charts(caller, fh, args.target)
        log.info("-> %d unique ids from %d chart rows", len(ids), len(chart_rows))
        records = lookup_all(caller, fh, ids) if ids else []

    log.info("-> %d records retrieved from the lookup API (minimum %d)", len(records), MIN_RECORDS)
    if not records:
        log.error("No records retrieved; nothing to check.")
        sys.exit(1)

    # Flatten for the quality checks. Bronze above is untouched; this is only a staging copy.
    # 摊平后做质量检查。上面的 Bronze 原样未动;这里只是一份暂存副本。
    df = pd.DataFrame(records)
    for col in ("collectionId", "trackCount", "releaseDate", "primaryGenreName", "feedUrl"):
        if col not in df.columns:                        # missing key in ALL rows / 所有行都缺这个键
            df[col] = pd.NA
    df["collectionId"] = df["collectionId"].astype("string")
    df["ingested_at"] = datetime.now(timezone.utc).isoformat()
    df["source_name"] = SOURCE_LOOKUP

    df, flag_cols = run_quality_checks(df)

    # Row-level pass/fail counts / 逐项通过与失败的行数
    log.info("\nQuality checks (%d rows)", len(df))
    log.info("%-26s %8s %8s", "check", "passed", "failed")
    report = {}
    for c in flag_cols:
        p = int(df[c].sum())
        report[c] = {"passed": p, "failed": len(df) - p}
        log.info("%-26s %8d %8d", c, p, len(df) - p)
    log.info("%-26s %8d %8d", "ALL CHECKS", int(df["qc_passed"].sum()), int((~df["qc_passed"]).sum()))

    # Save staging data, chart ranks and the report / 保存暂存数据、榜单名次和报告
    stage_path = os.path.join(staging_dir, "api_records.csv")
    chart_path = os.path.join(staging_dir, "api_chart_ranks.csv")
    # list-valued columns (genres, genreIds) cannot go into a flat CSV; genres is kept as 'a|b|c'
    # 列表型列(genres、genreIds)不能直接写进平面 CSV;genres 保留为 'a|b|c'
    if "genres" in df.columns:
        df["genres"] = df["genres"].map(lambda g: "|".join(g) if isinstance(g, list) else None)
    keep = [c for c in df.columns if not df[c].map(lambda v: isinstance(v, (list, dict))).any()]
    df[keep].to_csv(stage_path, index=False, encoding="utf-8")
    pd.DataFrame(chart_rows).to_csv(chart_path, index=False, encoding="utf-8")
    summary = {"run_id": run_id, "unique_ids_requested": len(ids), "records_retrieved": len(records),
               "minimum_required": MIN_RECORDS, "meets_minimum": len(records) >= MIN_RECORDS,
               "http": caller.stats, "checks": report,
               "all_checks_passed_rows": int(df["qc_passed"].sum()),
               "quarantine_candidates": int((~df["qc_passed"]).sum())}
    with open(os.path.join(log_dir, f"quality_report_{run_id}.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    log.info("\nHTTP: %s", caller.stats)
    log.info("Bronze  : %s", os.path.relpath(bronze_path, ROOT))
    log.info("Staging : %s", os.path.relpath(stage_path, ROOT))
    if len(records) < MIN_RECORDS:
        log.error("Only %d records (< %d). Re-run with a larger --target.", len(records), MIN_RECORDS)
        sys.exit(2)


if __name__ == "__main__":
    main()
