#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_podcast_flat_data.py
=============================
Cloud Native Data Engineering - Assignment 2, Part 1 (Option A: synthetic data)
云原生数据工程 - 作业 2 第 1 部分(方案 A:合成数据)

Domain / 领域:
    Podcast hosting + creator-side retention analytics (same domain as Assignment 1).
    播客托管 + 创作者侧留存分析(与作业 1 相同)。

What it produces / 产出:
    ONE flat, denormalized "wide" table. One row = one listening session
    (a listener plays one episode at one moment).
    一张扁平的非规范化"宽表"。一行 = 一次收听会话(某位听众在某个时刻播放某一集)。

Intentional data problems (required by the assignment) / 有意埋入的数据问题(作业要求):
    * repeated listener / creator names, cities and e-mails on every row   (重复的姓名、城市、邮箱)
    * inconsistent casing / spacing / spelling of names, countries, categories (大小写、空格、拼写不一致)
    * exact duplicate rows ("duplicate groups", e.g. logging retries)        (重复行,如日志重试)
    * NULL values (missing e-mail, city; no parent category; no guests)      (空值)
    * a multi-valued column (episode_guests) that breaks 1NF                 (多值列,违反 1NF)
    * stale values: the same creator/listener with two different e-mails     (过期值,用于演示更新异常)

Reproducible: a fixed random seed is used, so every run gives the same data.
可复现:使用固定随机种子,每次运行结果相同。

Usage / 用法:
    python generate_podcast_flat_data.py --rows 50000 --out podcast_sessions_flat.csv
