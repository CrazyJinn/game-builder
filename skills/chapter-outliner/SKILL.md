---
name: chapter-outliner
description: |
  推进 Section 图节点的提纲段：读 structurer 的章级设计简报（含分节规划）+ 本节 Section 统合的 Scene + 分支骨架 → 自检本节 event 丰满度 →（够）按分支节点图先行/本质差异/节奏门控产出节级提纲 Markdown（拓扑骨架契约值 + authoring 人读散文，lines 仅含拓扑占位，scene-block id 用 structurer 预分配）→ 落盘 25_剧本/chapter<NN>_<章概述>/sec<MM>_<节概述>/outline.md + 兜底建 SecOutline 产物节点（Section-[:has_outline]->SecOutline）写 outline_path + status=1（提纲就绪）。
  前驱：所属 Chapter status=11（结构已批）且本节无 SecOutline 节点或 SecOutline.status∈{-1,0}。若 event 素材不足以支撑提纲，**拒绝产出**并报告缺口（不写 status），由用户补全叙事基础后重调本 skill。
argument-hint: <section_id>
arguments:
  - section_id
allowed-tools: Read, Bash, Write, Edit
---

> **status=-1 = 作废重做**：当本节 SecOutline 节点被重置为 `status=-1` 时（如 Section/Chapter 属性变更沿 has_section/has_outline 级联），即使 outline.md 已落盘，也**必须重新产出并覆盖**。`-1` 明确表示有旧产物要覆盖，**禁止因文件已存在而跳过，也禁止读旧提纲内容**，直接以当前图节点数据 + 设计简报为唯一来源重新创作。

# 节提纲（SecOutline 提纲段 · status {-1,0}→1）

剧情创作流程的**第二段**（节级，在章级结构段之后、节级定稿段之前）。读 `chapter-structurer` 产出的**章级设计简报**（取分节规划里**本节**的定位）+ 本节 `Section` 经 `contains` 统合的 Scene + 分支骨架，**先自检本节 event 丰满度**；够丰满才按**分支节点图先行 / 本质差异 / 节奏**三门控产出**节级提纲（outline.md，纯 Markdown）**——确定「本节分几个 scene 段、每段场景/时间/bgm、choice 分叉与汇合、ending 位置」，`lines` 留空（细节对话由 `chapter-dialoguer` 填）。提纲无审批，产出即兜底建 `SecOutline` 产物节点（`Section-[:has_outline]->SecOutline`）并写 `SecOutline.status=1`（提纲就绪）。

> **素材不足门控**：若本节 event 不够丰满（事件数过少 / 事件链断裂 / Choice 指向的事件缺失 / 出场角色在本节无 involved 事件），**拒绝产出提纲**——不写 status、不落盘，只产出「素材不足报告」（列缺口）返回。用户可手动跑 `nrt-narrative-grower` 补全叙事基础后，重调本 skill 复查。

## 参数

| 参数 | 说明 |
|------|------|
| section_id | Section 节点 ID（snowflake）。由 plot-design 按 has_section 遍历各节时传入。 |

## 流程（三段式：查状态 → 完成任务 → 保存结果）

> 本 skill 是 SecOutline 产物节点的创建点 + 提纲段 status 的写入点。提纲 outline.md 由本 skill 直接创作产出，无纯产出子 skill。

### 1. 查询目标节点状态

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查询。

#### 1a. 解析 Section + 所属 Chapter + SecOutline + 前驱校验

```cypher
MATCH (ch:Chapter)-[:has_section]->(sec:Section {id:'<input>'})
OPTIONAL MATCH (sec)-[:has_outline]->(ol:SecOutline)
RETURN sec.id AS id, sec.section_no AS section_no, sec.title AS title,
       sec.summary AS summary,
       ol.id AS ol_id, ol.outline_path AS outline_path, ol.status AS ol_status,
       ch.id AS ch_id, ch.chapter_no AS chapter_no, ch.title AS ch_title, ch.status AS ch_status
LIMIT 1
```

**前驱校验**：`ch.status = 11`（结构已批）AND（`ol_status IS NULL` 或 `ol_status ∈ {-1, 0}`），否则停止并提示：
- `ch.status ≠ 11` → 先完成章级结构段（`chapter-structurer`）+ 结构审。
- `ol_status` 为 `1` → 本节提纲已就绪，停止并提示（后续走 `chapter-dialoguer`）。

