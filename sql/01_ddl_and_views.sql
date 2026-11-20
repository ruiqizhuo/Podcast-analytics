-- =====================================================================================
-- 01_ddl_and_views.sql
-- Assignment 3 - Snowflake warehouse: database, schemas, tables (Bronze/Silver/Star) and Gold views.
-- 作业 3 - Snowflake 数据仓库:数据库、Schema、表(Bronze/Silver/星型模型)和 Gold 视图。
--
-- Run by pipeline/05_load_snowflake.py (it also PUTs and COPYs the CSV files).
-- 由 pipeline/05_load_snowflake.py 执行(该脚本同时负责上传并 COPY CSV)。
-- Everything lives inside database PODCAST_DW; nothing outside it is touched.
-- 所有对象都在 PODCAST_DW 数据库内,不碰库外任何东西。
-- Tables/views use CREATE OR REPLACE so the script can be re-run; the database and warehouse use IF NOT EXISTS.
-- 表和视图用 CREATE OR REPLACE,方便重跑;数据库和仓库用 IF NOT EXISTS。
-- NOTE: PRIMARY/FOREIGN KEY constraints in Snowflake are informational only (NOT enforced);
--       integrity is checked by pipeline/04_star_schema.py and by queries.
-- 注意:Snowflake 的主键/外键约束只是说明性的(不强制执行),完整性由 04 脚本和查询来检查。
-- =====================================================================================

-- ---------- Warehouse (compute) and database / 计算仓库与数据库 ----------
-- XSMALL + auto-suspend after 60 s keeps trial credits low. / 最小规格 + 60 秒自动挂起,省试用额度。
CREATE WAREHOUSE IF NOT EXISTS PODCAST_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
USE WAREHOUSE PODCAST_WH;
CREATE DATABASE IF NOT EXISTS PODCAST_DW;
USE DATABASE PODCAST_DW;
CREATE SCHEMA IF NOT EXISTS BRONZE;
CREATE SCHEMA IF NOT EXISTS SILVER;
CREATE SCHEMA IF NOT EXISTS GOLD;
CREATE SCHEMA IF NOT EXISTS STAR;
CREATE SCHEMA IF NOT EXISTS STAGE;
CREATE STAGE IF NOT EXISTS STAGE.LOAD_STAGE;

-- ---------- BRONZE: raw API responses, one JSON document per response / 原始 API 响应 ----------
CREATE OR REPLACE TABLE BRONZE.API_RAW (
  source_name    VARCHAR,
  ingested_at    TIMESTAMP_TZ,
  request_url    VARCHAR,
  request_params VARIANT,
  http_status    NUMBER,
  raw_payload    VARIANT      -- untouched response body / 原样保存的响应体
);

-- ---------- SILVER: cleaned, masked, quarantined rows removed / 清洗、脱敏、隔离后的数据 ----------
CREATE OR REPLACE TABLE SILVER.CATEGORY (
  category_id NUMBER PRIMARY KEY, category_name VARCHAR, parent_category_id NUMBER);
CREATE OR REPLACE TABLE SILVER.COUNTRY (country_code VARCHAR PRIMARY KEY, country_name VARCHAR);
CREATE OR REPLACE TABLE SILVER.PLAN (plan_tier VARCHAR PRIMARY KEY, monthly_price_usd NUMBER(8,2));
CREATE OR REPLACE TABLE SILVER.CREATOR (
  creator_id NUMBER PRIMARY KEY, creator_name_hash VARCHAR, creator_email_masked VARCHAR, plan_tier VARCHAR);
CREATE OR REPLACE TABLE SILVER.PODCAST_SHOW (
  show_id NUMBER PRIMARY KEY, show_title VARCHAR, creator_id NUMBER, category_id NUMBER);
CREATE OR REPLACE TABLE SILVER.EPISODE (
  episode_id NUMBER PRIMARY KEY, show_id NUMBER, episode_title VARCHAR, episode_duration_sec NUMBER,
  episode_publish_date DATE);
CREATE OR REPLACE TABLE SILVER.GUEST (guest_id NUMBER PRIMARY KEY, guest_name_hash VARCHAR);
CREATE OR REPLACE TABLE SILVER.EPISODE_GUEST (episode_id NUMBER, guest_id NUMBER);
CREATE OR REPLACE TABLE SILVER.LISTENER (
  listener_key VARCHAR PRIMARY KEY, listener_name_hash VARCHAR, listener_email_masked VARCHAR, country_code VARCHAR);
