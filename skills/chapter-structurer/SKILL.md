---
name: chapter-structurer
description: |
  推进 Chapter 图节点的结构段：解析/创建 Chapter → 校验 Scene 前驱 → 把 N 个 Scene 按情感弧规划成若干节（Section）→ 为每节建 Section 节点 + has_section/contains 边 + 预分配全章 scene-block id（章内唯一）→ 产出章节设计简报（含分节规划）→ Chapter status=10（结构待审，生产完成直写，无 submit 步）。Section 是纯编排容器（无 status），节级产物节点（SecOutline/SecScript/LineAudio）由下游生产 skill 兜底建。
  在需要建立章节结构或重做章节结构时使用。设计简报供下游 chapter-outliner / chapter-dialoguer 对齐。
argument-hint: <chapter_id_or_title>
arguments:
  - chapter_id_or_title
allowed-tools: Read, Bash, Write
---

> **status=-1 = 作废重做**：当 Chapter 被 sync 级联或手动重置为 `status=-1` 时，即使 has_section/contains 边 + 设计简报已存在，也**必须重新分节、重新统合 Scene、重新产出设计简报并覆盖**（重走 0→10）。重做时先删除旧 has_section 边 + DETACH DELETE 旧 Section 节点**及其下游产物链**（SecOutline/SecScript/LineAudio，分节可能变，旧产物全部作废）再重建；设计简报直接覆盖。禁止因产物已存在而跳过。

# 章节结构（Chapter 结构段 · status 0→10）

剧情创作流程的**第一段**（章级）。建立章节骨架并锚定创作意图：创建/补全 Chapter 节点的编排属性 + 把本章 N 个 Scene 按情感弧**规划成 K 个节**（每节建 `Section` 节点 + `has_section` 边，节内 Scene 用 `contains` 边统合；Section 是纯编排容器——只存 section_no/title/summary，**无 status、无产物路径**，节级产物链 SecOutline/SecScript/LineAudio 由下游 skill 兜底建）+ **预分配全章 scene-block id**（章内唯一，下游 outliner/dialoguer 的段 id 来源）+ **产出章节设计简报**（全链路创作意图的唯一锚点），推进到 `Chapter.status=10`（结构待审，直写不经 submit）。**不创作对话**。

> 结构段只定 Scene 序 + 分节，不定分支拓扑（分支/结局拓扑由 chapter-outliner 在节级提纲里定）。

## 参数

| 参数 | 说明 |
|------|------|
| chapter_id_or_title | Chapter 节点 ID（snowflake）或 title 或 chapter_no。首次创建时调用方需在 prompt 中提供 `title`/`chapter_no`/`summary`/`branch_summary`，缺失则停止。 |

## 流程（三段式：查状态 → 完成任务 → 保存结果）

> 本 skill 是 Chapter 结构段 status 的写入点 + Section 节点的创建点 + 设计简报的产出点。不调子 skill。

### 1. 查询目标节点状态

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查询。

#### 1a. 解析或创建 Chapter

```cypher
MATCH (ch:Chapter) WHERE ch.id='<input>' OR ch.title='<input>' OR ch.chapter_no=<input>
RETURN ch.id AS id, ch.title AS title, ch.chapter_no AS chapter_no,
       ch.summary AS summary, ch.branch_summary AS branch_summary,
       ch.status AS status
LIMIT 1
```

- **已存在**：用其 `id` + `summary` 作为统合依据。`status=-1` 进入重做（段 3 先清旧 has_section 边 + 删旧 Section 及其下游产物链）。
- **不存在**（首次创建）：需从调用方（plot-design agent / 用户）获取 `title`/`chapter_no`/`summary`/`branch_summary`；缺失则停止并提示。生成新 id：
  ```bash
  python "${CLAUDE_SKILL_DIR}/../../scripts/snowflake_base62.py" -n 1 -q
  ```

#### 1b. 查候选 Scene + 前驱校验

从 `summary` 提及的地点名查 Scene：

```cypher
MATCH (s:Scene)
WHERE s.name STARTS WITH '<地点名>'
RETURN s.name AS name, s.scene_type AS scene_type, s.atmosphere AS atmosphere,
       s.time_of_day AS time_of_day, s.composition AS composition, s.lighting AS lighting,
       s.description AS description, s.status AS status
ORDER BY s.name LIMIT 50
```

> **前驱校验**：所选 Scene 的 `status` 必须为 `1`（已完成）。`status=0/-1` 表示场景未就绪，停止并提示先推进 `scene-designer`。

### 2. 完成任务（编排章节结构 + 分节规划 + 产出设计简报）

#### 2a. 选 Scene + 排序 + 分节规划

据 `summary` 的叙事范围，从候选 Scene 选定本章统合的 N 个 Scene，排定 `order`（按本章剧情首次出现顺序，从 0 起）。

然后**按情感弧把有序 Scene 列表切成 K 个连续段，每段一节**：
- 每节定 `section_no`（章内从 0 起）、`title`（节标题）、`summary`（本节戏剧职责一句话）。
- 分节依据是情感弧的段落感（一个情绪单元 / 一个叙事小目标），不是机械等分。**线性章节可只分 1 节**（K=1 合法）。
- 节是 Scene 序的**连续切片**，不交错（节 A 含 order 0–2，节 B 含 3–5）。
- **预分配全章每个 scene-block 的 id**：为每个 Scene 在剧本里的首次出现分配一个**章内唯一**的段标识（下游 outliner/dialoguer 直接用它做 `scenes[].id`，保证跨节 jump 与发布时拍平合并不冲突）。命名建议 `s<MM>_<short>`（MM=节序零填充，short=简短标识），如 `s00_酒店`、`s01_路口`。

