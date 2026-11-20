#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
06_run_queries.py
=================
Assignment 3, Part 2 - run the analytical queries in sql/02_analytical_queries.sql and record Snowflake's own metrics.
作业 3 第 2 部分 - 运行分析查询,并记录 Snowflake 自己给出的性能指标。

For every query: print the result (first rows) and collect elapsed time, bytes scanned, partitions scanned/total
from INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION. The result cache is switched OFF for this session so a repeated
run is not answered from cache (otherwise "before/after" timings would be meaningless).
对每条查询:打印结果前几行,并从 QUERY_HISTORY_BY_SESSION 读取耗时、扫描字节、扫描/总分区数。
本会话关闭结果缓存,否则重复运行会直接命中缓存,"优化前后"的耗时就没有意义。

Usage / 用法:
  python pipeline/06_run_queries.py                 run all queries / 运行全部
  python pipeline/06_run_queries.py Q5              run one query / 只运行某一条
  python pipeline/06_run_queries.py --file other.sql  use another SQL file (used for the optimized version)
Metrics are appended to logs/query_metrics.csv. Credentials: SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_PASSWORD.
指标追加写入 logs/query_metrics.csv。凭据来自环境变量。
"""

import argparse
import os
import re
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQL = os.path.join(ROOT, "sql", "02_analytical_queries.sql")
METRICS = os.path.join(ROOT, "logs", "query_metrics.csv")
METRIC_COLS = ["label", "query", "run", "wall_seconds", "result_md5", "query_id", "total_elapsed_time",
               "compilation_time", "execution_time", "bytes_scanned", "rows_produced", "partitions_scanned",
               "partitions_total"]
MARK = re.compile(r"^-- @([QR]\d+[A-Z]?)\s*\|\s*(.*)$", re.M)


def env(name):
    """Read a required environment variable. / 读取必需的环境变量。"""
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Missing environment variable {name} / 缺少环境变量 {name}")
    return v


def parse_queries(path):
    """Split the SQL file at the '-- @Qn | title' markers. / 按标记行拆分 SQL 文件。"""
    text = open(path, encoding="utf-8").read()
    ms = list(MARK.finditer(text))
    out = []
    for i, m in enumerate(ms):
        body = text[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(text)]
        sql = "\n".join(l for l in body.splitlines() if not l.strip().startswith("--")).strip().rstrip(";")
        out.append((m.group(1), m.group(2), sql))
    return out


def fingerprint(data):
    """Order-independent hash of a result set, to prove an optimized query returns the same answer.
    结果集的哈希(与行顺序无关),用来证明优化后的查询返回相同答案。"""
    import hashlib
    lines = sorted("|".join(str(v) for v in r) for r in data)
    return hashlib.md5(chr(10).join(lines).encode()).hexdigest()[:10]


def collect_metrics(cur, qid):
    """Read Snowflake's own numbers for one finished query. Never raises: a missing number is stored as None.
    读取 Snowflake 为某条已完成查询记录的指标;读不到就记 None,不会让脚本中断。"""
    import json
    out = {"query_id": qid}
    try:                                                  # timing + bytes from the session's query history / 耗时与字节数
        cur.execute("SELECT * FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION(RESULT_LIMIT => 50))")
        cols = [c[0].lower() for c in cur.description]
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            if d.get("query_id") == qid:
                for k in ("total_elapsed_time", "compilation_time", "execution_time", "bytes_scanned", "rows_produced"):
                    out[k] = d.get(k)
                break
    except Exception as e:                                # noqa: BLE001
        print("   (could not read query history / 读不到查询历史:", str(e).splitlines()[0], ")")
    try:                                                  # partitions from the operator stats of TableScan steps / 分区数来自 TableScan 算子统计
        cur.execute("SELECT operator_type, operator_statistics FROM TABLE(GET_QUERY_OPERATOR_STATS(%s))", (qid,))
        scanned = total = 0
        for op, stats in cur.fetchall():
            if op == "TableScan":
                pr = (json.loads(stats) if isinstance(stats, str) else stats or {}).get("pruning", {})
                scanned += pr.get("partitions_scanned", 0)
                total += pr.get("partitions_total", 0)
        out["partitions_scanned"], out["partitions_total"] = scanned, total
    except Exception as e:                                # noqa: BLE001
        print("   (could not read operator stats / 读不到算子统计:", str(e).splitlines()[0], ")")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="?", help="e.g. Q5")
    ap.add_argument("--file", default=DEFAULT_SQL)
    ap.add_argument("--repeat", type=int, default=1, help="run each query N times and report the median / 每条查询运行 N 次并报告中位数")
    ap.add_argument("--setup", help="a .sql file run once before the queries (time of each statement is printed) / 查询前先执行一次的 .sql 文件")
    ap.add_argument("--setup-only", action="store_true", help="run --setup and stop / 只执行 --setup 就结束")
    ap.add_argument("--label", default="baseline", help="tag stored with the metrics, e.g. baseline / optimized")
    args = ap.parse_args()

    import snowflake.connector
    conn = snowflake.connector.connect(account=env("SNOWFLAKE_ACCOUNT"), user=env("SNOWFLAKE_USER"),
                                       password=env("SNOWFLAKE_PASSWORD"))
    cur = conn.cursor()
    rows = []
    try:
        cur.execute("USE WAREHOUSE PODCAST_WH")
        cur.execute("USE DATABASE PODCAST_DW")
        cur.execute("ALTER SESSION SET USE_CACHED_RESULT = FALSE")      # no result cache / 关闭结果缓存
        cur.execute("SELECT 1")                                          # wake the warehouse first / 先唤醒仓库
        pd.set_option("display.width", 200)
        if args.setup:
            from snowflake.connector.util_text import split_statements
            with open(args.setup, encoding="utf-8") as fh:
                for stmt, _ in split_statements(fh, remove_comments=True):
                    if stmt.strip():
                        s0 = time.time()
                        cur.execute(stmt)
                        print(f"setup ({time.time() - s0:.1f} s): {stmt.strip().splitlines()[0][:90]}")
            if args.setup_only:
                return
        for qid, title, sql in parse_queries(args.file):
            if args.only and qid != args.only:
                continue
            for run in range(1, args.repeat + 1):
                t0 = time.time()
                cur.execute(sql)
                data = cur.fetchall()
                wall = time.time() - t0
                if run == 1:                                   # show the result once / 结果只打印一次
                    df = pd.DataFrame(data, columns=[c[0].lower() for c in cur.description])
                    print("\n=== " + qid + ": " + title + "\n" + df.head(15).to_string(index=False))
                    if len(df) > 15:
                        print(f"... ({len(df)} rows)")
                rec = {"label": args.label, "query": qid, "run": run, "wall_seconds": round(wall, 2),
                       "result_md5": fingerprint(data)}
                rec.update(collect_metrics(cur, cur.sfqid))
                rows.append(rec)
                print(f"   run {run}:", {k: v for k, v in rec.items() if k not in ("label", "query", "run", "query_id")})
    finally:
        cur.close()
        conn.close()
    os.makedirs(os.path.dirname(METRICS), exist_ok=True)
    new = pd.DataFrame(rows).reindex(columns=METRIC_COLS)      # fixed columns so appended runs always line up / 固定列,追加时才不会错位
    new.to_csv(METRICS, mode="a", header=not os.path.exists(METRICS), index=False)
    if args.repeat > 1 and rows:                 # median over repeated runs / 多次运行取中位数
        med = pd.DataFrame(rows).groupby("query")[["total_elapsed_time", "execution_time", "bytes_scanned"]].median()
        print("\nMedian over runs / 多次运行的中位数 (ms, ms, bytes)\n" + med.to_string())
    print(f"\nMetrics appended to logs{os.sep}query_metrics.csv")


if __name__ == "__main__":
    main()