CREATE OR REPLACE TABLE SILVER.SUBSCRIPTION (listener_key VARCHAR, show_id NUMBER, subscribed_on DATE);
CREATE OR REPLACE TABLE SILVER.LISTENING_SESSION (
  listener_key VARCHAR, session_id NUMBER PRIMARY KEY, episode_id NUMBER, session_started_at TIMESTAMP_NTZ,
  listened_seconds NUMBER, completed VARCHAR(1), device_type VARCHAR);
CREATE OR REPLACE TABLE SILVER.API_PODCAST (
  podcast_id NUMBER(18,0) PRIMARY KEY, podcast_name VARCHAR, artist_name VARCHAR, primary_genre VARCHAR,
  all_genres VARCHAR, track_count NUMBER, latest_release_at TIMESTAMP_NTZ, is_scheduled_future BOOLEAN,
  feed_url VARCHAR, store_country VARCHAR, content_rating VARCHAR, explicitness VARCHAR,
  ingested_at TIMESTAMP_TZ, source_name VARCHAR, a2_top_category VARCHAR);
CREATE OR REPLACE TABLE SILVER.API_CHART_RANK (podcast_id NUMBER(18,0), chart_country VARCHAR, chart_rank NUMBER);

-- ---------- STAR: star schema / 星型模型 ----------
CREATE OR REPLACE TABLE STAR.DIM_DATE (
  date_key NUMBER PRIMARY KEY, full_date DATE, year NUMBER, quarter NUMBER, month NUMBER, month_name VARCHAR,
  week_of_year NUMBER, day_of_week NUMBER, day_name VARCHAR, is_weekend BOOLEAN);
CREATE OR REPLACE TABLE STAR.DIM_LISTENER (
  listener_sk NUMBER PRIMARY KEY, listener_key VARCHAR, listener_name_hash VARCHAR,
  listener_email_masked VARCHAR, country_code VARCHAR);
CREATE OR REPLACE TABLE STAR.DIM_EPISODE (
  episode_sk NUMBER PRIMARY KEY, episode_id NUMBER, episode_title VARCHAR, episode_duration_sec NUMBER,
  episode_publish_date DATE);
CREATE OR REPLACE TABLE STAR.DIM_SHOW (
  show_sk NUMBER PRIMARY KEY, show_id NUMBER, show_title VARCHAR, category_id NUMBER, category_name VARCHAR,
  top_category_name VARCHAR, creator_id NUMBER);
-- SCD Type 2: one row per creator per plan version; valid_to = 9999-12-31 for the current version.
-- SCD Type 2:每个创作者每个套餐版本一行;当前版本的 valid_to 为 9999-12-31。
CREATE OR REPLACE TABLE STAR.DIM_CREATOR (
  creator_sk NUMBER PRIMARY KEY, creator_id NUMBER, creator_name_hash VARCHAR, creator_email_masked VARCHAR,
  plan_tier VARCHAR, valid_from DATE, valid_to DATE, is_current BOOLEAN);

CREATE OR REPLACE TABLE STAR.FACT_LISTENING_SESSION (      -- grain: one listening session / 粒度:一次收听会话
  date_key NUMBER REFERENCES STAR.DIM_DATE(date_key),
  listener_sk NUMBER REFERENCES STAR.DIM_LISTENER(listener_sk),
  episode_sk NUMBER REFERENCES STAR.DIM_EPISODE(episode_sk),
  show_sk NUMBER REFERENCES STAR.DIM_SHOW(show_sk),
  creator_sk NUMBER REFERENCES STAR.DIM_CREATOR(creator_sk),
  device_type VARCHAR, session_id NUMBER PRIMARY KEY, listened_seconds NUMBER, completed VARCHAR(1));
CREATE OR REPLACE TABLE STAR.FACT_SUBSCRIPTION (           -- grain: one subscription / 粒度:一条订阅
  date_key NUMBER REFERENCES STAR.DIM_DATE(date_key),
  listener_sk NUMBER REFERENCES STAR.DIM_LISTENER(listener_sk),
  show_sk NUMBER REFERENCES STAR.DIM_SHOW(show_sk),
  creator_sk NUMBER REFERENCES STAR.DIM_CREATOR(creator_sk),
  subscription_count NUMBER);

-- ---------- GOLD: curated views over Silver (same logic as pipeline/03_gold.py) ----------
-- Gold 视图:基于 Silver,逻辑与 03_gold.py 相同。
CREATE OR REPLACE VIEW GOLD.GOLD_CATEGORY_OVERVIEW AS
WITH top_of AS (            -- top-level category name of every category / 每个类目的一级类目名
  SELECT c.category_id, COALESCE(p.category_name, c.category_name) AS top_name
  FROM SILVER.CATEGORY c LEFT JOIN SILVER.CATEGORY p ON c.parent_category_id = p.category_id),
