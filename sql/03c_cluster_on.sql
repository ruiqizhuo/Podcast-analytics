-- Optimization C setup: define a clustering key on both fact tables (then re-run the ORIGINAL Q5).
-- 优化 C 的准备:给两张事实表定义聚簇键(然后重跑原始 Q5)。
-- Note: Snowflake re-clusters in the background with serverless compute, which uses a small amount of credits.
-- 注意:Snowflake 会在后台用无服务器计算重新聚簇,会消耗少量额度。
ALTER TABLE STAR.FACT_LISTENING_SESSION CLUSTER BY (show_sk, date_key);
ALTER TABLE STAR.FACT_SUBSCRIPTION CLUSTER BY (show_sk, date_key);
