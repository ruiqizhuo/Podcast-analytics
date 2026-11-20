-- Optimization B setup: pre-compute, once, whether each subscription was retained within 30 days.
-- 优化 B 的准备:一次性算好"每条订阅是否在 30 天内留存"。
-- Trade-off: the work moves from query time to load time, and the table must be rebuilt when new sessions or subscriptions arrive.
-- 代价:计算从查询时移到加载时;有新会话或新订阅时要重建。
CREATE OR REPLACE TABLE STAR.AGG_SUBSCRIPTION_RETENTION AS
WITH subs AS (
  SELECT fs.listener_sk, fs.show_sk, d.full_date AS sub_date
  FROM STAR.FACT_SUBSCRIPTION fs JOIN STAR.DIM_DATE d ON fs.date_key = d.date_key),
sess AS (
  SELECT f.listener_sk, f.show_sk, d.full_date AS session_date
  FROM STAR.FACT_LISTENING_SESSION f JOIN STAR.DIM_DATE d ON f.date_key = d.date_key)
SELECT s.listener_sk, s.show_sk, s.sub_date,
       MAX(IFF(x.session_date IS NOT NULL, 1, 0)) AS retained_30d,
       IFF(s.sub_date <= DATE '2026-08-31', 1, 0) AS is_observable      -- full 30-day window exists / 30 天窗口完整
FROM subs s
LEFT JOIN sess x
  ON x.listener_sk = s.listener_sk AND x.show_sk = s.show_sk
 AND x.session_date >= s.sub_date AND x.session_date < DATEADD('day', 30, s.sub_date)
GROUP BY s.listener_sk, s.show_sk, s.sub_date;
