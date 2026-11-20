// =====================================================================================
// 01_queries.cypher
// Assignment 3, Part 3 - three Cypher queries on the podcast graph (Neo4j Aura).
// 作业 3 第 3 部分 - 播客图上的 3 条 Cypher 查询。
// Graph / 图: (Creator)-[:PUBLISHES]->(Show)-[:IN_CATEGORY]->(Category)-[:SUBCATEGORY_OF]->(Category)
//             (Listener)-[:SUBSCRIBED_TO]->(Show)   (Listener)-[:LISTENED_TO]->(Show)
//             (Episode)-[:OF_SHOW]->(Show)          (Guest)-[:APPEARED_ON]->(Episode)
// Each query starts with a marker "// @Nn | title"; pipeline/08_run_cypher.py runs them one by one.
// 每条查询以 "// @Nn | 标题" 开头;pipeline/08_run_cypher.py 逐条运行。
// =====================================================================================

// @N1 | Co-subscription: which shows do the subscribers of the most-subscribed show also subscribe to? (2 hops)
// 共同订阅:订阅人数最多的节目,它的订阅者还订阅了哪些节目?(两跳)
// Caveat / 注意: popular shows co-occur more often just because they are popular; this is a "what to recommend first" list, not a measure of affinity.
MATCH (:Listener)-[:SUBSCRIBED_TO]->(top:Show)
WITH top, count(*) AS subscribers
ORDER BY subscribers DESC LIMIT 1
MATCH (top)<-[:SUBSCRIBED_TO]-(l:Listener)-[:SUBSCRIBED_TO]->(other:Show)
WHERE other <> top
RETURN top.title AS base_show, subscribers AS base_show_subscribers,
       other.title AS also_subscribed_to, count(DISTINCT l) AS shared_subscribers
ORDER BY shared_subscribers DESC, also_subscribed_to
LIMIT 5;

// @N2 | Cross-category listeners: how many listeners subscribe to shows in 1, 2, 3, ... different top-level categories?
// 跨类目听众:订阅了 1 个、2 个、3 个……不同一级类目节目的听众各有多少?
MATCH (l:Listener)-[:SUBSCRIBED_TO]->(:Show)-[:IN_CATEGORY]->(:Category)-[:SUBCATEGORY_OF*0..1]->(top:Category)
WHERE NOT (top)-[:SUBCATEGORY_OF]->()
WITH l, count(DISTINCT top) AS top_categories
RETURN top_categories AS distinct_top_categories, count(*) AS listeners
ORDER BY distinct_top_categories;

// @N3 | Guest bridges (3 hops): which guests appeared on shows of two or more different creators?
// 嘉宾桥梁(三跳):哪些嘉宾上过两位及以上不同创作者的节目?
MATCH (g:Guest)-[:APPEARED_ON]->(:Episode)-[:OF_SHOW]->(:Show)<-[:PUBLISHES]-(c:Creator)
WITH g, collect(DISTINCT c.creator_id) AS creators
WHERE size(creators) >= 2
RETURN g.guest_id AS guest_id, size(creators) AS creators_bridged, creators[0..5] AS first_creator_ids
ORDER BY creators_bridged DESC, guest_id
LIMIT 10;

// =====================================================================================
// Part 4b - three more queries for the query showcase (distinct from N1-N3).
// 第 4b 部分 - 查询展示用的另外 3 条(与 N1-N3 不重复)。
// =====================================================================================

// @N4 | Guest reach (3 hops from guest to listener): how many distinct listeners subscribe to at least one show the most-travelled guest appeared on?
// 嘉宾触达面(从嘉宾到听众三跳):出现在最多创作者节目里的那位嘉宾,有多少不同听众订阅了他上过的任一节目?
MATCH (g:Guest)-[:APPEARED_ON]->(:Episode)-[:OF_SHOW]->(:Show)<-[:PUBLISHES]-(c:Creator)
WITH g, count(DISTINCT c) AS creators ORDER BY creators DESC, g.guest_id LIMIT 1
MATCH (g)-[:APPEARED_ON]->(:Episode)-[:OF_SHOW]->(s:Show)<-[:SUBSCRIBED_TO]-(l:Listener)
RETURN g.guest_id AS guest_id, creators AS creators_bridged,
       count(DISTINCT s) AS shows_appeared_on, count(DISTINCT l) AS distinct_subscribers_reached;

// @N5 | Audience overlap (4 hops): which pairs of creators share the most subscribers (cross-promotion candidates)?
// 受众重叠(四跳):哪几对创作者共享的订阅者最多(适合交叉推广)?
MATCH (c1:Creator)-[:PUBLISHES]->(:Show)<-[:SUBSCRIBED_TO]-(l:Listener)-[:SUBSCRIBED_TO]->(:Show)<-[:PUBLISHES]-(c2:Creator)
WHERE c1.creator_id < c2.creator_id
RETURN c1.creator_id AS creator_a, c2.creator_id AS creator_b, count(DISTINCT l) AS shared_subscribers
ORDER BY shared_subscribers DESC, creator_a, creator_b
LIMIT 5;

// @N6 | One listener's neighbourhood: for the listener with the most subscriptions, list their shows, creators and listening so far
// 单个听众的"邻域":订阅数最多的听众,列出他订阅的节目、创作者和已收听情况
MATCH (l:Listener)-[:SUBSCRIBED_TO]->(:Show)
WITH l, count(*) AS n ORDER BY n DESC, l.listener_key LIMIT 1
MATCH (l)-[sub:SUBSCRIBED_TO]->(s:Show)<-[:PUBLISHES]-(c:Creator)
OPTIONAL MATCH (l)-[x:LISTENED_TO]->(s)
RETURN s.title AS show, c.creator_id AS creator_id, sub.on AS subscribed_on,
       coalesce(x.sessions, 0) AS sessions, coalesce(x.seconds, 0) AS seconds_listened
ORDER BY sessions DESC, show
LIMIT 10;
