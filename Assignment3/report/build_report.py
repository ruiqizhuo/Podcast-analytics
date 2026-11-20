#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_report.py
===============
Assemble the Assignment 3 report (Word) from the project's own files: notes, SQL / Cypher files and the screenshots in docs/screenshots.
用项目自己的文件(笔记、SQL / Cypher 文件、docs/screenshots 里的截图)组装作业 3 的 Word 报告。

Screenshots that do not exist yet are drawn as yellow placeholder boxes with the exact thing to capture.
还没有的截图会画成黄色占位框,写明要截什么。
Usage / 用法:  python report/build_report.py      ->  report/Ruiqi_Zhuo_Assignment3_Report.docx
"""

import os
import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "docs", "screenshots")
OUT = os.path.join(ROOT, "report", "Ruiqi_Zhuo_Assignment3_Report.docx")
DARK_RED = RGBColor(0x80, 0x00, 0x00)
GREY = RGBColor(0x59, 0x59, 0x59)

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(sec, side, Inches(1))

SHOT_INDEX = []          # (number, caption, status) for the index table / 截图索引
counter = {"shot": 0, "fig": 0}


# ---------------------------------------------------------------- styles / 样式
def set_font(style, name, size=None, bold=None, italic=None, color=None):
    style.font.name = name
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(a), name)
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rfonts.get(qn(a)) is not None:
            del rfonts.attrib[qn(a)]
    if size:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if italic is not None:
        style.font.italic = italic
    if color is not None:
        style.font.color.rgb = color


set_font(doc.styles["Normal"], "Arial", 10)
doc.styles["Normal"].paragraph_format.space_after = Pt(6)
doc.styles["Normal"].paragraph_format.line_spacing = 1.1
for name, size, before in (("Title", 24, 0), ("Heading 1", 16, 18), ("Heading 2", 12.5, 12), ("Heading 3", 11, 8)):
    st = doc.styles[name]
    set_font(st, "Arial", size, True, False, DARK_RED)
    st.paragraph_format.space_before = Pt(before)
    st.paragraph_format.space_after = Pt(6)
    st.paragraph_format.keep_with_next = True
for name in ("List Bullet", "List Number"):
    set_font(doc.styles[name], "Arial", 10)


# ---------------------------------------------------------------- helpers / 工具函数
def add_runs(p, text, size=None, color=None, italic=None):
    """Add text with **bold** and `code` inline markup. / 支持 **粗体** 和 `代码` 行内标记。"""
    for part in re.split(r"(\*\*.+?\*\*|`.+?`)", text):
        if not part:
            continue
        if part.startswith("**"):
            r = p.add_run(part[2:-2]); r.bold = True
        elif part.startswith("`"):
            r = p.add_run(part[1:-1]); r.font.name = "Courier New"
            r._element.rPr.rFonts.set(qn("w:eastAsia"), "Courier New")
            r.font.size = Pt((size or 10) - 1)
        else:
            r = p.add_run(part)
        if size and not part.startswith("`"):
            r.font.size = Pt(size)
        if color is not None:
            r.font.color.rgb = color
        if italic:
            r.italic = True
    return p


def H(text, level=1):
    return doc.add_heading(text, level=level)


def P(text, **kw):
    return add_runs(doc.add_paragraph(), text, **kw)


def B(items):
    for t in items:
        add_runs(doc.add_paragraph(style="List Bullet"), t)


def shade(cell, hexcolor):
    tcpr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hexcolor)
    tcpr.append(shd)


def T(rows, widths, header=True, size=8.5):
    """Table with a dark-red header row; widths in inches. / 深红表头的表格,宽度单位为英寸。"""
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.width = Inches(widths[j])
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.space_before = Pt(1)
            if header and i == 0:
                shade(c, "800000")
                add_runs(p, f"**{val}**", size=size, color=RGBColor(255, 255, 255))
            else:
                add_runs(p, str(val), size=size)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def CODE(text, size=7.5):
    """Monospace block with light grey shading. / 灰底等宽代码块。"""
    for line in text.rstrip().splitlines():
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.left_indent = Inches(0.1)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run(line if line else " ")
        r.font.name = "Courier New"; r.font.size = Pt(size)
        r._element.rPr.rFonts.set(qn("w:eastAsia"), "Courier New")
        ppr = p._element.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), "F2F2F2")
        ppr.append(shd)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def caption(text, kind="shot"):
    counter[kind] += 1
    label = f"Screenshot {counter['shot']}." if kind == "shot" else f"Figure {counter['fig']}."
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"{label} {text}".replace("`", ""))
    r.italic = True; r.font.size = Pt(8.5); r.font.color.rgb = GREY
    return label


def SHOT(filename, text, width=6.3):
    """Insert an existing screenshot with a numbered caption. / 插入已有截图并编号。"""
    path = os.path.join(SHOTS, filename)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(path, width=Inches(width))
    lab = caption(text)
    SHOT_INDEX.append((lab, text, "inserted"))


def FIG(filename, text, width=6.5):
    path = os.path.join(SHOTS, filename)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(path, width=Inches(width))
    caption(text, "fig")


def PLACEHOLDER(text, what):
    """Yellow box for a screenshot that still has to be taken. / 还没截的截图:黄色占位框。"""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.cell(0, 0); c.width = Inches(6.3); shade(c, "FFF2CC")
    add_runs(c.paragraphs[0], f"**[Screenshot to insert]** {what}", size=9)
    lab = caption(text)
    SHOT_INDEX.append((lab, text, "TO TAKE: " + what))


def parse_queries(path, marker):
    """Return [(id, title, code)] from a file with '<comment> @ID | title' markers (comment-only lines removed).
    从带标记的文件里取出查询(去掉纯注释行)。"""
    text = open(path, encoding="utf-8").read()
    rx = re.compile(r"^(?://|--) @(" + marker + r")\s*\|\s*(.*)$", re.M)
    ms = list(rx.finditer(text))
    out = []
    for i, m in enumerate(ms):
        body = text[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(text)]
        lines = [l for l in body.splitlines() if not l.strip().startswith(("//", "--"))]
        out.append((m.group(1), m.group(2), "\n".join(lines).strip()))
    return out


Q_SQL = {q[0]: q for q in parse_queries(os.path.join(ROOT, "sql", "02_analytical_queries.sql"), r"Q\d+")}
Q_OPT = {q[0]: q for q in parse_queries(os.path.join(ROOT, "sql", "03_q5_optimizations.sql"), r"Q\d+[A-Z]?")}
R_SQL = {q[0]: q for q in parse_queries(os.path.join(ROOT, "sql", "04_part4a_queries.sql"), r"R\d+")}
N_CY = {q[0]: q for q in parse_queries(os.path.join(ROOT, "cypher", "01_queries.cypher"), r"N\d+")}
SETUP_B = open(os.path.join(ROOT, "sql", "03a_setup_agg_table.sql"), encoding="utf-8").read()


def footer_page_numbers():
    p = sec.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Ruiqi Zhuo  |  Cloud Native Data Engineering  |  Assignment 3  |  page ")
    r.font.size = Pt(8); r.font.color.rgb = GREY
    for kind, txt in (("begin", None), (None, "PAGE"), ("end", None)):
        run = p.add_run(); run.font.size = Pt(8); run.font.color.rgb = GREY
        if kind:
            fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), kind); run._element.append(fc)
        else:
            it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = txt; run._element.append(it)


footer_page_numbers()

# ================================================================= TITLE / 标题
doc.add_paragraph("Podcast Hosting Platform: Live API Pipeline, Star-Schema Warehouse and Graph Database", style="Title")
P("**Cloud Native Data Engineering, Assignment 3**  |  Ruiqi Zhuo  |  University of Chicago, MS in Applied Data Science  |  November 2026")
P("Domain (shared with Assignments 1 and 2): podcast hosting with creator-side subscription and retention analytics. "
  "Warehouse: Snowflake. NoSQL: Neo4j Aura Free. All numbers in this report come from runs on the project data; "
  "where something was assumed or not verified, the text says so (see also Section 7, Limitations).")

H("1. Overview", 1)
T([["Layer / part", "What was built", "Main files"],
   ["Part 1 - Pipeline", "Live ingestion from two public Apple endpoints, 6 quality checks, Bronze / Silver / Gold (3 Gold tables), PII masking", "pipeline/01_ingest_api.py, 02_silver.py, 03_gold.py"],
   ["Part 2 - Warehouse", "Star schema (2 facts, 5 dimensions, SCD2 on creator plan), loaded into Snowflake, 5 analytical queries, Q5 optimization", "pipeline/04_star_schema.py, 05_load_snowflake.py, 06_run_queries.py; sql/"],
   ["Part 3 - NoSQL", "Neo4j Aura Free property graph (6 node labels, 7 relationship types), 3 Cypher queries", "pipeline/07_load_neo4j.py, 08_run_cypher.py; cypher/"],
   ["Part 4 - Showcase", "3 warehouse queries, 3 graph queries, reflection on how the two stores complement each other", "sql/04_part4a_queries.sql; cypher/"],
   ["Part 5 - Judgment", "Production decision under a $150/month AWS budget", "Section 6"]],
  [1.3, 3.3, 1.9])
P("**Code repository (public):** https://github.com/ruiqizhuo/Podcast-analytics")
P("Deliverables: this report; the pipeline and masking code (`pipeline/`); the warehouse script (`sql/warehouse_script.sql`, DDL + loads + queries + optimization); "
  "the Neo4j script (`cypher/neo4j_script.cypher`, constraints + load statements + all six queries). Credentials are read from environment variables only "
  "(`SNOWFLAKE_*`, `NEO4J_*`, `PII_SALT`) and appear in no file or screenshot.")

# ================================================================= PART 1
H("2. Part 1 - Live API pipeline and masking", 1)
H("2.1 Live API ingestion", 2)
P("**Sources.** Two public Apple endpoints, no API key: (1) the RSS top-podcasts chart "
  "(`rss.marketingtools.apple.com/api/v2/{country}/podcasts/top/100/podcasts.json`), which says who is on the chart and at what rank; "
  "(2) the iTunes Lookup API (`itunes.apple.com/lookup?id=...&entity=podcast`), which returns about 30 fields per podcast (e.g. `feedUrl`, `trackCount`, `releaseDate`, `primaryGenreName`).")
P("**Why two steps instead of offset paging.** The iTunes search endpoint ignores `offset` (tested: offset 0, 50 and 100 with limit 50 returned the same 50 rows). "
  "The pipeline therefore (a) iterates over 8 country charts and (b) cuts the id list into pages of 100 for the lookup call and loops until every page is done.")
T([["Result of the live run (2026-11-17 UTC)", "Value"],
   ["Country charts pulled (us, gb, ca, au, de, fr, jp, br)", "8 charts = 800 chart rows -> 667 unique podcast ids"],
   ["Lookup pages", "7 (6 x 100 + 67 ids) -> **663 records** (4 ids returned nothing); required minimum 500"],
   ["HTTP calls", "18 calls, 15 succeeded without retry, 3 retries, 0 permanent failures"],
   ["Retries", "3 real `ReadTimeout`s (charts ca and br) recovered with exponential backoff (2.1 s, 4.6 s, 2.4 s)"]],
  [3.0, 3.5])
P("**Rate limiting and error handling.** At least 3 seconds between any two calls (we believe iTunes allows about 20 calls per minute; this was not verified in Apple's documentation). "
  "Retry on 403 / 429 / 5xx / timeouts: wait for `Retry-After` if present, otherwise 2, 4, 8, 16 s plus jitter. Non-JSON or empty 200 responses, missing keys, empty lists and "
  "non-retryable 4xx are handled without crashing and logged. No HTTP 429 occurred, so the `Retry-After` branch was written but **not exercised**.")
SHOT("s01_ingest_log.png", "Log of the ingestion run (saved log file `logs/ingest_20261117T042638Z.log`): chart pulls, three retries, seven lookup pages, 663 records and the quality-check table. "
     "Log times are local time; the file name uses UTC.")
H("2.2 Quality checks", 2)
T([["Check", "Type", "Passed", "Failed"],
   ["chk_id_not_null", "null", "663", "0"],
   ["chk_id_unique", "duplicate", "663", "0"],
   ["chk_trackcount_range (integer, 0-20,000; the upper bound is our assumption)", "range", "663", "0"],
   ["chk_release_date_valid (parses and is not in the future)", "format", "639", "24"],
   ["chk_genre_not_null", "null", "663", "0"],
   ["chk_feed_url_format (starts with http/https)", "format", "644", "19"],
   ["**All checks (row-level)**", "", "**622**", "**41**"]],
  [3.9, 0.9, 0.85, 0.85])
P("The 41 failing rows were inspected: the 24 date failures are real podcasts whose latest episode is **scheduled in the future** (e.g. 2026-11-23), not bad data; "
  "the 19 URL failures have **no feedUrl**. Decision made by the student: rows without `feedUrl` are quarantined, rows with a future date are kept and flagged "
  "`is_scheduled_future` (this relaxes check 4 for Silver).")

H("2.3 Bronze, Silver, Gold", 2)
P("**Bronze** keeps the raw data untouched. API: one JSON line per response with audit fields `source_name`, `ingested_at`, request URL/parameters and HTTP status. "
  "Assignment 2: the raw flat table (50,000 rows x 26 columns, regenerated with seed 42); `build_normalization.py` rebuilds the 11 Assignment 2 tables from it "
  "and matches the Assignment 2 CSVs exactly (compared as text, row order ignored; this shows the rebuild equals Assignment 2, not that Assignment 2's cleaning rules are right). "
  "The raw flat table is synthetic but contains unmasked names and e-mails, so it is **not uploaded** to Snowflake; only the masked Silver data is.")
T([["Silver step (02_silver.py)", "Result"],
   ["API rows in / quarantined (no `feedUrl`) / kept", "663 / 19 (reason `chk_feed_url_format`) / 644, of which 22 are flagged `is_scheduled_future`"],
   ["Mapped to one of the 8 Assignment 2 top-level categories", "474 of 644; 170 are `Unmapped` (e.g. Sports, Society & Culture)"],
   ["Assignment 2 raw rows", "50,000 -> 500 exact duplicates quarantined -> 49,500 session rows"],
   ["PII leak check / session foreign keys", "PASS / PASS"]],
  [3.0, 3.5])
P("Apple genres are linked to the Assignment 2 categories through a hand-made table (`pipeline/seed/genre_to_a2_top_category.csv`, 75 genres; a `basis` column records whether a row is a same-name match, "
  "a child-to-top-level match, an Apple parent genre from the API's own `genres` list, or a judgment call). It is a manual judgment, not a validated taxonomy.")
P("**Gold** (`03_gold.py`; the same logic is also implemented as Snowflake views, which the loader compares with the pandas output: maximum absolute difference 0.000 for all three). Three tables; two of them combine Assignment 2 records with the API data, as the assignment asks:")
B(["`gold_category_overview`: one row per top-level category plus `Unmapped`: Assignment 2 shows, sessions, listening hours and share, completion rate, next to API charted podcasts and their share. "
   "Sanity check against Assignment 2 (Q1): True Crime 4,873.9 h / 23.7% / 11,639 sessions and Health & Fitness 7.6% match. True Crime has the largest listening share (23.7%) but only 10.7% of charted podcasts; "
   "News has 21.0% of charted podcasts but 14.5% of listening. **Not causal**: the listening is synthetic, the charts are real, and 26.4% of charted podcasts are `Unmapped`.",
   "`gold_plan_retention` (Assignment 2 data only, kept as a third table): 30-day subscription retention by creator plan (the plan the creator has **today**; R3 later shows the plan at subscription time). Definition fixed before the run: retained = at least one session on that show in the 30 days after `subscribed_on`; "
   "only subscriptions with `subscribed_on <= 2026-08-31` are counted (9,990 of 11,052). We restricted the analysis to subscriptions through August 31 (complete months); this cutoff excluded 1,062 subscriptions, including 39 from September 1 that also had a complete 30-day observation window (the data runs to 2026-09-30). Result: Free 19.8%, Standard 19.9%, Pro 22.4%, all 20.5%. "
   "The differences are small and no significance test was run, so no conclusion about plan tiers should be drawn.",
   "`gold_category_retention` (added after review; combines Assignment 2 with the API): per top-level category, A2 30-day retention next to API chart coverage (charted podcasts, share of the chart, average chart rank). "
   "Each side is aggregated on its own first and joined only on the category, so no A2 record is counted twice (the 11,052 subscriptions and 9,990 observable subscriptions of the categories add up exactly to the totals above). "
   "In the local run, True Crime has the highest 30-day retention (24.5%) but is only 4th by chart share (10.7%); News has the largest chart share (21.0%) but ranks 5th by retention (19.1%); Comedy is 2nd by chart share (18.5%) and 7th by retention (17.7%). "
   "The 170 charted podcasts that are `Unmapped` (26.4% of the chart) have no A2 side. Differences between categories are small, no significance test was run, and the A2 behaviour is synthetic, so this shows how the two sources can be put side by side, not why."])
H("2.4 PII masking", 2)
T([["Item", "Treatment"],
   ["Identified PII", "`listener_name`, `listener_email`, `listener_city`, `creator_name`, `creator_email`, guest names"],
   ["Technique", "HMAC-SHA256 (a salted hash; the secret salt is the HMAC key), first 16 hex characters kept. The same input gives the same token, so JOIN and DISTINCT still work."],
   ["E-mail / names / city", "E-mail becomes `<token>@<domain>` (domain kept to analyse providers); names become `<token>`; the city column is dropped (country kept)."],
   ["Salt", "Read from the environment variable `PII_SALT` only, never stored. It must stay fixed for a whole build. The first run used a throwaway salt; the steps after it were re-run by the student with their own salt."],
   ["Listener key", "Silver replaces the integer `listener_id` with `listener_key` = HMAC-SHA256(\"listener:<id>\") (16 hex chars) in `listener`, `subscription` and `listening_session` (as Assignment 1 planned). "
                    "Checks: unique across 5,534 listeners, no integer `listener_id` left, every session/subscription key exists in `listener` (all PASS)."],
   ["Not masked", "The API's `artistName` (a public publisher or brand name); `creator_id`, `show_id`, `episode_id` stay integers (business entities, not listeners)."],
   ["What this is not", "This is **pseudonymization, not anonymization**: whoever holds the salt can re-link the data. The risk of two different inputs sharing a 16-hex token beyond this run was not measured."]],
  [1.4, 5.1])

# ================================================================= PART 2
H("3. Part 2 - Star schema and Snowflake warehouse", 1)
H("3.1 Design", 2)
P("Two fact tables share conformed dimensions (a \"fact constellation\": one business process per fact table). Every dimension has a surrogate key (`*_sk`, numbered by the build script) and keeps its business key as a column. `fact_listening_session` is the main fact table (all listening analysis); `fact_subscription` is the supplementary one (subscription and retention analysis).")
T([["Table", "Grain / content", "Rows"],
   ["fact_listening_session", "One listening session. Measures `listened_seconds`, `completed`; degenerate `session_id`, `device_type`", "49,500"],
   ["fact_subscription", "One listener's subscription to one show. Measure `subscription_count` (= 1)", "11,052"],
   ["dim_date", "One day, 2025-06-03 to 2026-09-30", "485"],
   ["dim_listener", "One listener, keyed by the masked `listener_key`", "5,534"],
   ["dim_episode", "One episode", "3,181"],
   ["dim_show", "One show, category flattened to top level", "244"],
   ["dim_creator (SCD Type 2)", "One row per creator per plan version", "204 (150 creators)"]],
  [1.8, 3.8, 0.9])
FIG("fig_star_schema.png", "Star schema (fact constellation). Both fact tables point to the creator version valid on the event date.")
H("3.2 SCD Type 2 on creator plan, with proof", 2)
P("`dim_creator` keeps one row per creator and plan version with `valid_from`, `valid_to` and `is_current` (`valid_to` = 9999-12-31 for the current row). "
  "Each fact row stores the `creator_sk` of the version valid **on the event date**, found by a point-in-time lookup (`merge_asof`). "
  "Assignment 2 only holds the current plan, so **the history is simulated** (fixed seed 42). The rules are our assumptions, not sourced facts: about 30% of creators change plan, 1-2 times; "
  "the first change comes at least 30 days after the data start (2025-06-03, used as every creator's onboarding date because Assignment 2 has none); at least 30 days between changes (about one billing cycle); "
  "upgrades intended at 80% with no two downgrades in a row; the last plan equals the Assignment 2 plan. A first draft used 60 days; it was changed to 30 after the student judged 60 too long (neither value has a real-world source).")
P("**Result:** 40 of 150 creators changed plan, 54 changes in total (26 creators with 2 versions, 14 with 3): **34 upgrades and 20 downgrades (63% / 37%)**, not the intended 80/20, because the rules work backwards from the "
  "Assignment 2 plan and a creator who is on Free today can only have a downgrade history. Sessions by plan at event time: Standard 21,290, Free 16,878, Pro 11,332.")
P("**Proof, active and expired rows in Snowflake.** The query below returns the version rows of creators 5 and 26 from `STAR.DIM_CREATOR`:")
CODE("SELECT creator_sk, creator_id, plan_tier, valid_from, valid_to, is_current\nFROM STAR.DIM_CREATOR\nWHERE creator_id IN (5, 26)\nORDER BY creator_id, valid_from;")
SHOT("scd2_proof_snowflake.png", "SCD2 proof in Snowflake: expired (is_current FALSE) and active (TRUE, valid_to 9999-12-31) versions of creators 5 and 26 in STAR.DIM_CREATOR.", 6.3)
P("Expected result, taken from the local dimension file that was loaded (`data/star/dim_creator.csv`; the Snowflake row count of 204 matches the file):")
T([["creator_sk", "creator_id", "plan_tier", "valid_from", "valid_to", "is_current"],
   ["5", "5", "Free", "2025-06-03", "2026-05-23", "False  (expired)"],
   ["6", "5", "Standard", "2026-05-24", "9999-12-31", "True  (active)"],
   ["30", "26", "Standard", "2025-06-03", "2025-10-13", "False  (expired)"],
   ["31", "26", "Free", "2025-10-14", "2025-11-28", "False  (expired)"],
   ["32", "26", "Standard", "2025-11-29", "9999-12-31", "True  (active)"]],
  [0.9, 0.9, 1.0, 1.2, 1.2, 1.3])
P("Query Q3 (below) shows the effect on results: sessions grouped by the plan at the time versus the plan today. "
  "Integrity checks on the build (all PASS): both fact tables keep every Silver row; no missing foreign keys; `session_id` unique; exactly one current version per creator; "
  "current plan equals the Assignment 2 plan; versions have no gaps or overlaps; all fact dates exist in `dim_date`.")
H("3.3 Loading into Snowflake", 2)
P("`sql/01_ddl_and_views.sql` creates the warehouse `PODCAST_WH` (X-Small, auto-suspend 60 s), the database `PODCAST_DW` with schemas BRONZE / SILVER / GOLD / STAR, all tables (primary and foreign keys are informational in Snowflake, not enforced) "
  "and the three Gold views. `pipeline/05_load_snowflake.py` uploads each file (PUT to an internal stage) and loads it (COPY INTO), then checks that every row count equals the local file and that the Gold views equal the pandas Gold files; "
  "all checks passed.")
SHOT("s02_snowflake_tables.png", "Snowflake: tables in the BRONZE, SILVER and STAR schemas with row counts (22 tables; the Gold objects are views and are not listed here). "
     "STAR.AGG_SUBSCRIPTION_RETENTION is the pre-computed table of optimization B.")
H("3.4 Five analytical queries", 2)
P("Q2 and Q3 use the plan **at the time of the event** (SCD2); Q1, Q4 and Q5 do not involve plans. Full SQL is in Appendix A; the result cache was switched off for every run (`USE_CACHED_RESULT = FALSE`). "
  "Timings below are medians of 5 runs from the logged metrics file (total elapsed / execution, milliseconds); an earlier console summary showed slightly different medians for Q1-Q4 (373/32, 222/29, 223/29, 220/26) and the difference was not traced, so the logged file is used.")
T([["#", "Business question", "Technique", "Median ms (total / execution)"],
   ["Q1", "Listening hours by top-level category and category, with subtotals and a grand total", "ROLLUP", "409 / 35"],
   ["Q2", "Completion rate by creator plan (at the time) and device, with per-plan, per-device and overall rows", "GROUPING SETS", "262 / 29"],
   ["Q3", "Sessions by the plan at the time versus the creator's current plan (creators whose plan changed)", "SCD2 self-join", "282 / 30"],
   ["Q4", "Top 3 shows per top-level category by listening hours (RANK, so ties would add rows)", "Window function (RANK)", "224 / 27"],
   ["Q5", "30-day retention per show: the 5 highest and 5 lowest (RANK, so ties could add rows; 10 rows came back) among shows with at least 30 observable subscriptions, with 95% Wilson intervals", "Two fact tables via shared dimensions, CTEs, window", "783 / 79 (heaviest)"]],
  [0.4, 3.4, 1.5, 1.2])
SHOT("q1_rollup.png", "Q1 (ROLLUP): SQL and result in Snowsight, 36 rows (first 24 visible).", 6.5)
SHOT("q2_grouping_sets.png", "Q2 (GROUPING SETS): 20 rows; the last ORDER BY line is cut off in the editor view (full SQL in Appendix A).", 6.5)
SHOT("q3_scd2.png", "Q3 (SCD2): sessions by the plan at the time versus the creator's current plan, 9 rows; this is also the SCD2 demonstration in the warehouse.", 6.5)
SHOT("q4_window.png", "Q4 (window function RANK): top 3 shows per top-level category, 24 rows (first 14 visible).", 6.5)
SHOT("q5_retention.png", "Q5 (30-day retention per show, Wilson 95% interval): 10 rows; the editor shows only the first 29 lines of the query (full SQL in Appendix A).", 6.5)
P("**Q5 reading.** Retention is defined as at least one session on the show in the 30 days after `subscribed_on` (day 0 in, day 30 out); only subscriptions on or before 2026-08-31 are analysed (a deliberate month-end cutoff, see Section 2.3; the 39 subscriptions of 1 September would also have a full window). "
  "Small samples make a show's rate noisy, so each show gets a 95% Wilson interval and a flag when the overall rate lies outside it. With about 80 shows tested, a few flags are expected by chance. "
  "The per-show differences may be an artifact of how the synthetic sessions and subscriptions were generated (not verified). "
  "In the run shown, the overall rate is 20.5% and 7 of the 10 listed shows are flagged as differing from it (highest: 40.0% for The Balance Habits, with 40 subscriptions; lowest: 3.0% for Founders Playbook, with 33), "
  "but with about 80 shows tested some flags are expected by chance, so the list means \"worth a look\", not proof.")

H("3.5 Optimizing the most expensive query (Q5)", 2)
P("Q5 was the most expensive query (median 783 ms total, 79 ms execution in the first batch of runs, see the table below). Three changes were tried one at a time; **all four versions returned the identical result** (same order-independent result fingerprint `3b2306acc0`). "
  "Each version ran 5 times.")
T([["Version", "Total elapsed, median (range) ms", "Execution, median (range) ms", "Bytes scanned"],
   ["Baseline", "888 (542-1,244)", "91 (80-276)", "664,576"],
   ["A. Rewrite: EXISTS semi-join, sessions de-duplicated per day", "595 (347-897)", "53 (52-68)", "664,576"],
   ["B. Pre-computed table `STAR.AGG_SUBSCRIPTION_RETENTION`", "327 (184-384)", "41 (37-42)", "59,392 (-91%)"],
   ["C. Clustering key (show_sk, date_key) on both fact tables", "869 (458-1,178)", "82 (76-248)", "664,576"]],
  [2.6, 1.5, 1.4, 1.0])
P("**Which numbers are which.** The same Q5 was measured in several batches; they are not meant to be identical.")
T([["Number", "What it is", "Source"],
   ["783 ms total / 79 ms execution", "Median of 5 runs, first batch (label `baseline`), used in the query table above", "logs/query_metrics.csv"],
   ["888 / 91", "Median of 5 runs, re-run in the optimization session (label `baseline2`); the comparison basis for A, B and C", "logs/query_metrics.csv"],
   ["888 / 92 / 664,576 bytes", "One run of that batch (run 5, query id ...02631a) as recorded in Query History", "Query History via the connector"],
   ["137 ms / 0.27 MB", "The same query id as shown by Query Profile (next screenshots); not reconciled with the line above", "Snowsight Query Profile"],
   ["B: 327 / 41 (first 5 runs), 377 / 44 (second 5 runs), 332 / 43 (all 10)", "Pre-computed table; the table below uses the first 5 runs", "logs/query_metrics.csv"]],
  [2.3, 3.0, 1.2])
B(["**Reading.** Execution time is the stable number. Total elapsed time is dominated by compilation time, which varied from 143 to 1,096 ms between identical runs, so differences in total time are noisy. "
   "A cut execution time by about 42% and B by about 55%; B cut the bytes scanned by 91% according to Query History (about 78% if the baseline's Query Profile figure of 0.27 MB is used instead).",
   "**C changed nothing** (82 ms against 91 ms is inside the noise). That is expected: the tables hold only one or two micro-partitions, so there is nothing to prune. The clustering key was dropped again after the test; "
   "automatic background re-clustering costs credits, which was not quantified.",
   "**B moves the work from query time to load time.** Building the table took 1.3 s once, and it must be rebuilt when new sessions or subscriptions arrive. A needs no schema change and is the alternative when a stored table is not wanted.",
   "**Limits.** The absolute gains are tens of milliseconds because the data is tiny; this says nothing certain about production scale. The partition counts come from `GET_QUERY_OPERATOR_STATS` and how that tool counts was not verified, so bytes scanned is the clearer indicator. "
   "**Cross-check with the Query Profile screenshots (not reconciled).** The profile of the baseline shows 0.27 MB scanned and 137 ms execution, whereas the query-history figures used in the table are 664,576 bytes and 92 ms; for B the profile (0.06 MB, 50 ms) is close to the history (59,392 bytes, 42 ms). We did not find why the baseline numbers differ between the two views, so the exact size of the reduction in bytes scanned (-91% from history; about -78% if the profile figure is used) should be read as roughly 80-90%, and the direction (B scans far less than the baseline) is what the evidence supports. "
   "The first batch of five runs per version is used above; a second batch of five B runs (median execution 44 ms, total 377 ms) gave the same picture. Metrics are in `logs/query_metrics.csv` (one row per run with its query id)."])
SHOT("profile_baseline.png", "Query Profile of the baseline Q5 (query id 01c87f5f-0209-e2c4-0013-311a0002631a), before optimization: 5 of 5 partitions scanned, 0.27 MB scanned, execution 137 ms in the profile (the query-history figure in the table above is 92 ms, see the note below).", 6.2)
SHOT("profile_b.png", "Query Profile of optimized version B (query id 01c87f60-0209-e2d8-0013-311a000280be), after optimization: 0.06 MB scanned, execution 50 ms in the profile (query history: 42 ms).", 6.2)

# ================================================================= PART 3
H("4. Part 3 - NoSQL: Neo4j Aura Free", 1)
H("4.1 Why a graph database", 2)
P("The part of this domain that is hardest to express in the star schema is **relationships that run through several entities**: listener -> show <- listener -> show (co-subscription); "
  "guest -> episode -> show <- creator (which creators a guest connects); creator -> show <- listener -> show <- creator (audience overlap). In SQL each extra hop is another self-join; "
  "in Cypher it is one more segment of the pattern. DynamoDB (access by key, no ad-hoc joins) and MongoDB (nested documents) were the other options; the student chose Neo4j after a comparison. "
  "Caveat: every query below can also be written in SQL on the warehouse and **no graph-versus-SQL timing was run**, so the argument is about expressiveness, not speed.")
H("4.2 Graph model", 2)
T([["Element", "Source", "Count", "Key properties"],
   ["(:Listener)", "silver_listener", "5,534", "listener_key (masked), country_code"],
   ["(:Show)", "silver_podcast_show", "244", "show_id, title"],
   ["(:Creator)", "silver_creator", "150", "creator_id, plan_tier"],
   ["(:Category)", "silver_category", "28", "category_id, name"],
   ["(:Episode)", "silver_episode", "3,181", "episode_id, title, duration_sec, published"],
   ["(:Guest)", "silver_guest", "299", "guest_id (name not loaded)"],
   ["[:PUBLISHES] Creator->Show; [:IN_CATEGORY] Show->Category; [:SUBCATEGORY_OF] Category->Category", "", "244; 244; 20", ""],
   ["[:OF_SHOW] Episode->Show; [:APPEARED_ON] Guest->Episode", "", "3,181; 2,853", ""],
   ["[:SUBSCRIBED_TO] Listener->Show", "silver_subscription", "11,052", "on (date)"],
   ["[:LISTENED_TO] Listener->Show", "silver_listening_session, summed", "26,084", "sessions, seconds, completed (49,500 sessions in total)"]],
  [2.6, 1.5, 0.9, 1.5])
P("Only masked data is loaded (no names or e-mails). `pipeline/07_load_neo4j.py` creates one uniqueness constraint per label and writes with MERGE, so a re-run does not duplicate anything; "
  "it then compares every node and relationship count with the CSV files (all PASS, including 49,500 sessions summed on LISTENED_TO). "
  "**Connection note:** the default `neo4j+s://` failed with \"self-signed certificate in certificate chain\" on this network (cause not identified; a VPN, proxy or antivirus doing TLS inspection is a guess), "
  "so the load used `neo4j+ssc://`, which is encrypted but **does not verify the server certificate**. This is a limitation, not a verified secure connection.")
SHOT("aura_console_masked.png", "Neo4j Aura console: AuraDB Free instance running (Google Cloud, europe-west1), 9,436 nodes (5% of the limit) and 43,678 relationships (11%). Instance id and URLs masked.", 6.0)
SHOT("neo4j_load_checks.png", "Output of `pipeline/07_load_neo4j.py`: node and relationship counts equal the CSV files; all checks passed.", 5.6)
SHOT("graph_creator_show_listener.png", "Neo4j Query: Creator -> Show <- Listener (27 nodes, 26 relationships). The 25-row limit returned subscribers of one show.", 5.6)
SHOT("graph_guest145.png", "Neo4j Query: the network of guest 145: Guest -> Episode -> Show <- Creator (56 nodes, 56 relationships, 4 labels).", 6.2)
H("4.3 Three Cypher queries (access patterns)", 2)
P("**N1 - Business question:** which shows do subscribers of the most-subscribed show also subscribe to? (2 hops)")
CODE(N_CY["N1"][2])
P("Result: base show The Verdict Tapes 31 (634 subscribers); its subscribers also subscribe most to Byte Unplugged (59), Scene Hour (52), The Midnight Files (47), Cold Docket 98 (38) and The Byte Report (32). "
  "Caveat: popular shows co-occur more simply because they are popular, so this is a \"what to recommend first\" list, not a measure of affinity.")
SHOT("n1.png", "Cypher N1 (co-subscription, 2 hops): code and result in Neo4j Query.", 6.0)
P("**N2 - Business question:** how many listeners subscribe to shows in 1, 2, 3, ... different top-level categories?")
CODE(N_CY["N2"][2])
P("Result (distinct top-level categories: listeners): 1: 1,993; 2: 1,729; 3: 918; 4: 282; 5: 77; 6: 13; 7: 1. These sum to 5,013, so 521 of the 5,534 listeners have no subscription (derived by subtraction, not queried separately).")
SHOT("n2.png", "Cypher N2 (cross-category listeners, variable-length path `*0..1` up the category tree).", 6.0)
P("**N3 - Business question:** which guests appeared on shows of two or more different creators? (3 hops)")
CODE(N_CY["N3"][2])
P("Result: guest 145 appeared on shows of 18 different creators, guests 228 and 241 on 17. Caveat: with 299 guests and 2,853 appearances (about 9.5 each), almost every guest bridges many creators; "
  "we suspect the synthetic data assigns guests to episodes at random (not verified), so this query shows the pattern, not a real-world finding.")
SHOT("n3.png", "Cypher N3 (guest bridges, 3 hops: Guest -> Episode -> Show <- Creator).", 6.0)

# ================================================================= PART 4
H("5. Part 4 - Query showcase and reflection", 1)
H("5.1 Relational warehouse queries (Snowflake)", 2)
R_Q = {
    "R1": ("How is total listening trending month to month, and how large is the change compared with the previous month?",
           "R1 turns 49,500 sessions into a 16-month trend. Sessions rise from 319 (Jun 2025) to about 4,600 a month (Dec 2025 - Mar 2026), then fall to 1,560 in Aug 2026 "
           "(listening hours -23.8% in May, -14.5% in Jun, -32.4% in Jul, -33.5% in Aug). June 2025 is a partial month (data starts 3 June), so the +438.4% in July is inflated; "
           "the decline is probably a feature of how the synthetic sessions were generated (cause not investigated), not a real churn signal.",
           "r1_monthly_trend.png", "R1 (monthly trend with month-over-month change and moving average); first 8 of 16 rows shown."),
    "R2": ("Which category-and-device combinations carry the most listening, and does completion differ between them?",
           "R2 builds every category x device combination with subtotals in one CUBE (45 rows). Completion rates sit in a narrow 40-44% band for the combinations visible in the screenshot, "
           "so there is no strong category or device effect in those rows (only part of the 45 rows is visible).",
           "r2_cube.png", "R2 (CUBE over top-level category and device); first 8 of 45 rows shown."),
    "R3": ("How many new subscriptions arrive each quarter, split by the creator's plan on the day of subscription, and what is the running total per plan?",
           "R3 uses the SCD2 dimension to attribute each subscription to the plan in force that day. By 2026 Q3 the running totals are Free 3,407 and Pro 2,592; Standard is 5,053 (computed from the local star files that were loaded, not read from the screenshot), "
           "and 3,407 + 2,592 + 5,053 = 11,052, the number of subscriptions in `fact_subscription`. The plan history is simulated.",
           "r3_scd2_running_total.png", "R3 (new subscriptions per quarter by plan at subscription time, with running total); first 8 of 18 rows shown."),
}
for rid in ("R1", "R2", "R3"):
    bq, res, img, cap = R_Q[rid]
    P(f"**{rid} - Business question:** {bq}")
    CODE(R_SQL[rid][2])
    P("Result: " + res)
    SHOT(img, cap, 6.3)
H("5.2 Graph queries (Neo4j)", 2)
N_Q = {
    "N4": ("How many distinct listeners could be reached through the guest who has appeared on the most creators' shows? (3 hops from the guest to a listener)",
           "Guest 145 appears on 18 shows (18 creators) and reaches 638 distinct subscribers.", "n4.png", "Cypher N4 (guest reach, 3 hops from the guest to a listener)."),
    "N5": ("Which pairs of creators share the most subscribers, as cross-promotion candidates? (4 hops)",
           "Top pairs (creator a, creator b: shared subscribers): (10, 110) 61; (99, 110) 53; (83, 110) 52; (10, 99) 38; (60, 110) 38. Creator 110 owns The Verdict Tapes 31, the most-subscribed show, "
           "so most of this reflects popularity, not necessarily similar audiences (interpretation, not tested).", "n5.png", "Cypher N5 (audience overlap between creators, 4 hops)."),
    "N6": ("For the listener with the most subscriptions, which shows, creators and listening history are directly connected to them?",
           "That listener has 8 subscriptions (1-3 sessions each). One show (The Verdict Tapes 31) was subscribed on 2026-09-17 but already has 2 sessions: in the synthetic data sessions can precede the subscription date (known caveat).",
           "n6.png", "Cypher N6 (one listener's neighbourhood)."),
}
for nid in ("N4", "N5", "N6"):
    bq, res, img, cap = N_Q[nid]
    P(f"**{nid} - Business question:** {bq}")
    CODE(N_CY[nid][2])
    P("Result: " + res)
    SHOT(img, cap, 6.0)
H("5.3 How the two stores complement each other", 2)
P("The two stores answer different kinds of question. The warehouse queries (R1-R3) are all aggregations over many rows along shared dimensions: R1 turns 49,500 sessions into a 16-month trend with a month-over-month change and a moving average, "
  "R2 builds every category-by-device combination with subtotals in one CUBE, and R3 uses the SCD2 creator dimension to attribute each subscription to the plan the creator had on that day, with a running total per plan. "
  "These rely on the conformed date dimension, on history kept in `dim_creator`, and on an engine that scans and groups columns, which is what a columnar warehouse is built for. "
  "A graph store would have to recompute all of it and could not answer \"which plan was the creator on at the time\" without the SCD2 rows.")
P("The Neo4j queries (N1-N6) are traversals: from a show to its subscribers to their other shows (N1), from a guest through episodes and shows to creators (N3, N4), and from one creator through shows and listeners to another creator (N5). "
  "Each is a pattern of 2-4 hops (a hop is one relationship) that reads like the question being asked; in SQL the same questions need a chain of self-joins on the subscription and episode-guest tables. N6 has a different shape: after finding the listener with the most subscriptions, it reads that listener's directly connected shows, creators and listening summaries. "
  "The answers also show the limits of what we ran: N1 and N5 are dominated by one very popular show, and N3 flags almost every guest as a bridge, "
  "probably because the synthetic data assigns guests at random (not verified). The graph makes these questions easy to ask, but the quality of the answer still depends on the data.")
P("Together they form a platform in which the warehouse is the system of record for history and reporting (SCD2 lookups, rollups, trends) and the graph is a serving or exploration layer for relationship questions such as who else is connected "
  "to a show, guest or creator. Both are loaded from the same masked Silver data, so identifiers match across them (the same `listener_key`, `show_id`, `creator_id`). What we did not do is run the same question on both stores and compare "
  "time: the evidence here is about expressiveness and fit, not speed.")

# ================================================================= PART 5
H("6. Part 5 - Production judgment ($150/month AWS budget)", 1)
P("I would keep Snowflake as the core platform and run Neo4j only as a small, free relationship layer, assuming the $150/month budget covers the whole platform (Snowflake is hosted on AWS but billed by Snowflake, and Aura runs on Google Cloud, so neither is automatically on the AWS bill). The warehouse queries (R1 trend, R2 CUBE, R3 SCD2 running totals) are the repeated workload. All the work in this project cost about $0.9 of the $400 trial, a sample too small to prove production cost, so I add assumptions. An X-Small warehouse uses 1 credit per hour (Snowflake's published rate, not checked here); at an assumed $3 per credit, one hour of compute a day is about 30 credits, or $90 a month, while two hours a day (about $180) would exceed the budget, so auto-suspend and a resource monitor are essential. Storage here is a few megabytes and negligible. Aura Free holds 9,436 nodes and 43,678 relationships at 5% and 11% of its limits, so it costs nothing today, but N1-N6 are exploratory queries and a second data copy must be kept in sync, so I would deprioritize it. I did not check paid prices.")
P("Word count: 196. The $3 per credit price and the hours per day are assumptions, not measurements; the 72-hour reporting lag of the Snowflake console means the $0.9 may be incomplete.", color=GREY, size=8.5)
SHOT("snowflake_cost_management_masked.png", "Snowflake Cost Management (Account Overview, this month): $0.9 spent, $399 of the $400 trial left, trial ends in 29 days (on 2026-11-18). User name masked.", 6.3)

# ================================================================= LIMITATIONS
H("7. Limitations, assumptions and what was not verified", 1)
B(["**SCD2 history is simulated.** The change rules (30%, 1-2 changes, 30-day minimum, 80% upgrades) are our assumptions with no real-world source; the 63/37 upgrade/downgrade split is a by-product of the rules.",
   "**Synthetic data.** Assignment 2 listening data is synthetic: sessions can precede `subscribed_on`; show-level retention differences and the guest \"bridges\" may be generator artifacts (not verified). Nothing here is a real-world finding.",
   "**Manual mappings and bounds.** The genre-to-category table is a manual judgment (170 charted podcasts stay `Unmapped`); the 20,000 upper bound of `chk_trackcount_range` is our assumption.",
   "**API behavior.** The iTunes limit of about 20 calls a minute was not verified; the `Retry-After` branch was never exercised (no HTTP 429 occurred).",
   "**Pseudonymization only.** HMAC tokens can be re-linked by whoever holds the salt; collision risk beyond this run was not measured.",
   "**Optimization.** The data is tiny, so absolute gains are tens of milliseconds and say nothing certain about production scale. Compilation time is noisy, so execution time and bytes scanned are the reliable measures. "
   "Partition counts come from a tool whose counting was not verified, and the baseline's bytes scanned differ between Query History and Query Profile (not reconciled). Clustering (C) showed no effect and its background cost was not quantified. The metrics file `logs/query_metrics.csv` was repaired once after the column layout changed between appends "
   "(the layout of the old rows was inferred from their field count), and the runner now writes fixed columns.",
   "**Neo4j.** The connection used `neo4j+ssc://` (encrypted, certificate not verified). The Aura limits (about 200,000 nodes and 400,000 relationships) are inferred from the percentages shown in the console, not read. "
   "No graph-versus-SQL timing was done.",
   "**Cost.** The Snowflake figure of $0.9 may lag by up to 72 hours; paid-tier prices of Snowflake and Aura were not checked, and the $3 per credit used in Part 5 is an assumption, so the $150 judgment is an estimate, not a measurement."])

# ================================================================= APPENDICES
H("Appendix A - SQL of the five analytical queries (Part 2)", 1)
for qid in ("Q1", "Q2", "Q3", "Q4", "Q5"):
    q = Q_SQL[qid]
    P(f"**{qid}** - {q[1]}")
    CODE(q[2], 7)
H("Appendix B - SQL of the Q5 optimization (Part 2)", 1)
P("**Version A** (rewrite) and **version B** (reads the pre-computed table) share the tail of Q5 from the CTE `overall` onward; the full text is in `sql/03_q5_optimizations.sql` and `sql/warehouse_script.sql`.")
for qid in ("Q5A", "Q5B"):
    q = Q_OPT[qid]
    P(f"**{qid}** - {q[1]}")
    CODE("\n".join(q[2].splitlines()[:24]) + ("\n  ... (shared tail of Q5, see sql/03_q5_optimizations.sql)" if len(q[2].splitlines()) > 24 else ""), 7)
P("**Setup of B** (`sql/03a_setup_agg_table.sql`, run once):")
CODE("\n".join(l for l in SETUP_B.splitlines() if not l.strip().startswith("--")), 7)
H("Appendix C - Screenshot index", 1)
T([["Number", "Caption", "Status"]] + [[a, b[:150] + ("..." if len(b) > 150 else ""), ("inserted" if c == "inserted" else "to be inserted")] for a, b, c in SHOT_INDEX],
  [0.9, 3.6, 2.0], size=8)
if any(x[2] != "inserted" for x in SHOT_INDEX):
    P("The yellow box(es) mark screenshots that are still to be inserted; crop any user name, account name or instance id first.", color=GREY, size=8.5)

doc.save(OUT)
print("saved", OUT, "| screenshots:", counter["shot"], "| placeholders:", sum(1 for s in SHOT_INDEX if s[2] != "inserted"))
