-- =====================================================================================
-- 04_part4a_queries.sql
-- Assignment 3, Part 4a - three relational queries on the star schema (database PODCAST_DW).
-- 作业 3 第 4a 部分 - 星型模型上的 3 条关系型查询。
-- Markers "-- @Rn | title" are read by pipeline/06_run_queries.py:  python pipeline/06_run_queries.py R1 --file sql/04_part4a_queries.sql
-- 标记行 "-- @Rn | 标题" 由 06_run_queries.py 读取。
-- These three use what the relational model is best at: time series, multi-dimension cubes, SCD2 point-in-time + running totals.
-- 这 3 条展示关系型擅长的事:时间序列、多维立方体、SCD2 时点加累计。
-- =====================================================================================

-- @R1 | Monthly listening trend with month-over-month change and a 3-month moving average
-- 每月收听趋势:环比变化和 3 个月移动平均
SELECT d.year, d.month,
       COUNT(*)                                   AS sessions,
       ROUND(SUM(f.listened_seconds) / 3600, 1)   AS listening_hours,
       ROUND(100 * (SUM(f.listened_seconds) / NULLIF(LAG(SUM(f.listened_seconds)) OVER (ORDER BY d.year, d.month), 0) - 1), 1)
                                                  AS hours_mom_pct,
       ROUND(AVG(SUM(f.listened_seconds) / 3600) OVER (ORDER BY d.year, d.month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1)
                                                  AS hours_3m_moving_avg
FROM STAR.FACT_LISTENING_SESSION f
JOIN STAR.DIM_DATE d ON f.date_key = d.date_key
GROUP BY d.year, d.month
ORDER BY d.year, d.month;

-- @R2 | CUBE: listening hours and completion rate for every combination of top-level category and device (incl. subtotals)
-- CUBE:一级类目与设备的所有组合的收听小时和完播率(含各级小计)
SELECT COALESCE(s.top_category_name, 'ALL CATEGORIES') AS top_category,
       COALESCE(f.device_type, 'ALL DEVICES')          AS device_type,
       COUNT(*)                                          AS sessions,
       ROUND(SUM(f.listened_seconds) / 3600, 1)          AS listening_hours,
       ROUND(100 * AVG(IFF(f.completed = 'Y', 1, 0)), 1) AS completion_rate_pct
FROM STAR.FACT_LISTENING_SESSION f
JOIN STAR.DIM_SHOW s ON f.show_sk = s.show_sk
GROUP BY CUBE (s.top_category_name, f.device_type)
ORDER BY GROUPING(s.top_category_name), s.top_category_name, GROUPING(f.device_type), listening_hours DESC;

-- @R3 | New subscriptions per quarter by the creator's plan AT SUBSCRIPTION TIME (SCD2), with a running total per plan
-- 每季度新增订阅数,按订阅当时创作者的套餐(SCD2)分组,并给出每个套餐的累计值
SELECT d.year, d.quarter, c.plan_tier AS plan_at_subscription,
       SUM(fs.subscription_count) AS new_subscriptions,
       SUM(SUM(fs.subscription_count)) OVER (PARTITION BY c.plan_tier ORDER BY d.year, d.quarter) AS running_total
FROM STAR.FACT_SUBSCRIPTION fs
JOIN STAR.DIM_DATE d    ON fs.date_key = d.date_key
JOIN STAR.DIM_CREATOR c ON fs.creator_sk = c.creator_sk
GROUP BY d.year, d.quarter, c.plan_tier
ORDER BY c.plan_tier, d.year, d.quarter;
