#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
load_to_mysql.py
================
Cloud Native Data Engineering - Assignment 2, Part 4b (Load the normalized data)
云原生数据工程 - 作业 2 第 4b 部分(导入规范化后的数据)

Loads the 11 normalized CSV files (folder ./normalized) into the MySQL / RDS database
created by schema.sql, in foreign-key order, and prints the row count of every table.
把 11 个规范化 CSV(./normalized 文件夹)按外键顺序导入 schema.sql 建好的库,并打印每张表的行数。

SECURITY / 安全:
    Credentials are read from ENVIRONMENT VARIABLES only - never write a password in this file
    or in a screenshot.
    账号和密码只从环境变量读取,不要写进脚本,也不要出现在截图里。

    Windows (PowerShell):
        $env:DB_HOST="<your-rds-endpoint>"; $env:DB_USER="admin"; $env:DB_PASSWORD="<password>"
    macOS / Linux:
        export DB_HOST=<your-rds-endpoint> DB_USER=admin DB_PASSWORD=<password>

Optional / 可选: DB_PORT (3306), DB_NAME (podcast_db), DB_SSL_CA (path to the RDS CA bundle).

Usage / 用法:
    pip install pymysql pandas cryptography      # 'cryptography' is needed for MySQL 8.4's caching_sha2_password login
                                                 # MySQL 8.4 默认的 caching_sha2_password 登录方式需要 cryptography 包
    python load_to_mysql.py
"""

import os
import sys

import pandas as pd
import pymysql

# The CSV folder is looked up NEXT TO THIS SCRIPT (not in the folder you run the command from).
# Override with the environment variable CSV_DIR if you keep the files elsewhere.
# CSV 文件夹默认在"脚本所在目录"下查找(而不是运行命令时所在的目录);也可用环境变量 CSV_DIR 指定。
DATA_DIR = os.environ.get("CSV_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "normalized")
BATCH = 2000                      # 每批插入的行数 / rows per INSERT batch

# 外键顺序:被引用的表在前 / parents before children
LOAD_ORDER = ["country", "plan", "category", "creator", "podcast_show", "episode", "guest",
              "episode_guest", "listener", "subscription", "listening_session"]


def connect():
    """Open a connection using environment variables. / 用环境变量建立连接。"""
    missing = [k for k in ("DB_HOST", "DB_USER", "DB_PASSWORD") if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing environment variables: {', '.join(missing)}")
    kwargs = dict(host=os.environ["DB_HOST"], port=int(os.environ.get("DB_PORT", 3306)),
                  user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                  database=os.environ.get("DB_NAME", "podcast_db"), charset="utf8mb4", autocommit=False)
    if os.environ.get("DB_SSL_CA"):
        kwargs["ssl"] = {"ca": os.environ["DB_SSL_CA"]}
    return pymysql.connect(**kwargs)


def clean_value(v):
    """NaN / NA -> None, whole floats -> int (e.g. parent_category_id 7.0 -> 7).
    空值转 None;整数值的浮点数转 int。"""
    if pd.isna(v):
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def load_table(cur, table):
    df = pd.read_csv(os.path.join(DATA_DIR, f"{table}.csv"), encoding="utf-8")
    cols = ", ".join(f"`{c}`" for c in df.columns)
    marks = ", ".join(["%s"] * len(df.columns))
    sql = f"INSERT INTO `{table}` ({cols}) VALUES ({marks})"
    rows = [tuple(clean_value(v) for v in r) for r in df.itertuples(index=False, name=None)]
    for i in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[i:i + BATCH])
    return len(rows)


def main():
    # Fail early with a clear message if the CSV folder is missing / 文件夹不存在时给出清楚的提示
    if not os.path.isdir(DATA_DIR):
        sys.exit(f"CSV folder not found: {DATA_DIR}\n"
                 "Unzip normalized.zip so that the 'normalized' folder sits next to load_to_mysql.py.")
    print(f"Reading CSV files from: {DATA_DIR}")
    conn = connect()
    try:
        with conn.cursor() as cur:
            for table in LOAD_ORDER:
                n = load_table(cur, table)
                print(f"loaded {table:<18} {n:>7,} rows")
            conn.commit()

            print("\nRow counts read back from the database / 从数据库读回的行数:")
            total = 0
            for table in LOAD_ORDER:
                cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                n = cur.fetchone()[0]
                total += n
                print(f"  {table:<18} {n:>7,}")
            print(f"  {'TOTAL':<18} {total:>7,}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
