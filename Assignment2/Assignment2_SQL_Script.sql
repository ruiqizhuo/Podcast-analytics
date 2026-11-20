-- =============================================================================
-- Assignment2_SQL_Script.sql
-- Cloud Native Data Engineering - Assignment 2 (single submission file)
-- 云原生数据工程 - 作业 2(单个提交文件)
--
-- Contents / 内容
--   PART 4a  Schema DDL: 11 tables, PKs, FKs, constraints          建表脚本
--   PART 4c  Verification: row count of every table                验证:每张表的行数
--   PART 5   Eight business queries, each with its business question  8 条业务查询
--   PART 6   Index experiment: EXPLAIN ANALYZE before / after        索引实验
--
-- Target / 目标: Amazon RDS for MySQL 8.4 (works on MySQL 8.0+).
-- Security / 安全: no passwords or access keys appear in this file.   本文件不含任何密码或密钥。
-- =============================================================================

-- =============================================================================
-- PART 4a. Schema creation (DDL)
-- 第 4a 部分:建表(DDL)
-- =============================================================================
-- =============================================================================
-- schema.sql
-- Cloud Native Data Engineering - Assignment 2, Part 4a (Schema creation / DDL)
-- 云原生数据工程 - 作业 2 第 4a 部分(建表脚本 / DDL)
--
-- Domain / 领域 : Podcast hosting + creator-side retention analytics
-- Target / 目标 : Amazon RDS for MySQL 8.0+   (tested on MySQL 8.0)
-- Tables / 表   : 11 tables in 3NF, loaded from the normalized CSV files
--
-- Design notes / 设计说明
--   * Every table is InnoDB, utf8mb4.                                  所有表用 InnoDB 与 utf8mb4。
--   * 'podcast_show' is NOT called 'show' because SHOW is a reserved word in MySQL.
--     表名用 podcast_show,因为 show 是 MySQL 保留字。
--   * Many-to-many relationships are resolved with junction tables:
--       episode  x guest   -> episode_guest
--       listener x show    -> subscription
--     多对多用中间表解决。
--   * category.parent_category_id is a self-reference (recursive hierarchy);
--     NULL = top-level category.                                       类目表自引用,NULL 表示一级类目。
--   * ON DELETE RESTRICT protects history (cannot delete a show that has episodes, a listener
--     that has sessions, ...). Junction tables use ON DELETE CASCADE.
--     RESTRICT 保护历史数据;中间表用 CASCADE。
--   * No extra secondary indexes are created on purpose: Part 6 adds one and compares EXPLAIN plans.
--     故意不建额外索引:第 6 部分要建一个索引并对比执行计划。(InnoDB 会为外键自动建索引。)
--   * listening_session.completed is a stored derived column (from listened_seconds and the episode duration), kept for query convenience.
--     completed 是由 listened_seconds 与单集时长算出的存储派生列,为查询方便而保留。
-- =============================================================================

CREATE DATABASE IF NOT EXISTS podcast_db
    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE podcast_db;