shows AS (
  SELECT t.top_name AS a2_top_category, COUNT(*) AS a2_shows
  FROM SILVER.PODCAST_SHOW s JOIN top_of t ON s.category_id = t.category_id GROUP BY t.top_name),
ses AS (
  SELECT t.top_name AS a2_top_category, COUNT(*) AS sessions,
         ROUND(SUM(l.listened_seconds) / 3600, 1) AS listening_hours,
         ROUND(100 * AVG(IFF(l.completed = 'Y', 1, 0)), 1) AS completion_rate_pct
  FROM SILVER.LISTENING_SESSION l
  JOIN SILVER.EPISODE e ON l.episode_id = e.episode_id
  JOIN SILVER.PODCAST_SHOW s ON e.show_id = s.show_id
  JOIN top_of t ON s.category_id = t.category_id GROUP BY t.top_name),
a2 AS (
  SELECT sh.a2_top_category, sh.a2_shows, ses.sessions, ses.listening_hours, ses.completion_rate_pct
  FROM shows sh LEFT JOIN ses ON sh.a2_top_category = ses.a2_top_category),
api AS (
  SELECT a2_top_category, COUNT(DISTINCT podcast_id) AS api_charted_podcasts,
         ROUND(AVG(track_count), 1) AS api_avg_episode_count,
         ROUND(100 * AVG(IFF(is_scheduled_future, 1, 0)), 1) AS api_scheduled_future_pct
  FROM SILVER.API_PODCAST GROUP BY a2_top_category)
SELECT COALESCE(a2.a2_top_category, api.a2_top_category) AS a2_top_category,
       a2.a2_shows, a2.sessions, a2.listening_hours,
       ROUND(100 * a2.listening_hours / SUM(a2.listening_hours) OVER (), 1) AS listening_hours_share_pct,
       a2.completion_rate_pct, api.api_charted_podcasts,
       ROUND(100 * api.api_charted_podcasts / SUM(api.api_charted_podcasts) OVER (), 1) AS api_chart_share_pct,
       api.api_avg_episode_count, api.api_scheduled_future_pct
FROM a2 FULL OUTER JOIN api ON a2.a2_top_category = api.a2_top_category;

-- Retention: a subscription is retained if the listener has >= 1 session on that show in the 30 days after
-- subscribed_on (day 0 included, day 30 excluded). Only subscriptions up to 2026-08-31 (complete months) are analysed: a deliberate
-- month-end cutoff (2026-09-01 would also have a full window, 39 subscriptions); later ones are counted in not_yet_observable.
-- 留存:订阅后 30 天内(含第 0 天,不含第 30 天)对该节目至少有 1 次会话。只分析 2026-08-31(月末)及以前的订阅(9 月 1 日的 39 条也有完整窗口,但有意不纳入),
-- 更晚的计入 not_yet_observable。
CREATE OR REPLACE VIEW GOLD.GOLD_PLAN_RETENTION AS
WITH sub AS (
  SELECT s.listener_key, s.show_id, s.subscribed_on, c.plan_tier
  FROM SILVER.SUBSCRIPTION s
  JOIN SILVER.PODCAST_SHOW ps ON s.show_id = ps.show_id
  JOIN SILVER.CREATOR c ON ps.creator_id = c.creator_id),
ses AS (
  SELECT l.listener_key, e.show_id, l.session_started_at::DATE AS session_date
  FROM SILVER.LISTENING_SESSION l JOIN SILVER.EPISODE e ON l.episode_id = e.episode_id),
flag AS (
  SELECT sub.listener_key, sub.show_id, sub.plan_tier,
         COALESCE(MAX(IFF(DATEDIFF('day', sub.subscribed_on, ses.session_date) BETWEEN 0 AND 29, 1, 0)), 0) AS retained,
         IFF(sub.subscribed_on <= DATE '2026-08-31', 1, 0) AS observable
  FROM sub LEFT JOIN ses ON sub.listener_key = ses.listener_key AND sub.show_id = ses.show_id
  GROUP BY sub.listener_key, sub.show_id, sub.plan_tier, sub.subscribed_on),
by_tier AS (
  SELECT plan_tier, COUNT(*) AS subscriptions, SUM(observable) AS observable_subscriptions,
         SUM(IFF(observable = 1, retained, 0)) AS retained_30d,
         COUNT(*) - SUM(observable) AS not_yet_observable
  FROM flag GROUP BY plan_tier)
