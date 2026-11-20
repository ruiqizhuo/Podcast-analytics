#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
07_load_neo4j.py
================
Assignment 3, Part 3 - load the podcast graph (model B) into Neo4j Aura from the masked Silver CSVs, then verify.
作业 3 第 3 部分 - 把脱敏后的 Silver CSV 加载成图(方案 B)放进 Neo4j Aura,并做校验。

Graph model / 图模型
  (Creator)-[:PUBLISHES]->(Show)-[:IN_CATEGORY]->(Category)-[:SUBCATEGORY_OF]->(Category)
  (Listener)-[:SUBSCRIBED_TO {on}]->(Show)
  (Listener)-[:LISTENED_TO {sessions, seconds, completed}]->(Show)   one edge per (listener, show), summed from sessions
  (Episode)-[:OF_SHOW]->(Show)        (Guest)-[:APPEARED_ON]->(Episode)
Only masked data is loaded (no names, no e-mail addresses). / 只加载脱敏数据(没有姓名和邮箱)。

Credentials come ONLY from environment variables (never printed, never written to a file):
  NEO4J_URI (e.g. neo4j+s://xxxx.databases.neo4j.io)   NEO4J_USER   NEO4J_PASSWORD
凭据只从环境变量读取,不打印、不写入文件。

Idempotent: constraints use IF NOT EXISTS and every write is MERGE, so re-running does not duplicate anything.
可重复运行:约束用 IF NOT EXISTS,所有写入用 MERGE,重复运行不会产生重复数据。
Usage / 用法:  python pipeline/07_load_neo4j.py       Needs: pip install neo4j
"""

import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SILVER = os.path.join(ROOT, "data", "silver")
BATCH = 1000

CONSTRAINTS = [   # one uniqueness constraint per node label (also creates the lookup index) / 每种节点一个唯一约束
    "CREATE CONSTRAINT listener_key IF NOT EXISTS FOR (n:Listener) REQUIRE n.listener_key IS UNIQUE",
    "CREATE CONSTRAINT show_id IF NOT EXISTS FOR (n:Show) REQUIRE n.show_id IS UNIQUE",
    "CREATE CONSTRAINT creator_id IF NOT EXISTS FOR (n:Creator) REQUIRE n.creator_id IS UNIQUE",
    "CREATE CONSTRAINT category_id IF NOT EXISTS FOR (n:Category) REQUIRE n.category_id IS UNIQUE",
    "CREATE CONSTRAINT episode_id IF NOT EXISTS FOR (n:Episode) REQUIRE n.episode_id IS UNIQUE",
    "CREATE CONSTRAINT guest_id IF NOT EXISTS FOR (n:Guest) REQUIRE n.guest_id IS UNIQUE",
]


def env(name):
    """Read a required environment variable. / 读取必需的环境变量。"""
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Missing environment variable {name} / 缺少环境变量 {name}")
    return v


def rd(name):
    """Read one Silver CSV. / 读取一个 Silver CSV。"""
    return pd.read_csv(os.path.join(SILVER, f"silver_{name}.csv"))


def records(df):
    """DataFrame -> list of plain dicts (NaN -> None). / 转成字典列表(NaN 变 None)。"""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def write(session, query, rows):
    """Run `query` with UNWIND $rows in batches of BATCH. / 按批执行 UNWIND 写入。"""
    for i in range(0, len(rows), BATCH):
        session.run("UNWIND $rows AS r " + query, rows=rows[i:i + BATCH]).consume()


def build_edges():
    """Prepare all relationship tables with pandas. / 用 pandas 准备所有关系数据。"""
    sess, epi = rd("listening_session"), rd("episode")
    m = sess.merge(epi[["episode_id", "show_id"]], on="episode_id")
    m["done"] = (m["completed"] == "Y").astype(int)
    listened = (m.groupby(["listener_key", "show_id"])
                .agg(sessions=("session_id", "count"), seconds=("listened_seconds", "sum"), completed=("done", "sum"))
                .reset_index())
    return listened


def main():
    try:
        from neo4j import GraphDatabase
    except ImportError:
        raise SystemExit("pip install neo4j / 请先安装 neo4j 驱动")
    listener, show, creator, cat = rd("listener"), rd("podcast_show"), rd("creator"), rd("category")
    epi, guest, epg, sub = rd("episode"), rd("guest"), rd("episode_guest"), rd("subscription")
    listened = build_edges()

    driver = GraphDatabase.driver(env("NEO4J_URI"), auth=(env("NEO4J_USER"), env("NEO4J_PASSWORD")))
    try:
        driver.verify_connectivity()
        print("Connected to Neo4j / 已连接 Neo4j")
        with driver.session() as s:
            print("1/3 Constraints / 约束")
            for c in CONSTRAINTS:
                s.run(c).consume()

            print("2/3 Loading nodes and relationships / 加载节点和关系")
            write(s, "MERGE (n:Listener {listener_key: r.listener_key}) SET n.country_code = r.country_code",
                  records(listener[["listener_key", "country_code"]]))
            write(s, "MERGE (n:Creator {creator_id: r.creator_id}) SET n.plan_tier = r.plan_tier",
                  records(creator[["creator_id", "plan_tier"]]))
            write(s, "MERGE (n:Category {category_id: r.category_id}) SET n.name = r.category_name",
                  records(cat[["category_id", "category_name"]]))
            write(s, "MATCH (c:Category {category_id: r.category_id}), (p:Category {category_id: r.parent_category_id}) "
                     "MERGE (c)-[:SUBCATEGORY_OF]->(p)",
                  records(cat.dropna(subset=["parent_category_id"]).astype({"parent_category_id": int})
                          [["category_id", "parent_category_id"]]))
            write(s, "MERGE (n:Show {show_id: r.show_id}) SET n.title = r.show_title "
                     "WITH n, r MATCH (c:Creator {creator_id: r.creator_id}) MERGE (c)-[:PUBLISHES]->(n) "
                     "WITH n, r MATCH (k:Category {category_id: r.category_id}) MERGE (n)-[:IN_CATEGORY]->(k)",
                  records(show[["show_id", "show_title", "creator_id", "category_id"]]))
            write(s, "MERGE (n:Episode {episode_id: r.episode_id}) SET n.title = r.episode_title, "
                     "n.duration_sec = r.episode_duration_sec, n.published = r.episode_publish_date "
                     "WITH n, r MATCH (sh:Show {show_id: r.show_id}) MERGE (n)-[:OF_SHOW]->(sh)",
                  records(epi[["episode_id", "show_id", "episode_title", "episode_duration_sec", "episode_publish_date"]]))
            write(s, "MERGE (n:Guest {guest_id: r.guest_id})", records(guest[["guest_id"]]))
            write(s, "MATCH (g:Guest {guest_id: r.guest_id}), (e:Episode {episode_id: r.episode_id}) "
                     "MERGE (g)-[:APPEARED_ON]->(e)", records(epg[["guest_id", "episode_id"]]))
            write(s, "MATCH (l:Listener {listener_key: r.listener_key}), (sh:Show {show_id: r.show_id}) "
                     "MERGE (l)-[x:SUBSCRIBED_TO]->(sh) SET x.on = r.subscribed_on",
                  records(sub[["listener_key", "show_id", "subscribed_on"]]))
            write(s, "MATCH (l:Listener {listener_key: r.listener_key}), (sh:Show {show_id: r.show_id}) "
                     "MERGE (l)-[x:LISTENED_TO]->(sh) SET x.sessions = r.sessions, x.seconds = r.seconds, "
                     "x.completed = r.completed",
                  records(listened))

            print("3/3 Checks vs the CSV files / 与 CSV 对比校验")
            expect_nodes = {"Listener": len(listener), "Creator": len(creator), "Category": len(cat), "Show": len(show),
                            "Episode": len(epi), "Guest": len(guest)}
            expect_rels = {"PUBLISHES": len(show), "IN_CATEGORY": len(show), "SUBCATEGORY_OF": int(cat["parent_category_id"].notna().sum()),
                           "OF_SHOW": len(epi), "APPEARED_ON": len(epg), "SUBSCRIBED_TO": len(sub), "LISTENED_TO": len(listened)}
            ok_all = True
            for lab, n in expect_nodes.items():
                got = s.run(f"MATCH (n:{lab}) RETURN count(n) AS c").single()["c"]
                ok_all &= got == n
                print(f"  {'PASS' if got == n else 'FAIL'}  node {lab:<16}{got:>8,} (expected {n:,})")
            for rel, n in expect_rels.items():
                got = s.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c").single()["c"]
                ok_all &= got == n
                print(f"  {'PASS' if got == n else 'FAIL'}  rel  {rel:<16}{got:>8,} (expected {n:,})")
            tot = s.run("MATCH (l:Listener)-[x:LISTENED_TO]->() RETURN sum(x.sessions) AS c").single()["c"]
            ok_all &= tot == len(rd("listening_session"))
            print(f"  {'PASS' if tot == len(rd('listening_session')) else 'FAIL'}  sessions summed on LISTENED_TO {tot:,} "
                  f"(expected {len(rd('listening_session')):,})")
            print("\nAll checks passed / 全部通过" if ok_all else "\nSome checks FAILED / 有检查未通过")
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