-- Drop in reverse dependency order so the script can be re-run.
-- 按依赖的反序删除,脚本可重复执行。
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS listening_session, subscription, listener, episode_guest, guest,
                     episode, podcast_show, creator, category, plan, country;
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------------
-- 1. country  (listener.country_code -> country_name was a transitive dependency)
-- ---------------------------------------------------------------------------
CREATE TABLE country (
    country_code  CHAR(2)      NOT NULL COMMENT 'ISO 3166-1 alpha-2, e.g. US',
    country_name  VARCHAR(60)  NOT NULL,
    CONSTRAINT pk_country      PRIMARY KEY (country_code),
    CONSTRAINT uq_country_name UNIQUE (country_name)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 2. plan  (creator plan tier -> monthly price)
-- ---------------------------------------------------------------------------
CREATE TABLE plan (
    plan_tier          VARCHAR(20)  NOT NULL COMMENT 'Free / Standard / Pro',
    monthly_price_usd  DECIMAL(8,2) NOT NULL,
    CONSTRAINT pk_plan        PRIMARY KEY (plan_tier),
    CONSTRAINT ck_plan_price  CHECK (monthly_price_usd >= 0)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 3. category  (self-referencing hierarchy: parent_category_id -> category_id)
-- ---------------------------------------------------------------------------
CREATE TABLE category (
    category_id         INT          NOT NULL,
    category_name       VARCHAR(60)  NOT NULL,
    parent_category_id  INT          NULL COMMENT 'NULL = top-level category',
    CONSTRAINT pk_category        PRIMARY KEY (category_id),
    CONSTRAINT uq_category_name   UNIQUE (category_name),
    CONSTRAINT fk_category_parent FOREIGN KEY (parent_category_id)
        REFERENCES category (category_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_category_not_own_parent CHECK (parent_category_id IS NULL OR parent_category_id <> category_id)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 4. creator
-- ---------------------------------------------------------------------------
CREATE TABLE creator (
    creator_id     INT           NOT NULL,
    creator_name   VARCHAR(100)  NOT NULL,
    creator_email  VARCHAR(150)  NOT NULL,
    plan_tier      VARCHAR(20)   NOT NULL,
    CONSTRAINT pk_creator       PRIMARY KEY (creator_id),
    CONSTRAINT uq_creator_email UNIQUE (creator_email),
    CONSTRAINT fk_creator_plan  FOREIGN KEY (plan_tier)
        REFERENCES plan (plan_tier) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 5. podcast_show
-- ---------------------------------------------------------------------------
CREATE TABLE podcast_show (
    show_id      INT           NOT NULL,
    show_title   VARCHAR(100)  NOT NULL,
    creator_id   INT           NOT NULL,
    category_id  INT           NOT NULL,
    CONSTRAINT pk_podcast_show      PRIMARY KEY (show_id),
    CONSTRAINT fk_show_creator      FOREIGN KEY (creator_id)
        REFERENCES creator (creator_id)   ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_show_category     FOREIGN KEY (category_id)
        REFERENCES category (category_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 6. episode
-- ---------------------------------------------------------------------------
CREATE TABLE episode (
    episode_id            INT           NOT NULL,
    show_id               INT           NOT NULL,
    episode_title         VARCHAR(150)  NOT NULL,
    episode_duration_sec  INT           NOT NULL,
    episode_publish_date  DATE          NOT NULL,
    CONSTRAINT pk_episode          PRIMARY KEY (episode_id),
    CONSTRAINT fk_episode_show     FOREIGN KEY (show_id)
        REFERENCES podcast_show (show_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_episode_duration CHECK (episode_duration_sec > 0)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 7. guest   and   8. episode_guest  (many-to-many: episode x guest)
-- ---------------------------------------------------------------------------
CREATE TABLE guest (
    guest_id    INT           NOT NULL,
    guest_name  VARCHAR(100)  NOT NULL,
    CONSTRAINT pk_guest       PRIMARY KEY (guest_id),
    CONSTRAINT uq_guest_name  UNIQUE (guest_name)
) ENGINE = InnoDB;

CREATE TABLE episode_guest (
    episode_id  INT  NOT NULL,
    guest_id    INT  NOT NULL,
    CONSTRAINT pk_episode_guest PRIMARY KEY (episode_id, guest_id),
    CONSTRAINT fk_eg_episode    FOREIGN KEY (episode_id)
        REFERENCES episode (episode_id) ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT fk_eg_guest      FOREIGN KEY (guest_id)
        REFERENCES guest (guest_id)     ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 9. listener
-- (listener_email is NOT unique: the synthetic data contains one e-mail shared by two listeners)
-- (听众邮箱不设唯一:合成数据里有 1 个邮箱被两位听众共用)
-- ---------------------------------------------------------------------------
CREATE TABLE listener (
    listener_id     INT           NOT NULL,
    listener_name   VARCHAR(100)  NOT NULL,
    listener_email  VARCHAR(150)  NULL,
    listener_city   VARCHAR(80)   NULL,
    country_code    CHAR(2)       NOT NULL,
    CONSTRAINT pk_listener          PRIMARY KEY (listener_id),
    CONSTRAINT fk_listener_country  FOREIGN KEY (country_code)
        REFERENCES country (country_code) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 10. subscription  (many-to-many: listener x podcast_show, with the subscribe date)
-- A row exists if and only if the listener is subscribed (replaces the old is_subscribed Y/N flag).
-- 有这一行才表示已订阅(取代原来的 is_subscribed Y/N)。
-- ---------------------------------------------------------------------------
CREATE TABLE subscription (
    listener_id    INT   NOT NULL,
    show_id        INT   NOT NULL,
    subscribed_on  DATE  NOT NULL,
    CONSTRAINT pk_subscription      PRIMARY KEY (listener_id, show_id),
    CONSTRAINT fk_sub_listener      FOREIGN KEY (listener_id)
        REFERENCES listener (listener_id)  ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT fk_sub_show          FOREIGN KEY (show_id)
        REFERENCES podcast_show (show_id)  ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 11. listening_session  (the fact-like event table: one row = one listening session)
-- ---------------------------------------------------------------------------
CREATE TABLE listening_session (
    session_id          INT          NOT NULL AUTO_INCREMENT,
    listener_id         INT          NOT NULL,
    episode_id          INT          NOT NULL,
    session_started_at  DATETIME     NOT NULL,
    listened_seconds    INT          NOT NULL,
    completed           CHAR(1)      NOT NULL COMMENT 'Y = listened to the end (>= 95%), N = not',
    device_type         VARCHAR(20)  NOT NULL,
    CONSTRAINT pk_listening_session  PRIMARY KEY (session_id),
    CONSTRAINT uq_session_natural    UNIQUE (listener_id, episode_id, session_started_at),
    CONSTRAINT fk_session_listener   FOREIGN KEY (listener_id)
        REFERENCES listener (listener_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_session_episode    FOREIGN KEY (episode_id)
        REFERENCES episode (episode_id)   ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_session_seconds    CHECK (listened_seconds >= 0),
    CONSTRAINT ck_session_completed  CHECK (completed IN ('Y', 'N')),
    CONSTRAINT ck_session_device     CHECK (device_type IN ('Mobile', 'Desktop', 'Tablet', 'Smart Speaker'))
) ENGINE = InnoDB;


-- =============================================================================
-- PART 4c. Verification
-- 第 4c 部分:验证
-- =============================================================================
USE podcast_db;

-- Row count of every table and the total (expected total: 72,856 rows).
-- 每张表的行数以及总数(预期总数:72,856)。
SELECT 'country'           AS table_name, COUNT(*) AS row_count FROM country
UNION ALL SELECT 'plan',              COUNT(*) FROM plan
UNION ALL SELECT 'category',          COUNT(*) FROM category
UNION ALL SELECT 'creator',           COUNT(*) FROM creator
UNION ALL SELECT 'podcast_show',      COUNT(*) FROM podcast_show
UNION ALL SELECT 'episode',           COUNT(*) FROM episode
UNION ALL SELECT 'guest',             COUNT(*) FROM guest
UNION ALL SELECT 'episode_guest',     COUNT(*) FROM episode_guest
UNION ALL SELECT 'listener',          COUNT(*) FROM listener
UNION ALL SELECT 'subscription',      COUNT(*) FROM subscription
UNION ALL SELECT 'listening_session', COUNT(*) FROM listening_session;

SELECT (SELECT COUNT(*) FROM country) + (SELECT COUNT(*) FROM plan) + (SELECT COUNT(*) FROM category)
     + (SELECT COUNT(*) FROM creator) + (SELECT COUNT(*) FROM podcast_show) + (SELECT COUNT(*) FROM episode)
     + (SELECT COUNT(*) FROM guest) + (SELECT COUNT(*) FROM episode_guest) + (SELECT COUNT(*) FROM listener)
     + (SELECT COUNT(*) FROM subscription) + (SELECT COUNT(*) FROM listening_session) AS total_rows;

SELECT VERSION() AS mysql_version;


-- =============================================================================
-- PART 5. Eight business queries
-- 第 5 部分:8 条业务查询
-- =============================================================================
-- =============================================================================
-- queries.sql
-- Cloud Native Data Engineering - Assignment 2, Part 5 (Query your data)
-- 云原生数据工程 - 作业 2 第 5 部分(查询数据)
--
-- Eight business queries on the 3NF podcast database (podcast_db, MySQL 8.0+).
-- 在 3NF 播客数据库(podcast_db,MySQL 8.0+)上的 8 条业务查询。
--
-- Coverage / 覆盖:
--   INNER JOIN : Q1 Q2 Q3 Q4 Q6 Q7        LEFT JOIN : Q1 Q3 Q4 Q6 Q8        RIGHT JOIN : Q8
--   GROUP BY + HAVING : Q2 Q3 Q6
--   CTE (WITH) : Q4 Q5 Q6                 Window functions : Q1 Q4 Q5 Q7
--
-- "As of" date: the data ends on 2026-09-30, so queries use that fixed date instead of CURDATE().
-- "截止日期":数据到 2026-09-30 结束,所以查询里用固定日期,而不是 CURDATE()。
-- =============================================================================
USE podcast_db;


-- -----------------------------------------------------------------------------
-- Q1. Which top-level categories attract the most listening time, and what share
--     of all listening time does each one hold?
-- Q1. 哪些一级类目吸引了最多的收听时长?各占总时长的多少?
-- Tech: 5-table INNER JOIN, self-join to the parent category (LEFT JOIN),
--       GROUP BY, window function SUM() OVER ().
-- -----------------------------------------------------------------------------
SELECT
    COALESCE(p.category_name, c.category_name)                  AS top_level_category,
    COUNT(*)                                                    AS sessions,
    ROUND(SUM(ls.listened_seconds) / 3600, 1)                   AS listening_hours,
    ROUND(100 * SUM(ls.listened_seconds)
              / SUM(SUM(ls.listened_seconds)) OVER (), 1)       AS pct_of_total_hours
FROM listening_session ls
JOIN episode       e ON e.episode_id  = ls.episode_id
JOIN podcast_show  s ON s.show_id     = e.show_id
JOIN category      c ON c.category_id = s.category_id
LEFT JOIN category p ON p.category_id = c.parent_category_id      -- parent is NULL for top-level categories
GROUP BY COALESCE(p.category_name, c.category_name)
ORDER BY listening_hours DESC;


-- -----------------------------------------------------------------------------
-- Q2. How much listening does each creator plan tier generate, in total and per
--     creator? (Only tiers with at least 20 creators, so small tiers do not distort averages.)
-- Q2. 每种创作者套餐产生了多少收听,总量和人均各是多少?(只看至少有 20 位创作者的套餐)
-- Tech: INNER JOIN x5, GROUP BY, HAVING, COUNT(DISTINCT).
-- -----------------------------------------------------------------------------
SELECT
    cr.plan_tier,
    pl.monthly_price_usd,
    COUNT(DISTINCT cr.creator_id)                                          AS creators,
    COUNT(*)                                                               AS sessions,
    ROUND(SUM(ls.listened_seconds) / 3600, 1)                              AS listening_hours,
    ROUND(SUM(ls.listened_seconds) / 3600 / COUNT(DISTINCT cr.creator_id), 1) AS hours_per_creator
FROM listening_session ls
JOIN episode      e  ON e.episode_id  = ls.episode_id
JOIN podcast_show s  ON s.show_id     = e.show_id
JOIN creator      cr ON cr.creator_id = s.creator_id
JOIN plan         pl ON pl.plan_tier  = cr.plan_tier
GROUP BY cr.plan_tier, pl.monthly_price_usd
HAVING COUNT(DISTINCT cr.creator_id) >= 20
ORDER BY hours_per_creator DESC;


-- -----------------------------------------------------------------------------
-- Q3. Which shows have fewer than 20 subscribers and are therefore candidates for
--     promotion? Show the creator and category as well (15 weakest shown).
-- Q3. 哪些节目的订阅人数不足 20 人,适合重点推广?同时显示创作者和类目(只列最弱的 15 个)。
-- Tech: LEFT JOIN (keeps shows with zero subscribers), GROUP BY, HAVING.
-- -----------------------------------------------------------------------------
SELECT
    s.show_id,
    s.show_title,
    cr.creator_name,
    c.category_name,
    COUNT(sub.listener_id) AS subscribers
FROM podcast_show s
JOIN creator  cr ON cr.creator_id  = s.creator_id
JOIN category c  ON c.category_id  = s.category_id
LEFT JOIN subscription sub ON sub.show_id = s.show_id
GROUP BY s.show_id, s.show_title, cr.creator_name, c.category_name
HAVING COUNT(sub.listener_id) < 20
ORDER BY subscribers ASC, s.show_title
LIMIT 15;

-- Supporting counts quoted in the report (not one of the eight queries): total shows and shows with fewer than 20 subscribers.
-- 报告中引用的支撑计数(不属于 8 条查询之一):节目总数,以及订阅人数不足 20 的节目数。
SELECT COUNT(*)                   AS shows_total,
       SUM(subscribers < 20)      AS shows_under_20_subscribers
FROM (
    SELECT s.show_id, COUNT(sub.listener_id) AS subscribers
    FROM podcast_show s
    LEFT JOIN subscription sub ON sub.show_id = s.show_id
    GROUP BY s.show_id
) AS per_show;


-- -----------------------------------------------------------------------------
-- Q4. Which are the top 3 shows by number of sessions inside each top-level category?
-- Q4. 每个一级类目里,按会话数排名前 3 的节目是哪些?
-- Tech: two CTEs, INNER + LEFT JOIN, window function RANK() OVER (PARTITION BY ...).
-- -----------------------------------------------------------------------------
WITH show_sessions AS (
    SELECT
        s.show_id,
        s.show_title,
        COALESCE(p.category_name, c.category_name) AS top_level_category,
        COUNT(*)                                   AS sessions
    FROM listening_session ls
    JOIN episode       e ON e.episode_id  = ls.episode_id
    JOIN podcast_show  s ON s.show_id     = e.show_id
    JOIN category      c ON c.category_id = s.category_id
    LEFT JOIN category p ON p.category_id = c.parent_category_id
    GROUP BY s.show_id, s.show_title, COALESCE(p.category_name, c.category_name)
),
ranked AS (
    SELECT
        show_sessions.*,
        RANK() OVER (PARTITION BY top_level_category ORDER BY sessions DESC) AS rnk
    FROM show_sessions
)
SELECT top_level_category, rnk AS category_rank, show_title, sessions
FROM ranked
WHERE rnk <= 3
ORDER BY top_level_category, rnk;


-- -----------------------------------------------------------------------------
-- Q5. How did the number of sessions change from month to month?
-- Q5. 每个月的会话数比上个月增长了多少?
-- Tech: CTE + window function LAG() OVER (ORDER BY ...).
-- -----------------------------------------------------------------------------
WITH monthly AS (
    SELECT
        DATE_FORMAT(session_started_at, '%Y-%m') AS session_month,
        COUNT(*)                                 AS sessions
    FROM listening_session
    GROUP BY DATE_FORMAT(session_started_at, '%Y-%m')
)
SELECT
    session_month,
    sessions,
    LAG(sessions) OVER (ORDER BY session_month)                       AS prev_month_sessions,
    ROUND(100 * (sessions - LAG(sessions) OVER (ORDER BY session_month))
              / LAG(sessions) OVER (ORDER BY session_month), 1)       AS growth_pct
FROM monthly
ORDER BY session_month;


-- -----------------------------------------------------------------------------
-- Q6. Among shows that are still publishing (a new episode in the last 90 days), how many
--     subscriptions are "at risk", meaning the subscriber has not listened to that show for
--     60 days (as of 2026-09-30)? Per creator, for creators with at least 30 subscriptions on
--     such shows (not 30 at-risk ones), worst first. (Assignment 1 objective O3: churn warning.)
-- Q6. 在仍在更新的节目(最近 90 天内发过新单集)里,每位创作者名下有多少订阅处于"风险"状态,
--     即订阅者在截至 2026-09-30 的 60 天内没再听过这个节目?只看在这类节目上至少有 30 个订阅的创作者
--     (是 30 个符合分析条件的订阅,不是 30 个风险订阅),风险最高的在前。(对应 A1 的目标 O3:流失预警)
-- Tech: two CTEs, INNER + LEFT JOIN on a composite key, GROUP BY, HAVING.
-- Note: dormant shows are left out on purpose, to reduce the risk of reading inactivity caused by
--       a lack of new content as subscriber disengagement.
-- 说明:有意排除断更节目,以降低把"没有新内容导致的不活跃"误读为"订阅者不再感兴趣"的风险。
-- LIMITATION (documented, query not changed or re-run):
--   * The subscription table holds the status as of the data end date (2026-09-30), not the status at
--     the time of each session. The query ignores subscription.subscribed_on, so a listener who
--     subscribed less than 60 days ago and has not played the show since is counted as "at risk"
--     although the 60-day silence is not yet observable. A stricter version would count only
--     subscriptions with subscribed_on <= 2026-08-01 (60 days before the as-of date) and treat newer
--     subscribers separately; it would also need new result screenshots and a new Part 6 plan.
-- 局限(已在报告中说明,查询未修改、未重跑):
--   * subscription 表保存的是截至数据截止日(2026-09-30)的订阅状态,不是每次播放当时的状态。
--     查询没有使用 subscribed_on,因此不足 60 天前才订阅且之后没播放的听众也会被算作"风险",
--     尽管 60 天的沉默期还没有真正发生。更稳妥的口径是只统计 subscribed_on <= 2026-08-01 的成熟订阅,
--     并把新订阅者单独处理;这需要重新截图并重做第 6 部分的执行计划。
-- -----------------------------------------------------------------------------
WITH active_shows AS (
    SELECT show_id
    FROM episode
    GROUP BY show_id
    HAVING MAX(episode_publish_date) >= DATE_SUB('2026-09-30', INTERVAL 90 DAY)
),
last_listen AS (
    SELECT
        ls.listener_id,
        e.show_id,
        MAX(ls.session_started_at) AS last_session
    FROM listening_session ls
    JOIN episode e ON e.episode_id = ls.episode_id
    GROUP BY ls.listener_id, e.show_id
)
SELECT
    cr.creator_id,
    cr.creator_name,
    cr.plan_tier,
    COUNT(*)                                                                  AS subscriptions,
    SUM(CASE WHEN ll.last_session IS NULL
              OR ll.last_session < DATE_SUB('2026-09-30', INTERVAL 60 DAY)
             THEN 1 ELSE 0 END)                                               AS at_risk,
    ROUND(100 * SUM(CASE WHEN ll.last_session IS NULL
                          OR ll.last_session < DATE_SUB('2026-09-30', INTERVAL 60 DAY)
                         THEN 1 ELSE 0 END) / COUNT(*), 1)                    AS at_risk_pct
FROM subscription sub
JOIN active_shows a  ON a.show_id    = sub.show_id
JOIN podcast_show s  ON s.show_id    = sub.show_id
JOIN creator      cr ON cr.creator_id = s.creator_id
LEFT JOIN last_listen ll ON ll.listener_id = sub.listener_id
                        AND ll.show_id     = sub.show_id
GROUP BY cr.creator_id, cr.creator_name, cr.plan_tier
HAVING COUNT(*) >= 30
ORDER BY at_risk_pct DESC, subscriptions DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q7. In each country, which devices do listeners use, and what share of the country's
--     sessions does each device have?
-- Q7. 各国听众用什么设备收听?每种设备占该国会话的多少?
-- Tech: INNER JOIN x2, GROUP BY, window function SUM(COUNT(*)) OVER (PARTITION BY ...).
-- -----------------------------------------------------------------------------
SELECT
    co.country_name,
    ls.device_type,
    COUNT(*)                                                                     AS sessions,
    ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY co.country_name), 1) AS pct_of_country_sessions
FROM listening_session ls
JOIN listener l  ON l.listener_id   = ls.listener_id
JOIN country  co ON co.country_code = l.country_code
GROUP BY co.country_name, ls.device_type
ORDER BY co.country_name, sessions DESC;


-- -----------------------------------------------------------------------------
-- Q8. Where are the gaps in the catalog? Which categories have no show attached
--     directly, and how many sub-categories do they have?
-- Q8. 目录里哪里有空缺?哪些类目下没有直接挂任何节目?它们各有几个子类目?
-- Tech: RIGHT JOIN (keeps every category, even those with no show), self-joins on the
--       hierarchy, GROUP BY.
-- -----------------------------------------------------------------------------
SELECT
    c.category_id,
    c.category_name,
    COALESCE(p.category_name, '(top level)') AS parent_category,
    COUNT(DISTINCT sc.category_id)           AS sub_categories
FROM podcast_show s
RIGHT JOIN category c  ON c.category_id = s.category_id
LEFT JOIN  category p  ON p.category_id = c.parent_category_id
LEFT JOIN  category sc ON sc.parent_category_id = c.category_id
WHERE s.show_id IS NULL
GROUP BY c.category_id, c.category_name, p.category_name;


-- =============================================================================
-- PART 6. Optimization with proof
-- 第 6 部分:优化与证据
-- =============================================================================
-- =============================================================================
-- part6_optimization.sql
-- Cloud Native Data Engineering - Assignment 2, Part 6 (Optimization, with proof)
-- 云原生数据工程 - 作业 2 第 6 部分(优化,附证据)
--
-- Run this on the LIVE RDS instance, one numbered step at a time (select the statement, press
-- the lightning bolt). Copy the FULL output of every EXPLAIN ANALYZE into your report.
-- 在你自己的 RDS 上按步骤逐条运行(选中一条语句再点闪电图标)。把每条 EXPLAIN ANALYZE 的完整输出复制进报告。
--
-- NOTE: STEPS 1-5 are the first experiment; the measurements reported in the report use STEP 6 (INVISIBLE / VISIBLE).
--       说明:第 1-5 步是最初的实验;报告中的测量数字使用第 6 步(INVISIBLE / VISIBLE 切换)。
--
-- Chosen by the student / 你选定的方案:
--   Queries to profile : Q2 (plan tiers, 5-table join) and Q6 (at-risk subscriptions, CTE + joins)
--   Index to test      : idx_session_episode_seconds ON listening_session (episode_id, listened_seconds)
--                        -> aimed at Q2 (and, as a side effect, Q1)
--
-- HOW TO GET STABLE NUMBERS / 如何得到稳定的数字:
--   * Run each EXPLAIN ANALYZE THREE times and keep the output of the LAST run. The first run
--     reads data from disk; later runs hit the buffer pool, so only warm runs are comparable.
--     每条 EXPLAIN ANALYZE 连续运行 3 次,保留最后一次:第一次要从磁盘读,之后才命中缓存,只有"热运行"才可比。
--   * Run "before" and "after" in the same session, a few minutes apart.
--     "之前"和"之后"在同一个会话里、相隔几分钟内完成。
--   * To copy the plan in Workbench: right-click the result cell -> "Copy Field (unquoted)"
--     (or "Open Value in Viewer"), then paste it into a text file.
--     在 Workbench 里复制执行计划:右键结果单元格 -> Copy Field (unquoted),再粘贴到文本文件。
-- =============================================================================
USE podcast_db;


-- ---------------------------------------------------------------------------
-- STEP 1. Indexes BEFORE the change (screenshot or paste the result into the report)
-- 第 1 步:改动之前有哪些索引
-- ---------------------------------------------------------------------------
SHOW INDEX FROM listening_session;


-- ---------------------------------------------------------------------------
-- STEP 2. BEFORE: execution plans of the two heaviest queries (run each 3 times, keep the last)
-- 第 2 步:改动之前,两条最重查询的执行计划(各运行 3 次,保留最后一次)
-- ---------------------------------------------------------------------------
-- 2a BEFORE: Q2
EXPLAIN ANALYZE
SELECT
    cr.plan_tier,
    pl.monthly_price_usd,
    COUNT(DISTINCT cr.creator_id)                                          AS creators,
    COUNT(*)                                                               AS sessions,
    ROUND(SUM(ls.listened_seconds) / 3600, 1)                              AS listening_hours,
    ROUND(SUM(ls.listened_seconds) / 3600 / COUNT(DISTINCT cr.creator_id), 1) AS hours_per_creator
FROM listening_session ls
JOIN episode      e  ON e.episode_id  = ls.episode_id
JOIN podcast_show s  ON s.show_id     = e.show_id
JOIN creator      cr ON cr.creator_id = s.creator_id
JOIN plan         pl ON pl.plan_tier  = cr.plan_tier
GROUP BY cr.plan_tier, pl.monthly_price_usd
HAVING COUNT(DISTINCT cr.creator_id) >= 20
ORDER BY hours_per_creator DESC;

-- 2b BEFORE: Q6
EXPLAIN ANALYZE
WITH active_shows AS (
    SELECT show_id
    FROM episode
    GROUP BY show_id
    HAVING MAX(episode_publish_date) >= DATE_SUB('2026-09-30', INTERVAL 90 DAY)
),
last_listen AS (
    SELECT
        ls.listener_id,
        e.show_id,
        MAX(ls.session_started_at) AS last_session
    FROM listening_session ls
    JOIN episode e ON e.episode_id = ls.episode_id
    GROUP BY ls.listener_id, e.show_id
)
SELECT
    cr.creator_id,
    cr.creator_name,
    cr.plan_tier,
    COUNT(*)                                                                  AS subscriptions,
    SUM(CASE WHEN ll.last_session IS NULL
              OR ll.last_session < DATE_SUB('2026-09-30', INTERVAL 60 DAY)
             THEN 1 ELSE 0 END)                                               AS at_risk,
    ROUND(100 * SUM(CASE WHEN ll.last_session IS NULL
                          OR ll.last_session < DATE_SUB('2026-09-30', INTERVAL 60 DAY)
                         THEN 1 ELSE 0 END) / COUNT(*), 1)                    AS at_risk_pct
FROM subscription sub
JOIN active_shows a  ON a.show_id    = sub.show_id
JOIN podcast_show s  ON s.show_id    = sub.show_id
JOIN creator      cr ON cr.creator_id = s.creator_id
LEFT JOIN last_listen ll ON ll.listener_id = sub.listener_id
                        AND ll.show_id     = sub.show_id
GROUP BY cr.creator_id, cr.creator_name, cr.plan_tier
HAVING COUNT(*) >= 30
ORDER BY at_risk_pct DESC, subscriptions DESC
LIMIT 10;


-- ---------------------------------------------------------------------------
-- STEP 3. Hypothesis and the index / 第 3 步:假设与建索引
-- Q2 joins listening_session to episode on episode_id and only needs listened_seconds from it.
-- With the foreign-key index alone, MySQL finds the matching sessions by episode_id and then reads
-- every full row from the table to get listened_seconds. A composite index (episode_id, listened_seconds)
-- contains both columns, so MySQL can answer from the index alone (a "covering index") and skip
-- the row lookups. Expected change: the access path to listening_session changes (for example from
-- "Table scan on ls" to "Covering index lookup on ls using idx_session_episode_seconds") and the time drops.
-- Your own EXPLAIN output decides what is true; write down what you actually see.
-- Q2 按 episode_id 把会话连到单集,只需要会话的 listened_seconds。只有外键索引时,MySQL 要找到会话后再回表读整行;
-- 复合索引 (episode_id, listened_seconds) 已经包含这两列,可以只读索引("覆盖索引"),省掉回表。预期:对 listening_session 的访问
-- 方式发生变化(例如从 Table scan 变成 Covering index lookup),耗时下降。以你自己的 EXPLAIN 输出为准,看到什么就如实写什么。
-- ---------------------------------------------------------------------------
CREATE INDEX idx_session_episode_seconds ON listening_session (episode_id, listened_seconds);


-- ---------------------------------------------------------------------------
-- STEP 4. Indexes AFTER the change / 第 4 步:改动之后的索引
-- NOTE: MySQL may silently drop the automatic foreign-key index fk_session_episode, because the new
-- index starts with the same column and can replace it. This is expected, not an error.
-- 注意:MySQL 可能自动删掉原来的外键索引 fk_session_episode,因为新索引的第一列相同,可以替代它。这是正常现象。
-- ---------------------------------------------------------------------------
SHOW INDEX FROM listening_session;


-- ---------------------------------------------------------------------------
-- STEP 5. AFTER: the same plans again (run each 3 times, keep the last)
-- 第 5 步:改动之后,同样的执行计划(各运行 3 次,保留最后一次)
-- ---------------------------------------------------------------------------
-- 5a AFTER: Q2
EXPLAIN ANALYZE
SELECT
    cr.plan_tier,
    pl.monthly_price_usd,
    COUNT(DISTINCT cr.creator_id)                                          AS creators,
    COUNT(*)                                                               AS sessions,
    ROUND(SUM(ls.listened_seconds) / 3600, 1)                              AS listening_hours,
    ROUND(SUM(ls.listened_seconds) / 3600 / COUNT(DISTINCT cr.creator_id), 1) AS hours_per_creator
FROM listening_session ls
JOIN episode      e  ON e.episode_id  = ls.episode_id
JOIN podcast_show s  ON s.show_id     = e.show_id
JOIN creator      cr ON cr.creator_id = s.creator_id
JOIN plan         pl ON pl.plan_tier  = cr.plan_tier
GROUP BY cr.plan_tier, pl.monthly_price_usd
HAVING COUNT(DISTINCT cr.creator_id) >= 20
ORDER BY hours_per_creator DESC;

-- 5b AFTER (side effect check: Q6 uses different columns, so it should change little): Q6
EXPLAIN ANALYZE
WITH active_shows AS (
    SELECT show_id
    FROM episode
    GROUP BY show_id
    HAVING MAX(episode_publish_date) >= DATE_SUB('2026-09-30', INTERVAL 90 DAY)
),
last_listen AS (
    SELECT
        ls.listener_id,
        e.show_id,
        MAX(ls.session_started_at) AS last_session
    FROM listening_session ls
    JOIN episode e ON e.episode_id = ls.episode_id
    GROUP BY ls.listener_id, e.show_id
)
SELECT
    cr.creator_id,
    cr.creator_name,
    cr.plan_tier,
    COUNT(*)                                                                  AS subscriptions,
    SUM(CASE WHEN ll.last_session IS NULL
              OR ll.last_session < DATE_SUB('2026-09-30', INTERVAL 60 DAY)
             THEN 1 ELSE 0 END)                                               AS at_risk,
    ROUND(100 * SUM(CASE WHEN ll.last_session IS NULL
                          OR ll.last_session < DATE_SUB('2026-09-30', INTERVAL 60 DAY)
                         THEN 1 ELSE 0 END) / COUNT(*), 1)                    AS at_risk_pct
FROM subscription sub
JOIN active_shows a  ON a.show_id    = sub.show_id
JOIN podcast_show s  ON s.show_id    = sub.show_id
JOIN creator      cr ON cr.creator_id = s.creator_id
LEFT JOIN last_listen ll ON ll.listener_id = sub.listener_id
                        AND ll.show_id     = sub.show_id
GROUP BY cr.creator_id, cr.creator_name, cr.plan_tier
HAVING COUNT(*) >= 30
ORDER BY at_risk_pct DESC, subscriptions DESC
LIMIT 10;


-- ---------------------------------------------------------------------------
-- STEP 6. FINAL PROTOCOL used for the numbers in the report (Part 6.2 to 6.6)
-- 第 6 步:报告中数字实际使用的最终实验步骤(第 6.2 到 6.6 节)
-- After STEP 3, MySQL silently removed the foreign-key index fk_session_episode (SHOW INDEX: 6 rows).
-- To compare "without" and "with" the new index in ONE session, the foreign-key index was recreated by
-- hand (SHOW INDEX: 7 rows) and the new index was switched between INVISIBLE and VISIBLE.
-- 第 3 步之后 MySQL 自动删掉了外键索引 fk_session_episode(SHOW INDEX 为 6 行)。为了在同一会话里比较"有/无"新索引,
-- 手工把外键索引建回来(SHOW INDEX 为 7 行),并让新索引在 INVISIBLE 与 VISIBLE 之间切换。
-- ---------------------------------------------------------------------------
-- 6a Recreate the foreign-key index with its original definition / 按原定义重建外键索引
CREATE INDEX fk_session_episode ON listening_session (episode_id);
SHOW INDEX FROM listening_session;                                   -- expected: 7 rows / 预期 7 行

-- 6b BEFORE: the new index is ignored by the optimizer; run the EXPLAIN ANALYZE of STEP 2a (Q2) and
--     STEP 2b (Q6) three times each and keep the third run.
-- 6b 之前:优化器忽略新索引;把第 2a 步(Q2)和第 2b 步(Q6)的 EXPLAIN ANALYZE 各运行三次,保留第三次。
ALTER TABLE listening_session ALTER INDEX idx_session_episode_seconds INVISIBLE;

-- 6c AFTER: the new index is visible again; run the same statements three times each, keep the third run.
-- 6c 之后:新索引恢复可见;同样的语句各运行三次,保留第三次。
ALTER TABLE listening_session ALTER INDEX idx_session_episode_seconds VISIBLE;


-- ---------------------------------------------------------------------------
-- OPTIONAL. Remove the experiment index and go back to the original state.
-- Because the new index replaced the foreign-key index, recreate that one FIRST, otherwise MySQL
-- refuses to drop the new index ("needed in a foreign key constraint").
-- 可选:删掉实验索引,恢复原状。因为新索引取代了外键索引,要先把外键索引建回来,否则 MySQL 不让删。
-- ---------------------------------------------------------------------------
-- CREATE INDEX fk_session_episode ON listening_session (episode_id);
-- DROP INDEX idx_session_episode_seconds ON listening_session;