"""

import argparse
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

# ----------------------------------------------------------------------------
# 1) Configuration / 参数配置
# ----------------------------------------------------------------------------
SEED = 42                      # 随机种子 / random seed
N_CREATORS = 150               # 创作者数量 / number of creators
N_LISTENERS = 6000             # 听众数量 / number of listeners
DUP_RATE = 0.01                # 重复行比例 / share of exact duplicate rows

END_DATE = date(2026, 9, 30)               # 会话数据截止日 / last day with sessions
SHOW_LAUNCH_FROM = date(2025, 6, 1)        # 节目最早上线日 / earliest show launch
SHOW_LAUNCH_TO = date(2026, 3, 1)          # 节目最晚上线日 / latest show launch
EPISODE_LAST_PUBLISH = date(2026, 9, 20)   # 单集最晚发布日 / latest episode publish date

# 套餐:名称 -> 月费(美元)。月费由套餐决定 => 传递依赖 (creator -> plan -> price)
# Plans: name -> monthly price. Price depends on plan => transitive dependency.
PLANS = {"Free": 0, "Standard": 20, "Pro": 50}
PLAN_WEIGHTS = [0.30, 0.50, 0.20]

# 类目层级:一级类目 -> 二级类目 (自引用层级的来源)
# Category hierarchy: top-level -> children (source of the self-referencing hierarchy)
CATEGORY_TREE = {
    "Technology": ["Software Development", "AI & Machine Learning", "Gadgets"],
    "Business": ["Entrepreneurship", "Marketing", "Investing"],
    "Health & Fitness": ["Nutrition", "Mental Health", "Running"],
    "True Crime": ["Cold Cases", "Courtroom Stories"],
    "Comedy": ["Stand-up", "Improv"],
    "Education": ["Language Learning", "Science", "History"],
    "Arts": ["Film Reviews", "Books"],
    "News": ["Daily Briefing", "Analysis"],
}

# 国家代码 -> (国家名, 城市列表) / country code -> (name, cities)
COUNTRIES = {
    "US": ("United States", ["New York", "Chicago", "Austin", "Seattle", "Atlanta", "Denver"]),
    "GB": ("United Kingdom", ["London", "Manchester", "Leeds"]),
    "CA": ("Canada", ["Toronto", "Vancouver", "Montreal"]),
    "DE": ("Germany", ["Berlin", "Munich", "Hamburg"]),
    "FR": ("France", ["Paris", "Lyon"]),
    "IN": ("India", ["Mumbai", "Bengaluru", "Delhi"]),
    "BR": ("Brazil", ["Sao Paulo", "Rio de Janeiro"]),
    "AU": ("Australia", ["Sydney", "Melbourne"]),
    "JP": ("Japan", ["Tokyo", "Osaka"]),
    "MX": ("Mexico", ["Mexico City", "Guadalajara"]),
    "ES": ("Spain", ["Madrid", "Barcelona"]),
    "NL": ("Netherlands", ["Amsterdam", "Utrecht"]),
}
COUNTRY_WEIGHTS = [0.38, 0.10, 0.08, 0.07, 0.05, 0.08, 0.05, 0.05, 0.04, 0.04, 0.03, 0.03]
# 国家名的"脏"写法 / messy spellings of country names
COUNTRY_VARIANTS = {
    "US": ["USA", "U.S.", "United States of America"],
    "GB": ["UK", "Great Britain", "England"],
}

DEVICES = ["Mobile", "Desktop", "Tablet", "Smart Speaker"]
DEVICE_WEIGHTS = [0.62, 0.22, 0.08, 0.08]
DEVICE_VARIANTS = {"Mobile": ["mobile", "MOBILE"], "Desktop": ["desktop", "DESKTOP"],
                   "Tablet": ["tablet"], "Smart Speaker": ["smart speaker", "smart_speaker", "SmartSpeaker"]}

# 用于生成节目名与单集名的词库 / word lists for show and episode titles
SHOW_WORDS = {
    "Technology": (["Byte", "Stack", "Kernel", "Pixel", "Circuit", "Cloud"], ["Weekly", "Talks", "Unplugged", "Lab", "Report"]),
    "Business": (["Founders", "Startup", "Market", "Ledger", "Venture", "Pitch"], ["Unfiltered", "Hour", "Playbook", "Diaries", "Brief"]),
    "Health & Fitness": (["Daily", "Mindful", "Stride", "Fuel", "Balance", "Vital"], ["Habits", "Coach", "Minutes", "Journey", "Clinic"]),
    "True Crime": (["Cold", "Midnight", "Case", "Shadow", "Verdict", "Silent"], ["Files", "Tapes", "Docket", "Trail", "Stories"]),
    "Comedy": (["Laugh", "Banter", "Punchline", "Wit", "Giggle", "Roast"], ["Club", "Hour", "Show", "Riot", "Special"]),
    "Education": (["Curious", "Lecture", "Scholar", "Learn", "Atlas", "Think"], ["Hall", "Notes", "Academy", "Corner", "Minutes"]),
    "Arts": (["Reel", "Chapter", "Canvas", "Stage", "Scene", "Margin"], ["Review", "Club", "Notes", "Society", "Hour"]),
    "News": (["Morning", "Evening", "Global", "Signal", "Wire", "Front"], ["Briefing", "Digest", "Update", "Desk", "Round-up"]),
}
EPISODE_PHRASES = {
    "Technology": ["Why your API keeps timing out", "Inside a modern data center", "Open source burnout", "Edge computing explained", "Is the cloud too expensive", "Debugging in production", "The future of chips", "Privacy by design", "Rust versus Go", "Your first machine learning model"],
    "Business": ["How we got our first 100 customers", "Pricing lessons learned", "Hiring too fast", "Raising a seed round", "Cash flow basics", "When to pivot", "Building a brand", "Cold email that works", "Lessons from failure", "Scaling customer support"],
    "Health & Fitness": ["Sleep and recovery", "Building a morning routine", "Protein myths", "Running your first 10K", "Managing stress at work", "Strength training basics", "Hydration facts", "Mindful breathing", "Injury prevention", "Meal prep made simple"],
    "True Crime": ["The missing ledger", "A cold trail", "Inside the courtroom", "The unsolved night", "A witness steps forward", "The forged letter", "Evidence on trial", "The long investigation", "A town in doubt", "The final appeal"],
    "Comedy": ["Worst first dates", "Airport confessions", "Office politics", "Improv gone wrong", "Family dinner disasters", "My terrible roommates", "Road trip rules", "Karaoke night", "Tiny pet rivalries", "Awkward small talk"],
    "Education": ["How memory really works", "A short history of maps", "Learning a language fast", "The science of sleep", "Ancient trade routes", "Why the sky is blue", "Study habits that last", "The printing revolution", "Math without fear", "Climate basics"],
    "Arts": ["A classic reconsidered", "The art of the opening scene", "Debut novels worth reading", "Behind the camera", "Poetry for beginners", "Stage fright stories", "Why sequels disappoint", "Indie film picks", "Writing every day", "Museum after dark"],
    "News": ["Today in review", "Markets at the open", "The week ahead", "Local stories that matter", "Explainer: the budget", "Global headlines", "Weather and travel", "Tech policy update", "Sports round-up", "Reader questions"],
}
STUDIO_A = ["blue", "north", "echo", "pine", "amber", "river", "lumen", "cedar", "orbit", "maple"]
STUDIO_B = ["audio", "studio", "media", "labs", "works", "sound"]
EMAIL_DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "icloud.com", "proton.me"]

COLUMNS = [  # 最终列顺序 / final column order
    "session_started_at", "listened_seconds", "completed", "device_type",
    "listener_id", "listener_name", "listener_email", "listener_city",
    "listener_country_code", "listener_country_name",
    "episode_id", "episode_title", "episode_duration_sec", "episode_publish_date", "episode_guests",
    "show_id", "show_title", "category_name", "parent_category_name",
    "creator_id", "creator_name", "creator_email", "creator_plan_tier", "creator_plan_price_usd",
    "is_subscribed", "subscribed_on",
]


# ----------------------------------------------------------------------------
# 2) Build the clean "master data" / 先造干净的主数据
# ----------------------------------------------------------------------------
def build_catalog(rng, fake):
    """Creators -> shows -> episodes (clean).
    创作者 -> 节目 -> 单集(干净版本)。"""
    creators, shows, episodes = [], [], []
    used_titles = set()
    topics = list(CATEGORY_TREE.keys())
    guest_pool = [fake.name() for _ in range(300)]

    for cid in range(1, N_CREATORS + 1):
        first, last = fake.first_name(), fake.last_name()
        plan = str(rng.choice(list(PLANS), p=PLAN_WEIGHTS))
        studio = f"{rng.choice(STUDIO_A)}{rng.choice(STUDIO_B)}"
        creators.append({
            "creator_id": cid, "creator_name": f"{first} {last}",
            "creator_email": f"{first}.{last}@{studio}.com".lower(),
            "creator_plan_tier": plan, "creator_plan_price_usd": PLANS[plan],
        })

        for _ in range(int(rng.choice([1, 2, 3], p=[0.55, 0.30, 0.15]))):
            topic = str(rng.choice(topics))
            # 88% 的节目挂在二级类目;12% 直接挂在一级类目(父类目为空) => 演示 NULL 与递归
            # 88% of shows sit in a child category; 12% directly in a top-level one (NULL parent)
            if rng.random() < 0.88:
                category, parent = str(rng.choice(CATEGORY_TREE[topic])), topic
            else:
                category, parent = topic, None

            a, b = SHOW_WORDS[topic]
            while True:
                title = f"The {rng.choice(a)} {rng.choice(b)}" if rng.random() < 0.5 else f"{rng.choice(a)} {rng.choice(b)}"
                if title not in used_titles:
                    used_titles.add(title)
                    break
                title = f"{title} {int(rng.integers(2, 99))}"
                if title not in used_titles:
                    used_titles.add(title)
                    break

            show_id = len(shows) + 1
            shows.append({"show_id": show_id, "show_title": title, "category_name": category,
                          "parent_category_name": parent, "creator_id": cid, "topic": topic})

            # 单集:每 7~21 天发一集 / one episode every 7-21 days
            launch = SHOW_LAUNCH_FROM + timedelta(days=int(rng.integers(0, (SHOW_LAUNCH_TO - SHOW_LAUNCH_FROM).days)))
            pub = launch
            for k in range(1, int(rng.integers(6, 21)) + 1):
                if pub > EPISODE_LAST_PUBLISH:
                    break
                # 约 45% 的单集有嘉宾;多个嘉宾放在同一个单元格里 => 违反 1NF
                # ~45% of episodes have guests, stored in ONE cell => violates 1NF
                guests = None
                if rng.random() < 0.45:
                    names = [str(g) for g in rng.choice(guest_pool, size=int(rng.integers(1, 4)), replace=False)]
                    guests = ("; " if rng.random() < 0.85 else ", ").join(names)
                dur = int(np.clip(rng.lognormal(mean=np.log(2100), sigma=0.45), 600, 5400))
                episodes.append({
                    "episode_id": len(episodes) + 1, "show_id": show_id,
                    "episode_title": f"#{k} {rng.choice(EPISODE_PHRASES[topic])}",
                    "episode_duration_sec": dur, "episode_publish_date": pub, "episode_guests": guests,
                })
                pub += timedelta(days=int(rng.integers(7, 22)))

    return pd.DataFrame(creators), pd.DataFrame(shows), pd.DataFrame(episodes)


def build_listeners(rng, fake):
    """Listeners with a home country/city and a (clean) e-mail.
    听众:带国家、城市和(干净的)邮箱。"""
    codes = list(COUNTRIES)
    rows = []
    for lid in range(1, N_LISTENERS + 1):
        first, last = fake.first_name(), fake.last_name()
        code = str(rng.choice(codes, p=COUNTRY_WEIGHTS))
        rows.append({
            "listener_id": lid, "listener_name": f"{first} {last}",
            "listener_email": f"{first}.{last}{int(rng.integers(1, 999))}@{rng.choice(EMAIL_DOMAINS)}".lower(),
            "listener_city": str(rng.choice(COUNTRIES[code][1])),
            "listener_country_code": code, "listener_country_name": COUNTRIES[code][0],
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# 3) Generate sessions (one row = one listening session) / 生成收听会话
# ----------------------------------------------------------------------------
def zipf_weights(rng, n, s=0.9):
    """Long-tail popularity: a few popular items, many rarely played ones.
    长尾热度:少数热门,大量冷门(会产生只被播放 1 次的单集)。"""
    w = 1.0 / (np.arange(n) + 3) ** s
    rng.shuffle(w)
    return w / w.sum()


def generate_sessions(rng, creators, shows, episodes, listeners, n_base):
    show_w = zipf_weights(rng, len(shows))
    eps_by_show = {sid: g.reset_index(drop=True) for sid, g in episodes.groupby("show_id")}
    ep_w = {sid: zipf_weights(rng, len(g), s=0.8) for sid, g in eps_by_show.items()}
    show_launch = episodes.groupby("show_id")["episode_publish_date"].min().to_dict()

    # 每位听众订阅若干节目(热门节目被订阅更多)=> 听众-节目多对多
    # each listener subscribes to a few shows => listener-show many-to-many
    subs = {}
    for lid in listeners["listener_id"]:
        k = int(np.clip(rng.poisson(3), 0, 8))
        chosen = rng.choice(len(shows), size=min(k, len(shows)), replace=False, p=show_w) if k else []
        subs[lid] = {}
        for si in chosen:
            sid = int(shows.iloc[si]["show_id"])
            span = max(1, (END_DATE - show_launch[sid]).days)
            subs[lid][sid] = show_launch[sid] + timedelta(days=int(rng.integers(0, span)))

    act = rng.lognormal(0, 1.0, size=len(listeners))          # 听众活跃度 / listener activity
    act = act / act.sum()
    hour_w = np.array([1, 1, 1, 1, 1, 2, 4, 7, 8, 6, 5, 5, 7, 6, 5, 5, 6, 8, 10, 12, 12, 10, 6, 3], float)
    hour_w /= hour_w.sum()

    lis_idx = listeners.set_index("listener_id")
    cr_idx = creators.set_index("creator_id")
    sh_idx = shows.set_index("show_id")

    rows, seen = [], set()
    while len(rows) < n_base:
        lid = int(listeners.iloc[int(rng.choice(len(listeners), p=act))]["listener_id"])
        mine = list(subs[lid])
        if mine and rng.random() < 0.70:          # 70% 来自已订阅的节目 / 70% from subscribed shows
            sid = int(rng.choice(mine))
        else:
            sid = int(shows.iloc[int(rng.choice(len(shows), p=show_w))]["show_id"])
        eps = eps_by_show[sid]
        ep = eps.iloc[int(rng.choice(len(eps), p=ep_w[sid]))]

        # 会话时间 = 发布日 + 指数分布的延迟,且不晚于截止日 / publish date + exponential delay, capped
        pub = ep["episode_publish_date"]
        room = (END_DATE - pub).days
        if room < 0:
            continue
        delay = min(int(rng.exponential(12)), room)
        started = datetime.combine(pub + timedelta(days=delay), datetime.min.time()) + timedelta(
            hours=int(rng.choice(24, p=hour_w)), minutes=int(rng.integers(0, 60)), seconds=int(rng.integers(0, 60)))

        key = (lid, int(ep["episode_id"]), started)
        if key in seen:
            continue
        seen.add(key)

        dur = int(ep["episode_duration_sec"])
        frac = 1.0 if rng.random() < 0.42 else float(np.clip(rng.beta(1.5, 2.0) * 0.95, 0.02, 0.94))
        L, S, C = lis_idx.loc[lid], sh_idx.loc[sid], cr_idx.loc[int(sh_idx.loc[sid]["creator_id"])]
        sub_on = subs[lid].get(sid)
        rows.append({
            "session_started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
            "listened_seconds": int(round(frac * dur)),
            "completed": "Y" if frac >= 0.95 else "N",
            "device_type": str(rng.choice(DEVICES, p=DEVICE_WEIGHTS)),
            "listener_id": lid, "listener_name": L["listener_name"], "listener_email": L["listener_email"],
            "listener_city": L["listener_city"], "listener_country_code": L["listener_country_code"],
            "listener_country_name": L["listener_country_name"],
            "episode_id": int(ep["episode_id"]), "episode_title": ep["episode_title"],
            "episode_duration_sec": dur, "episode_publish_date": pub.strftime("%Y-%m-%d"),
            "episode_guests": ep["episode_guests"],
            "show_id": sid, "show_title": S["show_title"], "category_name": S["category_name"],
            "parent_category_name": S["parent_category_name"],
            "creator_id": int(S["creator_id"]), "creator_name": C["creator_name"], "creator_email": C["creator_email"],
            "creator_plan_tier": C["creator_plan_tier"], "creator_plan_price_usd": int(C["creator_plan_price_usd"]),
            # is_subscribed / subscribed_on describe the listener-show subscription as of the data end date and are
            # repeated on every session of that listener and show; a session can be EARLIER than subscribed_on.
            # is_subscribed / subscribed_on 表示截至数据截止日的订阅状态,会重复写在该听众该节目的每条会话上;
            # 因此某次播放的时间可以早于 subscribed_on(先听后订阅)。
            "is_subscribed": "Y" if sub_on else "N",
            "subscribed_on": sub_on.strftime("%Y-%m-%d") if sub_on else None,
        })
    return pd.DataFrame(rows)[COLUMNS]


# ----------------------------------------------------------------------------
# 4) Inject realistic data problems / 注入真实感的数据问题
# ----------------------------------------------------------------------------
def messy_person_name(name, style):
    """Different ways the same person's name can be typed.
    同一个人名的不同"脏"写法。"""
    first, last = name.split(" ", 1)
    return [name.lower(), name.upper(), f"{first}  {last}", f"{last}, {first}", f"{name} "][style]


def inject_problems(rng, df):
    df = df.copy()
    n = len(df)

    def pick(rate):                                    # 随机挑一部分行 / random subset of rows
        return rng.choice(n, size=int(n * rate), replace=False)

    # (a) 听众姓名:大小写/空格/"姓, 名" 不一致 (8% 的行) / inconsistent listener names
    for i in pick(0.08):
        df.iat[i, df.columns.get_loc("listener_name")] = messy_person_name(df.iat[i, df.columns.get_loc("listener_name")], int(rng.integers(0, 5)))
    # (b) 创作者姓名偶尔大小写不一致 (2%) / occasional creator-name casing
    for i in pick(0.02):
        v = df.iat[i, df.columns.get_loc("creator_name")]
        df.iat[i, df.columns.get_loc("creator_name")] = v.upper() if rng.random() < 0.5 else v.lower()
    # (c) 国家名写法不一致 (只改有变体的国家,约 5% 的行) / inconsistent country names
    for i in pick(0.05):
        code = df.iat[i, df.columns.get_loc("listener_country_code")]
        if code in COUNTRY_VARIANTS:
            df.iat[i, df.columns.get_loc("listener_country_name")] = str(rng.choice(COUNTRY_VARIANTS[code]))
    # (d) 类目名大小写不一致 (3%) / category casing
    for i in pick(0.03):
        v = df.iat[i, df.columns.get_loc("category_name")]
        df.iat[i, df.columns.get_loc("category_name")] = v.lower() if rng.random() < 0.5 else v.upper()
    # (e) 设备类型写法不一致 (10%) / device spellings
    for i in pick(0.10):
        v = df.iat[i, df.columns.get_loc("device_type")]
        if v in DEVICE_VARIANTS:
            df.iat[i, df.columns.get_loc("device_type")] = str(rng.choice(DEVICE_VARIANTS[v]))
    # (f) "是否听完"编码不一致 (2%) / completed flag coding
    for i in pick(0.02):
        v = df.iat[i, df.columns.get_loc("completed")]
        df.iat[i, df.columns.get_loc("completed")] = {"Y": "yes", "N": "no"}[v] if rng.random() < 0.5 else {"Y": "1", "N": "0"}[v]

    # (g) 过期邮箱:约 6% 的创作者,他们 25% 的行带着"旧邮箱" => 同一创作者两个邮箱(更新异常)
    #     stale e-mails: ~6% of creators have an old address on 25% of their rows
    stale_creators = rng.choice(df["creator_id"].unique(), size=max(1, int(df["creator_id"].nunique() * 0.06)), replace=False)
    for cid in stale_creators:
        idx = df.index[df["creator_id"] == cid]
        for i in rng.choice(idx, size=max(1, int(len(idx) * 0.25)), replace=False):
            local = df.at[i, "creator_email"].split("@")[0]
            df.at[i, "creator_email"] = f"{local}@oldmail-studio.com"
    #     同理:约 3% 的听众换过邮箱域名,35% 的行带着旧邮箱 / ~3% of listeners changed e-mail provider
    stale_listeners = rng.choice(df["listener_id"].unique(), size=int(df["listener_id"].nunique() * 0.03), replace=False)
    for lid in stale_listeners:
        idx = df.index[df["listener_id"] == lid]
        for i in rng.choice(idx, size=max(1, int(len(idx) * 0.35)), replace=False):
            local = df.at[i, "listener_email"].split("@")[0]
            df.at[i, "listener_email"] = f"{local}@legacy-mail.net"

    # (h) 空值:邮箱缺失 4%、城市缺失 6% / NULLs: missing e-mail 4%, missing city 6%
    df.loc[pick(0.04), "listener_email"] = None
    df.loc[pick(0.06), "listener_city"] = None
    return df


def add_duplicates(rng, df):
    """Append exact duplicate rows (e.g. logging retries), keep them next to the original.
    追加完全重复的行(如日志重试),并让它们紧挨着原行。"""
    dup_idx = rng.choice(len(df), size=int(len(df) * DUP_RATE / (1 - DUP_RATE)), replace=False)
    out = pd.concat([df, df.iloc[dup_idx]], ignore_index=True)
    return out.sort_values("session_started_at", kind="mergesort").reset_index(drop=True)


# ----------------------------------------------------------------------------
# 5) Main / 入口
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Generate the flat podcast sessions dataset.")
    ap.add_argument("--rows", type=int, default=50000, help="total rows incl. duplicates / 总行数(含重复行)")
    ap.add_argument("--out", default="podcast_sessions_flat.csv", help="output CSV path / 输出文件")
    args = ap.parse_args()

    rng = np.random.default_rng(SEED)
    Faker.seed(SEED)
    fake = Faker("en_US")

    n_dup = int(args.rows * DUP_RATE)
    n_base = args.rows - n_dup

    creators, shows, episodes = build_catalog(rng, fake)
    listeners = build_listeners(rng, fake)
    df = generate_sessions(rng, creators, shows, episodes, listeners, n_base)
    df = inject_problems(rng, df)
    df = add_duplicates(rng, df)

    df.to_csv(args.out, index=False, encoding="utf-8")          # 显式指定编码 / explicit encoding
    print(f"rows={len(df):,}  columns={df.shape[1]}  -> {args.out}")
    print(f"catalog: creators={len(creators)}, shows={len(shows)}, episodes={len(episodes)}, listeners={len(listeners)}")


if __name__ == "__main__":
    main()