#### 1b. 读设计简报 + 查创作上下文

**先读章级设计简报**：Read `25_剧本/chapter<NN>_<章概述>/设计简报.md`（NN = chapter_no 零填充，<章概述> 取章 title），取出**分节规划里本节**（按 section_no 匹配）的定位——所含 Scene + **预分配 scene-block id**（本节提纲的 `scenes[].id` 必须用这些，不自创）+ 戏剧职责，以及全章的情感弧线 / 戏剧意图（本节在弧线中的位置）。简报缺失则停止并提示先跑 `chapter-structurer`。

再查图：

```cypher
// (1) 本节统合的 Scene（结构段已建 Section→contains 边）+ 视觉上下文，按 order
MATCH (sec:Section {id:'<sec_id>'})-[r:contains]->(s:Scene)
RETURN s.name AS name, s.scene_type AS scene_type, s.atmosphere AS atmosphere,
       s.time_of_day AS time_of_day, s.composition AS composition, s.lighting AS lighting,
       s.description AS description, r.order AS order
ORDER BY r.order;
```

```cypher
// (2) 分支骨架：本节 Scene 相关地点的 Choice + 结局事件
MATCH (s:Scene {name: '<scene名>'})<-[:has_scene]-(loc:Location)
MATCH (e:Event)-[:occurred_at]->(loc)
OPTIONAL MATCH (e)-[:presents]->(choice:Choice)
OPTIONAL MATCH (choice)-[op:option]->(target:Event)
RETURN e.title AS event_title, e.time AS event_time, e.ending_kind AS ending_kind,
       e.description AS event_desc, choice.name AS choice_name,
       op.label AS option_label, op.leads_to_ending AS leads_to_ending,
       target.title AS target_event, target.ending_kind AS target_ending
ORDER BY e.time LIMIT 100
```

> 角色声音（LanguageStyle）在提纲段**不查**——outline YAML 无字段承载语气；声音留给 `chapter-dialoguer` 段查用。

#### 1c. event 丰满度自检（素材不足门控）

本节提纲的剧情密度靠 event 支撑。进入段 2 创作前，先体检**本节**范围内 event 的丰满度——**不足则拒绝产出提纲**，避免为空洞骨架浪费后续立绘出图。聚焦本节 Scene 所属 Location 的 Event：

```cypher
// (1) 本节涉及的 Event 数量 + 清单（Section→contains→Scene<-has_scene-Location<-occurred_at-Event）
MATCH (sec:Section {id:'<sec_id>'})-[:contains]->(s:Scene)<-[:has_scene]-(loc:Location)
MATCH (e:Event)-[:occurred_at]->(loc)
RETURN count(DISTINCT e) AS event_count, collect(DISTINCT e.title) AS events;

// (2) Event 之间的 evt_relation 链（事件是否连贯，非孤岛）
MATCH (sec:Section {id:'<sec_id>'})-[:contains]->(s:Scene)<-[:has_scene]-(loc:Location)<-[:occurred_at]-(e1:Event)
MATCH (e1)-[:evt_relation]->(e2:Event)
RETURN count(*) AS relation_count;

// (3) Choice option 指向的 target Event 是否存在（分支是否有落点）
MATCH (sec:Section {id:'<sec_id>'})-[:contains]->(s:Scene)<-[:has_scene]-(loc:Location)<-[:occurred_at]-(e:Event)
MATCH (e)-[:presents]->(c:Choice)-[op:option]->(target:Event)
RETURN c.name AS choice, collect(op.label) AS options, collect(target.title) AS targets;

// (4) 出场角色在本节地点的 involved Event 数（角色弧有着落否）
MATCH (sec:Section {id:'<sec_id>'})-[:contains]->(s:Scene)<-[:has_scene]-(loc:Location)<-[:occurred_at]-(e:Event)<-[:involved]-(char:Character)
RETURN char.name AS char, count(DISTINCT e) AS event_count;
```

**判断（定性，不硬编码阈值）**：综合体检结果判定 event 是否够支撑本节剧情密度。命中任一即判「素材不足」：
- **event_count 明显过少**（本节每个 Scene 平均不足 ~1 个 Event，撑不起段落）
- **事件链断裂**（Event 间几乎无 evt_relation，关键转折无承接）
- **Choice 分支无落点**（option 指向的 target Event 缺失）
- **出场角色无着落**（主要角色在本节 involved 的 Event = 0，角色弧空转）

