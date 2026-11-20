#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
08_run_cypher.py
================
Assignment 3, Part 3/4 - run the Cypher queries in cypher/01_queries.cypher on Neo4j Aura and print the results.
作业 3 第 3/4 部分 - 在 Neo4j Aura 上运行 cypher/01_queries.cypher 里的查询并打印结果。

Usage / 用法:
  python pipeline/08_run_cypher.py            run all / 运行全部
  python pipeline/08_run_cypher.py N2         run one / 只运行一条
  python pipeline/08_run_cypher.py --file F   another .cypher file / 换一个文件
Credentials: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (environment only). / 凭据只来自环境变量。
Times are measured by the client and include network time; they are NOT Neo4j-internal timings.
耗时由客户端测得,包含网络时间,不是 Neo4j 内部耗时。
"""

import argparse
import os
import re
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "cypher", "01_queries.cypher")
MARK = re.compile(r"^// @(N\d+[A-Z]?)\s*\|\s*(.*)$", re.M)


def env(name):
    """Read a required environment variable. / 读取必需的环境变量。"""
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Missing environment variable {name} / 缺少环境变量 {name}")
    return v


def parse(path):
    """Split the file at the '// @Nn | title' markers. / 按标记行拆分文件。"""
    text = open(path, encoding="utf-8").read()
    ms = list(MARK.finditer(text))
    out = []
    for i, m in enumerate(ms):
        body = text[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(text)]
        q = "\n".join(l for l in body.splitlines() if not l.strip().startswith("//")).strip().rstrip(";")
        out.append((m.group(1), m.group(2), q))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="?")
    ap.add_argument("--file", default=DEFAULT)
    args = ap.parse_args()
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(env("NEO4J_URI"), auth=(env("NEO4J_USER"), env("NEO4J_PASSWORD")))
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 60)
    try:
        with driver.session() as s:
            for qid, title, q in parse(args.file):
                if args.only and qid != args.only:
                    continue
                t0 = time.time()
                res = s.run(q)
                rows = [r.data() for r in res]
                res.consume()
                wall = time.time() - t0
                print(f"\n=== {qid}: {title}")
                print(pd.DataFrame(rows).to_string(index=False) if rows else "(no rows)")
                print(f"   {len(rows)} rows, client-side time {wall * 1000:.0f} ms")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
