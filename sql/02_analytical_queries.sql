-- =====================================================================================
-- 02_analytical_queries.sql
-- Assignment 3, Part 2 - five analytical queries on the star schema (database PODCAST_DW).
-- 作业 3 第 2 部分 - 星型模型上的 5 条分析查询。
-- Each query starts with a marker line "-- @Qn | title"; pipeline/06_run_queries.py runs them one by one.
-- 每条查询以 "-- @Qn | 标题" 开头;pipeline/06_run_queries.py 逐条运行。
-- Plan tiers below are the plan the creator had ON THE EVENT DATE (SCD2 point-in-time), the history is simulated.
-- 下面的套餐是事件发生当天创作者所处的套餐(SCD2 时点),套餐历史是模拟的。
-- =====================================================================================

-- @Q1 | ROLLUP: listening hours by top-level category, then category, with subtotals and a grand total
-- 按一级类目、类目汇总收听小时,带小计和总计(ROLLUP)
SELECT IFF(GROUPING(s.top_category_name) = 1, '** ALL CATEGORIES **', s.top_category_name) AS top_category,
       IFF(GROUPING(s.category_name) = 1, '(subtotal)', s.category_name)                   AS category,
       COUNT(*)                                          AS sessions,
       ROUND(SUM(f.listened_seconds) / 3600, 1)          AS listening_hours,
       ROUND(100 * AVG(IFF(f.completed = 'Y', 1, 0)), 1) AS completion_rate_pct
FROM STAR.FACT_LISTENING_SESSION f
JOIN STAR.DIM_SHOW s ON f.show_sk = s.show_sk
GROUP BY ROLLUP (s.top_category_name, s.category_name)
ORDER BY GROUPING(s.top_category_name), s.top_category_name, GROUPING(s.category_name), listening_hours DESC;

-- @Q2 | GROUPING SETS: completion rate by creator plan (at the time) and device, with per-plan, per-device and overall rows
-- 按(当时)创作者套餐和设备统计完播率,同时给出按套餐、按设备和总体的行(GROUPING SETS)
SELECT COALESCE(c.plan_tier, 'ALL PLANS')      AS plan_tier_at_time,
       COALESCE(f.device_type, 'ALL DEVICES')  AS device_type,
       COUNT(*)                                          AS sessions,
       ROUND(AVG(f.listened_seconds) / 60, 1)            AS avg_minutes_listened,
       ROUND(100 * AVG(IFF(f.completed = 'Y', 1, 0)), 1) AS completion_rate_pct
FROM STAR.FACT_LISTENING_SESSION f
JOIN STAR.DIM_CREATOR c ON f.creator_sk = c.creator_sk
GROUP BY GROUPING SETS ((c.plan_tier, f.device_type), (c.plan_tier), (f.device_type), ())
ORDER BY GROUPING(c.plan_tier), c.plan_tier, GROUPING(f.device_type), f.device_type;

-- @Q3 | SCD2 in action: sessions by the plan at the time vs the creator's CURRENT plan (only creators whose plan changed)
-- SCD2 的作用:按"当时套餐"与"当前套餐"对比会话数(只看套餐变更过的创作者)
SELECT h.plan_tier   AS plan_at_time,
       cur.plan_tier AS plan_now,
       COUNT(DISTINCT h.creator_id)             AS creators,
       COUNT(*)                                 AS sessions,
       ROUND(SUM(f.listened_seconds) / 3600, 1) AS listening_hours
FROM STAR.FACT_LISTENING_SESSION f
JOIN STAR.DIM_CREATOR h   ON f.creator_sk = h.creator_sk
JOIN STAR.DIM_CREATOR cur ON cur.creator_id = h.creator_id AND cur.is_current
WHERE h.creator_id IN (SELECT creator_id FROM STAR.DIM_CREATOR GROUP BY creator_id HAVING COUNT(*) > 1)
GROUP BY h.plan_tier, cur.plan_tier
ORDER BY plan_at_time, plan_now;

-- @Q4 | Window function: top 3 shows per top-level category by listening hours
-- 窗口函数:每个一级类目收听小时最高的 3 档节目
WITH per_show AS (
  SELECT s.top_category_name, s.show_title, COUNT(*) AS sessions,
         ROUND(SUM(f.listened_seconds) / 3600, 1) AS listening_hours
  FROM STAR.FACT_LISTENING_SESSION f
  JOIN STAR.DIM_SHOW s ON f.show_sk = s.show_sk
  GROUP BY s.top_category_name, s.show_title),