**素材不足时**：**停止——不进入段 2，不写 status、不落盘 outline.md**。产出「素材不足报告」返回，列出具体缺口（哪个维度不足 + 涉及的 Scene/角色/Choice），供用户参考补全（可手动跑 `nrt-narrative-grower`）。**禁止硬凑提纲**——空洞提纲会让后续 dialoguer 产出的对话无据可依。

**素材够时**：进入段 2 产出提纲。

### 2. 完成任务（按三门控产出节级提纲 outline.md）

据设计简报（本节在情感弧中的位置 + 戏剧职责）+ 本节 Scene 序 + 分支骨架，**先结构后内容**，三步产出节级提纲（格式见 [提纲格式.md](references/提纲格式.md)——拓扑骨架用 `key: value` 行 + 反引号标契约值，authoring 散文为 md 正文）：

#### 2a. 分支节点图先行（结构验证）

**写一句台词前先画分支拓扑**：用纸面节点图厘清本节分支结构——哪个 scene 分叉、分支在哪汇合、ending 落在哪。自检：
- **无死胡同**：每条分支最终汇合回主线或导向 ending，不存在走不通的路径。
- **自然汇合**：分支不是多条永不相交的平行线（除非有显式 BE/TE 分流设计理由）。
- **落点存在**：choice 的每个 option 跳向的 scene id 都在本节 scenes 内（跨节跳转用章内唯一 id，见 2c）。

> 详见 [references/分支结构方法论.md](references/分支结构方法论.md)「分支节点图先行」。节点图在脑内/草稿推演即可，不必落盘——避免把对话写进结构性死胡同。

#### 2b. 分支本质差异门控

对每个 `choice` 的 options 做**有意义选择测试**：选项之间必须是**戏剧本质不同**（不同价值观取向 / 不同后果路径 / 不同信息揭示），不是 flavor 级文案差异（"我来帮" vs "我晚点帮"不算）。

- 命中 flavor 级差异（表面文案不同、剧情本质相同）→ **标注问题**，在产出报告里建议用户手动补 Choice 的戏剧分化；本次先按现状产出但标记待补。

> 详见 [references/分支结构方法论.md](references/分支结构方法论.md)「分支本质差异门控」。

#### 2c. 节奏/戏剧结构 + 落盘

据设计简报的**情感弧线**安排本节 scene 序的节奏：明确本节的 turning point（转折点）/ climax（高潮）位置，让情绪有起伏而非平铺。然后产出节级 outline **md**——**拓扑骨架（`key: value` 行 + 反引号标契约值）+ `authoring` 人读散文**。

#### 拓扑骨架（dialoguer 必须原样搬到定稿；反引号内值为契约值，不得改写）

1. **节头**：一级标题 `# sec<MM> <节标题> · chapter <NN>`。
2. **资源清单**（`## 资源清单`）：`- 出场角色：`角色名``、`- 场景：`场景名``（提纲段**不列立绘变体**，细节对话段才定）。
3. **场景段**（每段一个 `## 场景段：`id``）：`id` 用设计简报分节规划里 structurer 预分配的本节 id（**不自创；全章节内唯一**）；段下 `- 场景：`场景名`(=Scene.name)` / `- 时段：` / `- BGM 倾向：`（自由散文写该场景的音乐情绪定位，如「轻快爵士、晨间慵懒」——**不是 track 名**：BGM 走图 `Scene-has_bgm->BgmTrack` 关联（scene-design 编排 `bgm-designer` 管理），发布时注入章 JSON；提纲的倾向描述供 `bgm-designer` 产 prompt 时参考）。
4. **分支拓扑**（每场景段下 `### 分支拓扑`，仅在存在分支时）：对应定稿 `lines` 占位，用 md 列表写 `choice` 的 options（label + 跳向的 scene id）、`jump` 串联、`ending` 位置与 kind（对齐 `Event.ending_kind` / `option.leads_to_ending`）；**不写 say/narrate 台词**。无分支的段此节留空（dialoguer 填逐句对话）。