SELECT plan_tier, subscriptions, observable_subscriptions, retained_30d,
       ROUND(100 * retained_30d / NULLIF(observable_subscriptions, 0), 1) AS retention_30d_pct, not_yet_observable
FROM by_tier
UNION ALL
SELECT 'ALL', SUM(subscriptions), SUM(observable_subscriptions), SUM(retained_30d),
       ROUND(100 * SUM(retained_30d) / NULLIF(SUM(observable_subscriptions), 0), 1), SUM(not_yet_observable)
FROM by_tier;

-- Gold E: A2 30-day retention per top-level category next to API chart coverage. Each side is aggregated on its own
-- first (flag per subscription -> per category; API podcasts -> per category) and joined only afterwards, so no A2 record
-- is counted twice. Ranks are computed among A2 categories only ('Unmapped' has no A2 side).
-- Gold E:按一级类目并列 A2 的 30 天留存与 API 榜单覆盖。两侧先各自聚合再连接,不会重复计算 A2 记录;
-- 名次只在 A2 类目之间计算('Unmapped' 没有 A2 一侧)。
CREATE OR REPLACE VIEW GOLD.GOLD_CATEGORY_RETENTION AS
WITH top_of AS (
  SELECT c.category_id, COALESCE(p.category_name, c.category_name) AS top_name
  FROM SILVER.CATEGORY c LEFT JOIN SILVER.CATEGORY p ON c.parent_category_id = p.category_id),
sub AS (
  SELECT s.listener_key, s.show_id, s.subscribed_on, t.top_name AS a2_top_category
  FROM SILVER.SUBSCRIPTION s
  JOIN SILVER.PODCAST_SHOW ps ON s.show_id = ps.show_id
  JOIN top_of t ON ps.category_id = t.category_id),
ses AS (
  SELECT l.listener_key, e.show_id, l.session_started_at::DATE AS session_date
  FROM SILVER.LISTENING_SESSION l JOIN SILVER.EPISODE e ON l.episode_id = e.episode_id),
flag AS (
  SELECT sub.listener_key, sub.show_id, sub.a2_top_category,
         COALESCE(MAX(IFF(DATEDIFF('day', sub.subscribed_on, ses.session_date) BETWEEN 0 AND 29, 1, 0)), 0) AS retained,
         IFF(sub.subscribed_on <= DATE '2026-08-31', 1, 0) AS observable
  FROM sub LEFT JOIN ses ON sub.listener_key = ses.listener_key AND sub.show_id = ses.show_id
  GROUP BY sub.listener_key, sub.show_id, sub.a2_top_category, sub.subscribed_on),
a2 AS (
  SELECT a2_top_category, COUNT(*) AS a2_subscriptions, SUM(observable) AS observable_subscriptions,
         SUM(IFF(observable = 1, retained, 0)) AS retained_30d
  FROM flag GROUP BY a2_top_category),
api AS (
  SELECT a2_top_category, COUNT(DISTINCT podcast_id) AS api_charted_podcasts
  FROM SILVER.API_PODCAST GROUP BY a2_top_category),
rk AS (
  SELECT p.a2_top_category, ROUND(AVG(r.chart_rank), 1) AS api_avg_chart_rank
  FROM SILVER.API_CHART_RANK r JOIN SILVER.API_PODCAST p ON r.podcast_id = p.podcast_id
  GROUP BY p.a2_top_category),
joined AS (
  SELECT COALESCE(a2.a2_top_category, api.a2_top_category) AS a2_top_category,
         a2.a2_subscriptions, a2.observable_subscriptions, a2.retained_30d,
         ROUND(100 * a2.retained_30d / NULLIF(a2.observable_subscriptions, 0), 1) AS retention_30d_pct,
         api.api_charted_podcasts,
         ROUND(100 * api.api_charted_podcasts / SUM(api.api_charted_podcasts) OVER (), 1) AS api_chart_share_pct,
         rk.api_avg_chart_rank
  FROM a2 FULL OUTER JOIN api ON a2.a2_top_category = api.a2_top_category
  LEFT JOIN rk ON COALESCE(a2.a2_top_category, api.a2_top_category) = rk.a2_top_category)
SELECT j.*,
       IFF(a2_subscriptions IS NULL, NULL, RANK() OVER (PARTITION BY (a2_subscriptions IS NULL) ORDER BY retention_30d_pct DESC)) AS retention_rank,
       IFF(a2_subscriptions IS NULL, NULL, RANK() OVER (PARTITION BY (a2_subscriptions IS NULL) ORDER BY api_chart_share_pct DESC)) AS chart_share_rank
FROM joined j;