ranked AS (
  SELECT *, RANK() OVER (PARTITION BY top_category_name ORDER BY listening_hours DESC) AS rank_in_category,
         ROUND(100 * listening_hours / SUM(listening_hours) OVER (PARTITION BY top_category_name), 1) AS share_of_category_pct
  FROM per_show)
SELECT top_category_name, rank_in_category, show_title, sessions, listening_hours, share_of_category_pct
FROM ranked
WHERE rank_in_category <= 3
ORDER BY top_category_name, rank_in_category;

-- @Q5 | 30-day retention per show: the 5 highest and 5 lowest shows (only shows with >= 30 observable subscriptions)
-- 按节目看 30 天留存:最高 5 档和最低 5 档(只看可观察订阅数 >= 30 的节目)
-- Small samples make rates noisy, so each show also gets a 95% Wilson confidence interval, and a flag says whether the
-- overall rate lies OUTSIDE that interval (i.e. the show differs from average more than chance alone would explain).
-- With ~80 shows tested, a few flags are expected by chance alone: read the list as "worth a look", not as proof.
-- 样本小时比例波动大,所以每档节目附带 95% Wilson 置信区间,并标注整体留存率是否落在区间之外(即差异超出随机波动)。
-- 同时检验约 80 档节目,即使没有真实差异也会有少数被标记:结果应理解为"值得关注",而不是定论。
WITH subs AS (
  SELECT fs.listener_sk, fs.show_sk, d.full_date AS sub_date
  FROM STAR.FACT_SUBSCRIPTION fs
  JOIN STAR.DIM_DATE d ON fs.date_key = d.date_key
  WHERE d.full_date <= DATE '2026-08-31'),
sess AS (
  SELECT f.listener_sk, f.show_sk, d.full_date AS session_date
  FROM STAR.FACT_LISTENING_SESSION f
  JOIN STAR.DIM_DATE d ON f.date_key = d.date_key),
flag AS (
  SELECT s.listener_sk, s.show_sk, MAX(IFF(x.session_date IS NOT NULL, 1, 0)) AS retained
  FROM subs s
  LEFT JOIN sess x
    ON x.listener_sk = s.listener_sk AND x.show_sk = s.show_sk
   AND x.session_date >= s.sub_date AND x.session_date < DATEADD('day', 30, s.sub_date)
  GROUP BY s.listener_sk, s.show_sk),
overall AS (SELECT SUM(retained) / COUNT(*) AS p_all FROM flag),
per_show AS (
  SELECT show_sk, COUNT(*) AS n, SUM(retained) AS retained_30d, SUM(retained) / COUNT(*) AS p
  FROM flag GROUP BY show_sk HAVING COUNT(*) >= 30),
scored AS (               -- Wilson interval, z = 1.96 / Wilson 区间
  SELECT p.*, 1.96 AS z,
         (p.p + 1.96 * 1.96 / (2 * p.n)) / (1 + 1.96 * 1.96 / p.n) AS centre,
         1.96 * SQRT(p.p * (1 - p.p) / p.n + 1.96 * 1.96 / (4 * p.n * p.n)) / (1 + 1.96 * 1.96 / p.n) AS half
  FROM per_show p),
ranked AS (
  SELECT sc.*, sh.show_title, sh.top_category_name,
         RANK() OVER (ORDER BY sc.p DESC) AS rk_high, RANK() OVER (ORDER BY sc.p ASC) AS rk_low
  FROM scored sc JOIN STAR.DIM_SHOW sh ON sc.show_sk = sh.show_sk)
SELECT IFF(rk_high <= 5, 'highest 5', 'lowest 5') AS grp, show_title, top_category_name,
       n AS subscriptions, retained_30d,
       ROUND(100 * p, 1) AS retention_30d_pct,
       ROUND(100 * (centre - half), 1) AS ci95_low_pct, ROUND(100 * (centre + half), 1) AS ci95_high_pct,
       ROUND(100 * o.p_all, 1) AS overall_pct,
       IFF(o.p_all < centre - half OR o.p_all > centre + half, 'yes', 'no') AS differs_from_overall
FROM ranked CROSS JOIN overall o
WHERE rk_high <= 5 OR rk_low <= 5
ORDER BY p DESC;