> 这一步确定「本章分几节、每节含哪些 Scene（按 order）、每节的 scene-block id」。分支拓扑留给 outliner。

#### 2b. 产出章节设计简报（全链路创作意图锚点）

下游 outliner/dialoguer 都读它对齐——**这是"本章要表达什么"的唯一显式记录**。基于 `summary` + 所选 Scene + 分节规划推导，Write 产出 `25_剧本/chapter<NN>_<章概述>/设计简报.md`（NN = `chapter_no` 零填充），含**五节**：

- **设计支柱**（3–5 个不可妥协的玩家体验/情感目标）——本章必须传递什么。
- **情感弧线**（本章情绪起点→终点的轨迹 + 关键转折点）。
- **戏剧意图**（本章在整部作品里的任务：建立什么 / 转折什么 / 收束什么）。
- **本章核心循环**（galgame 适配：即时体验段 / 本章节目标 / 长期留存钩子）。
- **分节规划**（逐节列出：`section_no` / `title` / `summary` / 所含 Scene（按 contains order）+ 预分配 scene-block id / 该节在全章情感弧中的位置）。分节规划是 outliner 按节产提纲、dialoguer 按节定稿的依据。

> 每节怎么写详见 [references/设计简报方法论.md](references/设计简报方法论.md)——产出前读它（含「分节规划」写法）。简报是创作锚点不是剧本，保持精炼。

### 3. 保存结果（MERGE 兜底 + 建 Section + 写 status）

`--multi` 单事务，节点先于边；`status=-1` 重做时先删旧 Section 及其下游产物链（SecOutline/SecScript/LineAudio）再重建：

```cypher
// 0.（仅 status=-1 重做时）清旧 has_section 边 + 删旧 Section 的产物链 + DETACH DELETE 旧 Section
//    （分节可能变，旧产物全部作废；DETACH DELETE 只删 Section 本身，产物链须显式先删）
MATCH (ch:Chapter {id:'<chapter_id>'})-[r:has_section]->() DELETE r;
MATCH (ch:Chapter {id:'<chapter_id>'})-[:has_section]->(sec:Section)
OPTIONAL MATCH (sec)-[:has_outline|produces*1..3]->(p)
DETACH DELETE p;
MATCH (ch:Chapter {id:'<chapter_id>'})-[:has_section]->(sec:Section) DETACH DELETE sec;

// 1. Chapter 编排属性 + brief_path + status=10（不再写 outline_path/script_path——产物路径已下放 SecOutline/SecScript 节点）
MATCH (ch:Chapter {id:'<chapter_id>'})
SET ch.title = '<title>',
    ch.chapter_no = <chapter_no>,
    ch.summary = '<summary>',
    ch.branch_summary = '<branch_summary>',
    ch.brief_path = '25_剧本/chapter<NN>_<章概述>/设计简报.md',   // dashboard 结构审渲染简报内容的数据源
    ch.status = 10;    // 结构待审（生产完成直写，无 submit 步），待 dashboard approve→11

// 2. 每节：MERGE Section（纯编排，无 status）+ has_section(sync=true)；节内每 Scene：contains(order,sync=false)
//    （对 K 个节循环；每个 sec_id 用 snowflake_base62.py 新生成）
MERGE (sec:Section {id:'<sec_id>'});
MATCH (sec:Section {id:'<sec_id>'})
SET sec.section_no = <MM>, sec.title = '<sec_title>', sec.summary = '<sec_summary>';
MATCH (ch:Chapter {id:'<chapter_id>'}), (sec:Section {id:'<sec_id>'})
MERGE (ch)-[r:has_section]->(sec) SET r.sync = true;
//    节内每个 Scene（按 order）：
MATCH (sec:Section {id:'<sec_id>'}), (s:Scene {name:'<scene_name>'})
MERGE (sec)-[r:contains]->(s) SET r.order = <order>, r.sync = false;
```

> `has_section` 边 `sync=true`（组成关系：人改 Chapter 属性时级联重置 Section 及其产物链→-1）；`contains` 边 `sync=false`（编排引用，不级联）。Section 无 status——「待提纲」表现为**尚无 SecOutline 节点**（由 chapter-outliner 兜底建）。

**status 写入**：结构段完成 → `Chapter.status=10`（结构待审，直写不经 submit）。后续由 dashboard `approve` 10→11（结构已批），才进入各节的 `chapter-outliner`。

最后汇总：设计简报路径 `25_剧本/chapter<NN>_<章概述>/设计简报.md`（已写入 `ch.brief_path`，dashboard 结构审渲染简报全文）、分节列表（section_no/title/所含 Scene+order+预分配 id）、Chapter `status=10`（结构待审）、K 个 Section（纯编排容器）。

## 参考文档

- 创作方法论：[references/设计简报方法论.md](references/设计简报方法论.md) — 设计支柱/情感弧线/戏剧意图/核心循环/分节规划各节写法
- 剧情 Schema：[00_init/Schema/剧情.md](../../../00_init/Schema/剧情.md) — Chapter/Section/产物链（SecOutline/SecScript/LineAudio）/has_section/has_outline/produces/contains 定义、status 流转
- 场景美术 Schema：[00_init/Schema/场景美术.md](../../../00_init/Schema/场景美术.md) — Scene 字段
- 下游：[chapter-outliner](../chapter-outliner/SKILL.md)（读设计简报 + 结构批 status=11 后按节产出提纲）
