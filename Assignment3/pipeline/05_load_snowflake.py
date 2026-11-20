#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05_load_snowflake.py
====================
Assignment 3, Part 2 - create the Snowflake objects and load Bronze / Silver / Star data, then verify.
作业 3 第 2 部分 - 建 Snowflake 对象,加载 Bronze / Silver / 星型模型数据,并做校验。

Steps / 步骤
  1. run sql/01_ddl_and_views.sql (warehouse, database, schemas, tables, Gold views)
  2. PUT each local file to an internal stage, COPY INTO the table
  3. check: Snowflake row count == local file row count
  4. check: Gold views in Snowflake == data/gold/*.csv produced by pandas (within rounding)
  1. 执行 DDL 脚本  2. 上传文件到内部 Stage 并 COPY INTO  3. 校验行数  4. 校验 Gold 视图与 pandas 结果一致

Credentials come ONLY from environment variables (never printed, never written to a file):
  SNOWFLAKE_ACCOUNT  e.g. ORG-ACCOUNT        SNOWFLAKE_USER        SNOWFLAKE_PASSWORD
凭据只从环境变量读取,不打印、不写入文件。

Usage / 用法:  python pipeline/05_load_snowflake.py
Needs: pip install snowflake-connector-python  /  需要先安装 snowflake-connector-python。
This script only touches objects inside database PODCAST_DW (plus the PODCAST_WH warehouse).
本脚本只操作 PODCAST_DW 数据库内的对象(以及 PODCAST_WH 仓库)。
"""

import glob
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
DDL = os.path.join(ROOT, "sql", "01_ddl_and_views.sql")

# (schema.table, local csv path)  -- order matters only for readability; constraints are not enforced
# (表, 本地文件) 顺序仅为可读性;Snowflake 不强制约束
CSV_TABLES = (
    [(f"SILVER.{t.upper()}", f"silver/silver_{t}.csv") for t in
     ["category", "country", "plan", "creator", "podcast_show", "episode", "guest", "episode_guest", "listener",
      "subscription", "listening_session", "api_podcast", "api_chart_rank"]]
    + [(f"STAR.{t.upper()}", f"star/{t}.csv") for t in
       ["dim_date", "dim_listener", "dim_episode", "dim_show", "dim_creator",
        "fact_listening_session", "fact_subscription"]])


def env(name):
    """Read a required environment variable. / 读取必需的环境变量。"""
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Missing environment variable {name} / 缺少环境变量 {name}")
    return v


def run_sql_file(cur, path):
    """Execute every statement in a .sql file. / 执行 .sql 文件里的每条语句。"""
    from snowflake.connector.util_text import split_statements
    with open(path, encoding="utf-8") as f:
        for stmt, _ in split_statements(f, remove_comments=True):
            if stmt.strip():
                cur.execute(stmt)


def put_and_copy(cur, table, csv_rel):
    """Upload one CSV to the stage and COPY it into `table`. / 上传一个 CSV 并 COPY 进表。"""
    path = os.path.join(DATA, csv_rel)
    sub = table.replace(".", "_").lower()
    cur.execute(f"REMOVE @PODCAST_DW.STAGE.LOAD_STAGE/{sub}/")                 # clear our own stage folder / 清理自己的 stage 子目录
    cur.execute(f"PUT 'file://{path.replace(os.sep, '/')}' @PODCAST_DW.STAGE.LOAD_STAGE/{sub}/ "
                f"AUTO_COMPRESS=TRUE OVERWRITE=TRUE")
    cur.execute(f"COPY INTO PODCAST_DW.{table} FROM @PODCAST_DW.STAGE.LOAD_STAGE/{sub}/ "
                f"FILE_FORMAT=(TYPE=CSV SKIP_HEADER=1 FIELD_OPTIONALLY_ENCLOSED_BY='\"' NULL_IF=('') "
                f"EMPTY_FIELD_AS_NULL=TRUE) ON_ERROR=ABORT_STATEMENT")


def load_bronze(cur):
    """Load the raw API JSON lines into BRONZE.API_RAW (one VARIANT per response).
    把原始 API JSON 行加载进 BRONZE.API_RAW(每个响应一个 VARIANT)。"""
    files = sorted(glob.glob(os.path.join(DATA, "bronze", "api_raw_*.jsonl")))
    if not files:
        print("  (no Bronze JSONL found, skipped / 没找到 Bronze 文件,跳过)")
        return 0
    cur.execute("REMOVE @PODCAST_DW.STAGE.LOAD_STAGE/bronze_api_raw/")
    for p in files:
        cur.execute(f"PUT 'file://{p.replace(os.sep, '/')}' @PODCAST_DW.STAGE.LOAD_STAGE/bronze_api_raw/ "
                    f"AUTO_COMPRESS=TRUE OVERWRITE=TRUE")
    cur.execute("COPY INTO PODCAST_DW.BRONZE.API_RAW FROM (SELECT $1:source_name::VARCHAR, "
                "$1:ingested_at::TIMESTAMP_TZ, $1:request_url::VARCHAR, $1:request_params, $1:http_status::NUMBER, "
                "$1:raw_payload FROM @PODCAST_DW.STAGE.LOAD_STAGE/bronze_api_raw/) "
                "FILE_FORMAT=(TYPE=JSON) ON_ERROR=ABORT_STATEMENT")
    return sum(sum(1 for _ in open(p, encoding="utf-8")) for p in files)


def view_df(cur, name):
    """Read a Gold view into a DataFrame with lower-case column names. / 把 Gold 视图读成 DataFrame。"""
    cur.execute(f"SELECT * FROM PODCAST_DW.GOLD.{name}")
    df = pd.DataFrame(cur.fetchall(), columns=[c[0].lower() for c in cur.description])
    return df


def same(sf, local, key):
    """Compare a Snowflake view with the pandas Gold CSV: same keys, numbers equal within 0.051 (rounding).
    比较 Snowflake 视图与 pandas 的 Gold CSV:键相同,数值误差 <= 0.051(四舍五入差异)。"""
    sf = sf.sort_values(key).reset_index(drop=True)
    local = local.sort_values(key).reset_index(drop=True)
    if list(sf[key]) != list(local[key]) or list(sf.columns) != list(local.columns):
        return False, "keys or columns differ / 键或列不同"
    worst = 0.0
    for c in local.columns:
        if c == key:
            continue
        a = pd.to_numeric(sf[c], errors="coerce").astype(float)
        b = pd.to_numeric(local[c], errors="coerce").astype(float)
        if not (a.isna() == b.isna()).all():
            return False, f"NULL pattern differs in {c} / {c} 的空值位置不同"
        d = (a - b).abs().max(skipna=True)
        worst = max(worst, 0.0 if pd.isna(d) else float(d))
    return worst <= 0.051, f"max abs diff {worst:.3f} / 最大绝对差 {worst:.3f}"


def main():
    try:
        import snowflake.connector
    except ImportError:
        raise SystemExit("pip install snowflake-connector-python / 请先安装 snowflake-connector-python")
    conn = snowflake.connector.connect(account=env("SNOWFLAKE_ACCOUNT"), user=env("SNOWFLAKE_USER"),
                                       password=env("SNOWFLAKE_PASSWORD"))
    cur = conn.cursor()
    try:
        print("1/4 Creating objects / 创建对象 ...")
        run_sql_file(cur, DDL)

        print("2/4 Loading files / 加载文件 ...")
        counts = {}
        for table, rel in CSV_TABLES:
            put_and_copy(cur, table, rel)
            counts[table] = len(pd.read_csv(os.path.join(DATA, rel)))
        counts["BRONZE.API_RAW"] = load_bronze(cur)

        print("3/4 Row counts / 行数校验")
        ok_all = True
        for table, n in counts.items():
            cur.execute(f"SELECT COUNT(*) FROM PODCAST_DW.{table}")
            got = cur.fetchone()[0]
            ok = got == n
            ok_all &= ok
            print(f"  {'PASS' if ok else 'FAIL'}  {table:<32}{got:>8,} (local {n:,})")

        print("4/4 Gold views vs pandas / Gold 视图与 pandas 对比")
        for view, csv, key in [("GOLD_CATEGORY_OVERVIEW", "gold_category_overview.csv", "a2_top_category"),
                               ("GOLD_PLAN_RETENTION", "gold_plan_retention.csv", "plan_tier"),
                               ("GOLD_CATEGORY_RETENTION", "gold_category_retention.csv", "a2_top_category")]:
            local = pd.read_csv(os.path.join(DATA, "gold", csv))
            ok, msg = same(view_df(cur, view), local, key)
            ok_all &= ok
            print(f"  {'PASS' if ok else 'FAIL'}  {view:<26}{msg}")
        print("\nAll checks passed / 全部通过" if ok_all else "\nSome checks FAILED / 有检查未通过")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
