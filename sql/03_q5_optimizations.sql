-- =====================================================================================
-- 03_q5_optimizations.sql
-- Assignment 3, Part 2 - optimized versions of Q5 (the most expensive query, see logs/query_metrics.csv).
-- 作业 3 第 2 部分 - Q5(最耗资源的查询)的优化版本。
-- A = rewrite, B = pre-computed table. C (clustering) re-runs the ORIGINAL Q5 after sql/03c_cluster_on.sql.
-- A = 改写,B = 预计算表。C(聚簇)是在运行 03c_cluster_on.sql 之后重跑原始 Q5。
-- Run: python pipeline/06_run_queries.py Q5A --file sql/03_q5_optimizations.sql --repeat 5 --label A_rewrite
-- =====================================================================================

-- @Q5A | Optimization A (query rewrite): semi-join with EXISTS instead of LEFT JOIN + MAX over every matching session
-- 优化 A(改写查询):用 EXISTS 半连接代替"左连接所有匹配会话再 MAX",不再把一条订阅展开成多行
-- Same question and same output columns as Q5 in 02_analytical_queries.sql; only the way `flag` is computed differs.
-- 问题和输出列与 02 文件里的 Q5 完全相同,只有 `flag`(每条订阅是否留存)的计算方式不同。
WITH subs AS (
  SELECT fs.listener_sk, fs.show_sk, d.full_date AS sub_date
  FROM STAR.FACT_SUBSCRIPTION fs
  JOIN STAR.DIM_DATE d ON fs.date_key = d.date_key
  WHERE d.full_date <= DATE '2026-08-31'),
sess AS (
  SELECT DISTINCT f.listener_sk, f.show_sk, d.full_date AS session_date      -- one row per (listener, show, day) / 同一天多次会话只留一行
  FROM STAR.FACT_LISTENING_SESSION f
  JOIN STAR.DIM_DATE d ON f.date_key = d.date_key),
matched AS (
  SELECT s.listener_sk, s.show_sk
  FROM subs s
  WHERE EXISTS (SELECT 1 FROM sess x
                WHERE x.listener_sk = s.listener_sk AND x.show_sk = s.show_sk
                  AND x.session_date >= s.sub_date AND x.session_date < DATEADD('day', 30, s.sub_date))),
flag AS (
  SELECT s.listener_sk, s.show_sk, IFF(m.listener_sk IS NULL, 0, 1) AS retained
  FROM subs s LEFT JOIN matched m ON m.listener_sk = s.listener_sk AND m.show_sk = s.show_sk),
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

-- @Q5B | Optimization B (pre-computed): read the retention flag from STAR.AGG_SUBSCRIPTION_RETENTION
-- 优化 B(预计算):直接读 STAR.AGG_SUBSCRIPTION_RETENTION 里提前算好的留存标记
-- The table is built once by sql/03a_setup_agg_table.sql (that one-off cost is reported separately).
-- 该表由 sql/03a_setup_agg_table.sql 一次性建好(这笔一次性成本单独报告)。
-- Same question and same output columns as Q5 in 02_analytical_queries.sql; only the way `flag` is computed differs.
-- 问题和输出列与 02 文件里的 Q5 完全相同,只有 `flag`(每条订阅是否留存)的计算方式不同。
WITH flag AS (
  SELECT listener_sk, show_sk, retained_30d AS retained
  FROM STAR.AGG_SUBSCRIPTION_RETENTION
  WHERE is_observable = 1),
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