> 跨节/跨章跳转：本节内用 `scene`（章内唯一 id 寻址）；跨章用 `file`（章 stem）。预分配 id 的章内唯一性保证跨节 jump 不冲突。

#### authoring 人读散文（不进定稿，仅供 dialoguer 参考；不进 schema）

- **节级**：`## 方向`（direction，一段话讲清**本节**剧情发展方向，**核心字段**）/ `## 情感弧`（emotion_arc，本节 start→end + 中途转折）/ `## 约束`（constraints，给 dialoguer 的硬约束清单）。
- **每场景段**：`### 职责`（purpose，这场戏的戏剧职责）/ `### 节拍`（beats，节拍走向，自然语言列表，**禁写台词**——给 dialoguer 节拍依据）/ `### 母题锚点`（motif_anchors）/ `### 衔接`（transition）。

字段定义详见 [提纲格式.md](references/提纲格式.md)。

#### md 写作约定（提纲不进 schema、不被代码解析，无 YAML 约束）

- **契约值用反引号**：场景段 id、scene 名、bgm track、角色名、跳转目标等需原样搬进定稿的值，一律用反引号包裹（如 `` `酒店-客房` ``），提示 dialoguer 不得改写。
- **authoring 散文自由**：direction / emotion_arc / constraints / beats 等自由换行、自由长度，不强制引号、不禁多行。
- 其余字段语义（meta.chapter/title、scenes.id 唯一、lines 仅拓扑占位）与定稿 schema 子集一致，仅载体从 YAML 改为 md。

#### 落盘

**Write**：`25_剧本/chapter<NN>_<章概述>/sec<MM>_<节概述>/outline.md`（NN=`chapter_no`、MM=`section_no` 零填充；<章概述>取章 title、<节概述>取节 title 核心主题，清洗 Windows 非法字符）。Write 自动创建章/节目录。

> 节级提纲 = 拓扑骨架契约值 + authoring 散文。`chapter-dialoguer` 读此文件，以「节拍（beats）」章节为节拍依据，在保持拓扑契约值不变的前提下填逐句台词成节级 `台词.jsonl`；**authoring 散文不搬进台词**。

### 3. 保存结果（MERGE 兜底建 SecOutline + has_outline 边 + 写 outline_path/status=1）

`--multi` 单事务，节点先于边；`ol_id` 用 `snowflake_base62.py` 新生成（已存在 SecOutline 时复用其 id）：

```cypher
// 1. MERGE 兜底建 SecOutline 产物节点（重做时复用已有节点）
MERGE (ol:SecOutline {id:'<ol_id>'})
SET ol.name = '<节标题>提纲',
    ol.outline_path = '<OUTLINE_PATH>',
    ol.status = 1;      // 提纲就绪，无审批，直接进入 chapter-dialoguer

// 2. 兜底建 has_outline 边（Section→SecOutline，sync=true：节编排变更级联作废产物链）
MATCH (sec:Section {id:'<sec_id>'}), (ol:SecOutline {id:'<ol_id>'})
MERGE (sec)-[r:has_outline]->(ol) SET r.sync = true;
```

**status 写入**：节级提纲产出 → `SecOutline.status=1`（提纲就绪）。提纲段**无审批**。Section 无 status（纯编排容器），不写。

最后汇总：提纲文件 `SecOutline.outline_path`、`SecOutline.status=1`、分支拓扑概要（分叉/汇合/ending 位置）+ 任何 flavor 级分支的待补标注。

## 参考文档

- 创作方法论：[references/分支结构方法论.md](references/分支结构方法论.md) — 节点图先行/本质差异/后果可见/节奏
- 提纲格式（outline.md 拓扑骨架 + authoring 散文）：[提纲格式.md](references/提纲格式.md)；运行时章 JSON 权威 schema：[剧本.schema.json](../../../99_game/data/剧本.schema.json)
- 剧情 Schema：[00_init/Schema/剧情.md](../../../00_init/Schema/剧情.md) — Chapter/Section/产物链（SecOutline/SecScript/LineAudio）/has_section/has_outline/produces 定义
- 上游：[chapter-structurer](../chapter-structurer/SKILL.md)（章级建结构 + 分节 + 产设计简报 → Chapter status=11）
- 下游：[chapter-dialoguer](../chapter-dialoguer/SKILL.md)（读本节提纲填细节对话 → SecScript status=10）
