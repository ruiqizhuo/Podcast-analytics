#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_apis.py
=============
Assignment 3 - quick probe of two candidate public podcast APIs (no key needed).
作业 3 - 快速探测两个候选公开播客 API(不需要密钥)。

What it checks / 检查内容:
  1. iTunes Search API : does `offset` really page through results? how many rows per call?
     iTunes Search API:offset 是否真的能翻页?每次调用返回多少条?
  2. Apple RSS top chart: how many rows does one chart return? which fields exist?
     Apple RSS 排行榜:一个榜单返回多少条?有哪些字段?

Usage / 用法 (PowerShell):
    pip install requests
    python probe_apis.py
Then paste the printed output back to Claude. / 然后把打印出来的结果贴给 Claude。

Only ~5 calls are made, 4 s apart (iTunes limit is about 20 calls/minute).
只发约 5 次请求,间隔 4 秒(iTunes 限制约每分钟 20 次)。
"""

import time

import requests

ITUNES = "https://itunes.apple.com/search"
APPLE_RSS = "https://rss.marketingtools.apple.com/api/v2/us/podcasts/top/100/podcasts.json"
HEADERS = {"User-Agent": "cloud-data-eng-assignment3-probe/1.0"}
PAUSE = 4  # seconds between calls / 两次请求之间的间隔(秒)


def get(url, params=None):
    """GET with timeout; return (status, json_or_None, response_headers).
    带超时的 GET 请求;返回(状态码, JSON 或 None, 响应头)。"""
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        try:
            data = r.json()
        except ValueError:
            data = None
        return r.status_code, data, r.headers
    except requests.RequestException as exc:
        print(f"   request failed / 请求失败: {exc}")
        return None, None, {}


def itunes_page(term, limit, offset):
    """One iTunes search call; return (status, list of results).
    调用一次 iTunes 搜索;返回(状态码, 结果列表)。"""
    status, data, hdrs = get(ITUNES, {"term": term, "media": "podcast", "entity": "podcast",
                                      "limit": limit, "offset": offset})
    results = (data or {}).get("results", [])
    return status, results, hdrs


print("=" * 60)
print("1) iTunes Search API")
print("=" * 60)

pages = {}
for offset in (0, 200):
    status, results, hdrs = itunes_page("technology", 200, offset)
    ids = [x.get("collectionId") for x in results]
    pages[offset] = ids
    print(f"   offset={offset:<4} status={status}  rows={len(results)}  "
          f"Retry-After={hdrs.get('Retry-After')}")
    if offset == 0 and results:
        print("   fields / 字段:", ", ".join(sorted(results[0].keys())))
    time.sleep(PAUSE)

if pages[0] and pages[200]:
    overlap = len(set(pages[0]) & set(pages[200]))
    print(f"   overlap between page offset=0 and offset=200: {overlap} ids")
    print("   -> offset works / offset 有效" if overlap == 0
          else "   -> offset seems IGNORED or overlapping / offset 似乎无效或有重叠")
elif not pages[200]:
    print("   offset=200 returned no rows: either the result cap is < 200 or offset is unsupported.")
    print("   offset=200 没有返回数据:可能结果上限不足 200,或不支持 offset。")

# Different search terms give different result sets (fallback to reach 500 rows).
# 不同搜索词给出不同结果集(凑够 500 条的备选方案)。
seen = set(pages[0])
for term in ("comedy", "news"):
    status, results, _ = itunes_page(term, 200, 0)
    ids = {x.get("collectionId") for x in results}
    new = len(ids - seen)
    seen |= ids
    print(f"   term={term:<8} status={status}  rows={len(results)}  new unique ids={new}")
    time.sleep(PAUSE)
print(f"   unique podcasts so far / 目前去重后的节目数: {len(seen)}")

print()
print("=" * 60)
print("2) Apple RSS top chart (US, top 100)")
print("=" * 60)
status, data, hdrs = get(APPLE_RSS)
if status == 200 and data:
    results = data.get("feed", {}).get("results", [])
    print(f"   status={status}  rows={len(results)}")
    if results:
        print("   fields / 字段:", ", ".join(sorted(results[0].keys())))
        print("   first row / 第一行:", {k: results[0].get(k) for k in ("name", "artistName", "id")})
else:
    print(f"   status={status}  (URL pattern may be wrong / URL 格式可能不对)")

print()
print("Done. Paste everything above to Claude. / 完成,请把以上输出贴给 Claude。")
