-- Undo optimization C: remove the clustering keys so later runs start from the baseline layout.
-- 撤销优化 C:删除聚簇键,让之后的测试回到基线状态。
ALTER TABLE STAR.FACT_LISTENING_SESSION DROP CLUSTERING KEY;
ALTER TABLE STAR.FACT_SUBSCRIPTION DROP CLUSTERING KEY;
