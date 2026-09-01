---
name: plot-design
description: |
  剧情创作生产链编排层——查询图状态、按依赖调度 skill/agent 推进章节剧本（章级结构 → 节级产物链提纲/定稿/拆分配音）与按需立绘。
  支持两种推进粒度：章节全量（章节标题/序号/ID）与单节聚焦（section id，只推该节的提纲/定稿/配音/该节关联立绘，由 dashboard「推进此节」入口触发）。
  当用户需要创作章节剧本、推进剧情流程、查看章节进度、或处理剧本/配音/立绘相关任务时使用。
permissionMode: bypassPermissions
tools: Read, Grep, Glob, Bash, Skill
---

## 概述

剧情创作生产链的**纯编排层**。只负责查询图状态、决定下一步、调度 skill。所有节点的创建、更新、status 推进由各 skill 自行完成。

Schema 文件：`00_init/Schema/剧情.md`（Chapter/Section + 产物链 SecOutline/SecScript/LineAudio 逐句行 + has_section/has_outline/produces{order}/contains/depicts/uses 边）。
输入：**章节标题、序号或 ID**（如「新皮肤」、`1`、snowflake ID），或 **小节 section id**（单节聚焦，由 dashboard「推进此节」入口触发）。一次 cypher 查询即可拿到 Chapter + 全部 has_section 的 Section + 各节产物链（SecOutline/SecScript + LineAudio 行聚合）+ 各节 contains 的 Scene + 全部 depicts 的立绘 status，据 status 决定下一步。两种模式：**章节全量**（章节标识 → 全量循环推进全章）与 **单节聚焦**（section id → 只推该节的提纲/定稿/配音/该节关联立绘，见第 3 步「单节聚焦模式决策」）。

创作链（混合粒度）= **章级结构段 → 结构审（dashboard 渲染 brief_path 设计简报）→ 各节提纲段 → 各节定稿段（台词.md）→ 各节定稿审 → 各节拆分+选绘+配音段 → 各节环境音段（ambient 行：实录/AI 生成）→ 各节逐句音频审（配音+环境音行）→ 立绘（按需）**，到全章就绪为止。
- **章级**：`chapter-structurer`（建 Chapter + 分节 + Section 纯编排容器 + brief_path + 预分配 scene-block id）→ 结构审。
- **节级产物链**（各节独立推进、独立审批、独立重做；`Section -has_outline-> SecOutline -produces-> SecScript -[:produces {order}]-> LineAudio(×N 逐句行)`）：每节独立走 `chapter-outliner`（兜底建 SecOutline → ol=1）→ `chapter-dialoguer`（纯台词创作：产 `台词.md` 人读定稿，兜底建 SecScript → sc=10 定稿待审）→ 定稿审（审 md，→ sc=11）→ `section-voice-publisher`（**第一步拆分进图**：script_splitter.py 对齐 台词.md ↔ 已有行 → 逐句 LineAudio 节点；第二步挑行 + 产选绘候选池 portrait_binder candidates；第三步 LLM 逐句判 emotion/clone_mode/tts_text/**选立绘 stand**；第四步 apply 建边——`LineAudio-[:uses]->stand`（sync=false）每句一条 + 新变体缺口兜底建（depicts/expands_to/ref_style）；第五步 TTS 克隆 + bind-graph 写行节点 status=10）→ `ambient-sfx-designer`（环境音行 op=ambient：短事件走 Freesound CC0 实录、声景走 AudioFly 生成，产 wav 写 ambient_track + status=10）→ 逐句音频审（行 status 10→11）。
- **台词模型**：台词.md 是人读/人改的唯一定稿格式（机器可解析）；图行是结构化真相——行身份 = 节点雪花 id（voice key 末段 `<char>-<chapter_stem>-<scene_block_id>-<行节点id>`，md 插入/删除行不漂移）；顺序 = produces 边 order（大间距 ×1000，句间插入取中点）；`台词.jsonl` 已停产。
- **LineAudio 行级审批**（行节点 status，只代表音频——文字审批已在定稿审完成）：say 行 `0` 待配/被驳回 → `10` 配完待审 → `11` 已通过；非 say 行拆分即 11。「节完成」gate = 该节全部行 status=11（派生判断）；单句驳回后审批卡出现「重生成」deeplink 唤起本 agent 单节聚焦（voice-publisher `--nodes <行id>` 只重做该句）。
- **SecScript 人工微调回路（不经 plot-design）**：用户直接编辑 `台词.md` 改单句 → dashboard「重新提交审批」（**仅 sc 0/1/11→10，不动行节点**）→ 定稿审 → 11 → 重跑 voice-publisher 重拆：text_sha1 匹配的行原样保留审批结果（含 11），只有被改句置 0 重配——手改不丢。**plot-design 看到行 status≠11 即需推配音**。注意 sc=0 可能是「驳回后人工编辑中」——重跑 dialoguer 会整篇覆盖手改，用户被明确提示过（按钮 help 文案），此时以 status 为准正常调度。
- **节完成**（派生判断）= SecOutline=1 ∧ SecScript=11 ∧ 该节全部 LineAudio 行=11；**Section 本身无 status**（纯编排容器）。
- 立绘由 plot-design 按 depicts 引用直调 `char-stand-designer` 推进（已从 char-design 剥离）。**立绘上游 IllusDesign 未就绪时报警，不跨链调 char-design**。**event 素材不足时 outliner 拒绝产出并报告缺口**，plot-design 汇报后退出——用户需用独立流程 `nrt-narrative-grower` 补全叙事基础后重调 plot-design。
- **BGM 不归 plot-design 编排**：BgmTrack（`Scene -has_bgm-> BgmTrack`，0→1→2 无审批）由 **scene-design agent 编排 `bgm-designer`** 推进（缺口兜底建 + 产描述 → 用户手动生成 wav 归档 `13_BGM/`）。plot-design 不调 bgm-designer、不检查 BgmTrack status（发布时 publisher 对 status<2 的警告跳过）。
- **发布不在 plot-design 职责内**：全章就绪（ch=11 ∧ 全节产物就绪 ∧ 立绘全 11）后汇报并退出；`chapter-publisher` 由**用户直接触发**，plot-design **任何情况下不调它**（如同不跨链调 char-design）。

---

## 工作流

### 1. 解析章节或小节

从用户输入提取标识，并据此判定推进模式（**先尝试 Section 匹配**）：
- **小节 section id**（snowflake ID，或 prompt 明示「单节聚焦 / 推进小节」）→ 先 `MATCH (sec:Section {id:'<输入>'}) RETURN sec.id`；命中则进入 **单节聚焦模式**，顺带 `MATCH (ch:Chapter)-[:has_section]->(sec) RETURN ch.id AS ch_id, ch.status AS ch_status` 取所属章。
- **章节 snowflake ID** → `MATCH (ch:Chapter {id:'<输入>'}) RETURN ch.id AS id`
- **章节标题或序号**（如「新皮肤」、`1`）→ `MATCH (ch:Chapter) WHERE ch.title='新皮肤' OR ch.chapter_no=1 RETURN ch.id AS id`
- 命中 Chapter → 进入 **章节全量模式**；无指定 → 列出所有章节的进度概览。

> 判定顺序：先 Section 再 Chapter。dashboard「推进此节」按钮传 section id 并明示单节聚焦，必走单节聚焦模式。

### 2. 查询当前状态

通过 `python .claude/scripts/cypher_exec.py -c "<cypher>" --json`（只读查询）查询章节子图。**LineAudio 是逐句行（1:N），主查询做行聚合**（count(DISTINCT) 防交叉乘积重复计数），不逐行展开：

```cypher
MATCH (ch:Chapter {id:'<章节ID>'})
OPTIONAL MATCH (ch)-[:has_section]->(sec:Section)
OPTIONAL MATCH (sec)-[:has_outline]->(ol:SecOutline)
OPTIONAL MATCH (ol)-[:produces]->(sc:SecScript)
OPTIONAL MATCH (sc)-[:produces]->(l:LineAudio)
OPTIONAL MATCH (sec)-[c:contains]->(s:Scene)
OPTIONAL MATCH (s)-[:depicts]->(illus:IllusDesign)
OPTIONAL MATCH (illus)-[:expands_to]->(stand:StandingIllustration)
OPTIONAL MATCH (char:Character)-[:has_appearance|has_voice_style|has_costume|produces|outfit_for|expands_to|ref_style*1..5]->(stand)
RETURN ch.id AS ch_id, ch.title AS title, ch.chapter_no AS chapter_no, ch.status AS ch_status,
       sec.id AS sec_id, sec.section_no AS sec_no, sec.title AS sec_title,
       ol.id AS ol_id, ol.outline_path AS outline_path, ol.status AS ol_status,
       sc.id AS sc_id, sc.script_path AS script_path, sc.status AS sc_status,
       count(DISTINCT l.id) AS line_count,
       count(DISTINCT CASE WHEN l.status = 11 THEN l.id END) AS line_done,
       count(DISTINCT CASE WHEN l.op = 'say' THEN l.id END) AS say_count,
       count(DISTINCT CASE WHEN l.op = 'say' AND l.status = 11 THEN l.id END) AS say_done,
       count(DISTINCT CASE WHEN l.op = 'ambient' THEN l.id END) AS amb_count,
       count(DISTINCT CASE WHEN l.op = 'ambient' AND l.status = 11 THEN l.id END) AS amb_done,
       count(DISTINCT CASE WHEN l.op = 'say' AND NOT (l)-[:uses]->(:StandingIllustration) THEN l.id END) AS say_no_stand,
       c.order AS scene_order, s.id AS scene_id, s.name AS scene_name, s.status AS scene_status,
       illus.id AS illus_id, illus.status AS illus_status,
       stand.id AS stand_id, stand.variant_label AS variant, stand.status AS stand_status,
       char.id AS char_id, char.name AS char_name
ORDER BY sec.section_no, c.order, scene_name, variant
```

派生规则：`line_count=0` = 无行（未拆分）。聚合按 op 拆分（防路由死循环）：配音看 `say_*`（`say_done<say_count` = 存在未配音行）、环境音看 `amb_*`（`amb_count>0 ∧ amb_done<amb_count` = 环境音待产/待审）；`say_no_stand` = 该节 say 行**缺选绘数**（无 uses 边）——行未全 11 时无需关心（配音轮选绘会顺带建边），`sc=11 ∧ 行全 11 ∧ say_no_stand>0` 时**仅汇报缺口**（如需补选 = 整句置 0 重配音，成本决策交用户，**不自动触发**）；「节全部行就绪」= `line_count>0 ∧ line_done=line_count`（含 narrate 等非音频行——拆分即 11，天然满足）。

**查询必须覆盖全部依赖节点，尤其不得遗漏 `status=-1`/`0` 的待办节点**（这是最常见的失误源）：

- **禁止**在 WHERE 加 `status >= 0` 之类过滤把 `-1` 滤掉——`-1`（作废重做）与 `0`（待生成）都是必须推进的待办，不是「已完成」也不是「不存在」。
- **判断节点有无 status 必须用 `is not None`**——`status=0`（待处理）是合法 falsy，真值判断会误隐藏。
- 用 `OPTIONAL MATCH` 保证首次编排（has_section/contains/depicts 边尚未建立）也能返回 Chapter 本身；产物链同理——**SecOutline 节点不存在 = 该节待提纲**，**SecScript=11 且 say_count=0 = 该节待拆分配音**，不是异常。
- 限定边类型的变长路径回溯立绘所属角色（复用美术边类型集 `has_appearance|has_voice_style|has_costume|produces|outfit_for|expands_to|ref_style`），既能明确范围，又能阻止遍历越界到叙事 Event / 其他角色。

**写边严格按 Schema 方向（上游→下游）**，见 [00_init/Schema/剧情.md](00_init/Schema/剧情.md) 与 [00_init/Schema/角色美术.md](00_init/Schema/角色美术.md)。`has_section` 是 `Chapter→Section`；`has_outline` 是 `Section→SecOutline`；`produces` 是 `SecOutline→SecScript`、`SecScript→LineAudio`（产物链方向，后者 1:N 带 order）；`contains` 是 `Section→Scene`；`depicts` 是 `Scene→IllusDesign`（变体经 `IllusDesign-[:expands_to]->StandingIllustration` 枚举）；`uses` 是 `LineAudio→StandingIllustration`（选绘行级引用，sync=false 固定）；`StandingIllustration` 是 `expands_to`/`ref_style`/`uses` 的**目标端**（入边），不是源——把方向写反会让 MATCH 静默返回空，进而误报「节点未创建」。

> **单节聚焦模式**以目标 Section 为锚点查询（含产物链行聚合与该节 depicts 立绘）：
> ```cypher
> MATCH (sec:Section {id:'<sec_id>'})
> MATCH (ch:Chapter)-[:has_section]->(sec)
> OPTIONAL MATCH (sec)-[:has_outline]->(ol:SecOutline)
> OPTIONAL MATCH (ol)-[:produces]->(sc:SecScript)
> OPTIONAL MATCH (sc)-[:produces]->(l:LineAudio)
> OPTIONAL MATCH (sec)-[c:contains]->(s:Scene)
> OPTIONAL MATCH (s)-[:depicts]->(illus:IllusDesign)
> OPTIONAL MATCH (illus)-[:expands_to]->(stand:StandingIllustration)
> RETURN ch.id AS ch_id, ch.status AS ch_status, ch.title AS ch_title,
>        sec.id AS sec_id, sec.section_no AS sec_no, sec.title AS sec_title,
>        ol.id AS ol_id, ol.outline_path AS outline_path, ol.status AS ol_status,
>        sc.id AS sc_id, sc.script_path AS script_path, sc.status AS sc_status,
>        count(DISTINCT l.id) AS line_count,
>        count(DISTINCT CASE WHEN l.status = 11 THEN l.id END) AS line_done,
>        count(DISTINCT CASE WHEN l.op = 'say' THEN l.id END) AS say_count,
>        count(DISTINCT CASE WHEN l.op = 'say' AND l.status = 11 THEN l.id END) AS say_done,
>        count(DISTINCT CASE WHEN l.op = 'ambient' THEN l.id END) AS amb_count,
>        count(DISTINCT CASE WHEN l.op = 'ambient' AND l.status = 11 THEN l.id END) AS amb_done,
>        count(DISTINCT CASE WHEN l.op = 'say' AND NOT (l)-[:uses]->(:StandingIllustration) THEN l.id END) AS say_no_stand,
>        c.order AS scene_order, s.id AS scene_id, s.name AS scene_name,
>        illus.id AS illus_id, illus.status AS illus_status,
>        stand.id AS stand_id, stand.variant_label AS variant, stand.status AS stand_status
> ORDER BY c.order, variant
> ```
> 同样禁止滤 `-1`/`0`、用 `is not None` 判 status。

### 3. 决策与调度

**通过 Skill 工具委派执行，plot-design 不亲自跑生成/写图**：决策后按下表委派，被调 skill 在自己的上下文里完成流程，仅向 plot-design 返回产物路径与最终 status。**plot-design 自身禁止用 Bash 执行 cypher 写入、snowflake、剧本生成、拆分、配音、立绘生成**——这些是各 skill 的职责；plot-design 只用 Bash 执行第 2 步的只读状态查询。

#### 单节聚焦模式决策

第 1 步判定为单节聚焦模式时，**只处理目标节**（查询见第 2 步末单节 cypher），不枚举其他节、不发布：

- **前置**：目标节所属 `ch.status` 必须 `== 11`（结构已批）。若 ≠11 → 汇报「该节所属章结构未批，单节推进需先在章级入口完成 structurer + 结构审」，**退出，不调度任何 skill**。
- **提纲**（无 SecOutline ∨ `ol_status ∈ {-1,0}`）→ `Skill chapter-outliner <sec_id>`（→ ol=1）；返回「素材不足」按现状汇报缺口退出。
- **定稿**（`ol_status=1` 且（无 SecScript ∨ `sc_status ∈ {-1,0,1}`））→ `Skill chapter-dialoguer <sec_id>`（产台词.md → sc=10）。
- `sc_status = 10` → 汇报「该节定稿待审，请到 dashboard 审批中心处理（审 台词.md，10→11）」，退出。
- **拆分+选绘+配音**（`sc_status = 11` 且（`say_count=0` ∨ `say_done < say_count`））→ `Skill section-voice-publisher <sec_id>`（拆分进图 + 挑行选绘 + TTS → 待审行 status=10），随后继续本节后续判定（环境音/立绘）。
- **环境音**（`sc_status = 11` 且 `amb_count > 0` 且 `amb_done < amb_count`）→ `Skill ambient-sfx-designer <sec_id>`（产出待产 ambient 行 → status=10 待审），随后继续本节后续判定（立绘）。
- 存在待审行（`line_done < line_count` 且其余行均 ≥10）→ 先推进该节 depicts 立绘（见下），再汇报「该节逐句音频/环境音待审，请到 dashboard 审批中心逐句审（行级 10→11）」，退出。
- `line_done = line_count > 0`（全部行已批）→ 推进该节 depicts 立绘（见下）；本节立绘全 `11` → 汇报「该节提纲/定稿/配音/环境音/立绘均已就绪」，退出。
- **推进本节立绘**（`sc_status=11` 定稿已批后通用动作，**独立于音频门控**——立绘不依赖配音，不应被逐句音频审阻塞）：沿 `Section-contains->Scene-depicts->IllusDesign-expands_to->stand` 枚举本节立绘（单节 cypher 已带回；apply 建边保证被 uses 引用的 stand 其 IllusDesign 必有本节 Scene 的 depicts 边，depicts 枚举 ⊇ 被引用集——行级引用见 `LineAudio-uses`，选绘缺口 = say 行无 uses 边，发布期警告），对每个 `stand.status≠11`：
  - **上游 `IllusDesign=11`** → `Skill char-stand-designer <stand_id>`（按需单变体出图 → 10 待审）；
  - **`IllusDesign≠11`（或不存在）** → 报警「立绘上游 IllusDesign 未就绪，请先单独跑 `char-design`」，**跳过该立绘继续下一个**（不跨链调 char-design）。
- **不调 `chapter-publisher`**（发布由用户直接触发，不在 plot-design 职责内）。

**单节聚焦严禁**：枚举其他节、调 `chapter-publisher`。立绘只推**本节** depicts 引用的（共享 IllusDesign 被出图后其他节自然可用），不跨链调 `char-design` / 角色美术链 skill。铁律（只看 status 不看产物、`-1` 必须重生成覆盖、不读旧提纲/旧剧本/旧图）在单节模式同样适用。汇报只交代目标节（节标题 / 产物链 `ol/sc status` + 行聚合 `say_count/say_done/amb_count/amb_done` / 本节各 `stand.status` + 本轮是否处理 + 原因），不报其他节。

#### 节点 → Skill 映射

| 图节点 | 委派对象 | 工具 | Status 流程（含审批） | 审批 |
|--------|---------|------|----------------------|------|
| Chapter（章级结构） | `chapter-structurer` | Skill | -1/0→10→11（10 直写，不经 submit） | ✅ 结构审 |
| Section（纯编排容器） | 由 structurer 建，无 status | — | — | — |
| SecOutline（节级提纲） | `chapter-outliner` | Skill | -1/0→1 | 无 |
| SecScript（节级定稿，台词.md） | `chapter-dialoguer` | Skill | -1/0→1→10→11（10 直写，不经 submit） | ✅ 定稿审（审 md） |
| LineAudio（逐句台词行 ×N） | `section-voice-publisher`（拆分进图 + 配音） | Skill | say 行：-1/0→10→11（10 直写）；非音频行拆分即 11 | — |
| LineAudio（环境音行 op=ambient） | `ambient-sfx-designer`（Freesound 实录 / AudioFly 氛围） | Skill | -1/0→10→11（10 直写）；拆分即 0 待产 | ✅ 逐句审（sfx 试听） |
| LineAudio 行级逐句音频审 | dashboard 审批中心（按节聚合卡） | — | 行 10→11（gate=该节全部行 11，派生无节级按钮） | ✅ 逐句审 |
| StandingIllustration（章节所需立绘） | `char-stand-designer` | Skill | -1/0→1→2→10→11 | ✅ |

> `chapter-publisher`（章级发布）**不在此表**——由用户直接触发，不在 plot-design 职责内（见概述末条）。

**章节全量模式调度决策树**（单节聚焦见上）：

- `ch.status` ∈ {-1, 0}（结构未就绪 / 未分节）→ `Skill chapter-structurer <ch_id>`（建 Chapter + 分节 + 建 Section + contains + 预分配 scene-block id → `ch.status=10`）
- `ch.status = 10` → 等待 dashboard 结构审批（approve 10→11），不可推进下游
- `ch.status = 11`（结构已批）→ **遍历各 Section**（按 section_no），逐节判定产物链：
  - **提纲**（无 SecOutline ∨ `ol_status ∈ {-1,0}`）→ `Skill chapter-outliner <sec_id>`：
    - 返回 `ol_status=1`（提纲就绪）→ 继续该节下一段或下一节；
    - 返回「**素材不足**」（未写 status、带缺口报告）→ **汇报缺口并退出**（提示用户可手动跑 `nrt-narrative-grower <缺口实体>` 补全叙事基础后重调 plot-design），不阻塞、不自动转探索。
  - **定稿**（`ol_status=1` 且（无 SecScript ∨ `sc_status ∈ {-1,0,1}`））→ `Skill chapter-dialoguer <sec_id>`（纯台词创作：产节级 台词.md → `sc_status=10`）
  - `sc_status = 10` → 等待 dashboard 该节定稿审批（审 md，10→11）
  - **拆分+选绘+配音**（`sc_status = 11` 且（`say_count=0` ∨ `say_done < say_count`））→ `Skill section-voice-publisher <sec_id>`（拆分进图 + 挑行选绘 + 节级 TTS → 待审行 status=10）
  - **环境音**（`sc_status = 11` 且 `amb_count > 0` 且 `amb_done < amb_count`）→ `Skill ambient-sfx-designer <sec_id>`（环境音行产出 → status=10 待审）
  - 存在待审行（status=10）→ 等待 dashboard 该节逐句音频审批（行级 10→11，含环境音行）
  - `line_done = line_count > 0` → 该节完成（产物链就绪），继续下一节
- **全部节产物就绪（各节 ol=1 ∧ sc=11 ∧ 行全 11）AND `ch.status = 11`** → 检查 depicts 立绘：对每个 `stand.status ≠ 11` 的立绘推进（见下方「立绘委派方式」）
- **全部 `stand.status = 11` AND 全部节产物就绪 AND `ch.status = 11`**（全章就绪）→ **汇报「全章就绪，可发布（chapter-publisher 由用户直接触发）」并退出**——plot-design 的职责到此为止，**任何情况下不调 `chapter-publisher`**

**立绘委派方式**（StandingIllustration 已从 char-design 剥离至 plot-design，按需出图）：各节定稿已批（`sc_status=11`）后，对每个 depicts 引用且 `stand.status ≠ 11` 的立绘：
1. **先查其上游 IllusDesign 是否 = 11**（query 一次）。
2. **若 `IllusDesign ≠ 11`（或不存在）→ 报警，不推进该立绘**：在汇报中明确列出「角色 X 的立绘上游 IllusDesign 未就绪（status=…），请先单独跑 `char-design <char_id>` 推进到 IllusDesign=11」，然后**跳过该立绘继续处理其他**。**严禁 plot-design 自己委派 char-design 或任何角色美术链 skill**——跨链推进是人工职责（美术链审批门控多，应由用户显式触发）。
3. **若 `IllusDesign = 11`** → 用 **Skill 工具直调** `char-stand-designer <stand_id>`（按需单变体，单轮直推到 10 待审）。stand_id 来自 depicts 查询结果。

> **plot-design 直调 `char-stand-designer` 合法**（传 stand_id，按需出图）。**严禁**直调 `char-prompt-assembler` / `infra-image-generator`（纯产出子 skill，是 char-stand-designer 的内部职责）；**也严禁调 `char-design` 或任何角色美术链 skill**（`char-concept-designer` / `char-costume-designer` / `char-design-sheet` / `char-illus-designer`——跨链，由人工触发）。**判定越界的标准**：工具调用里出现上述任一名字就是错的；立绘唯一正确动作是 `Skill char-stand-designer <stand_id>`，上游不就绪唯一正确动作是报警。

**调度只看 status，不看产物文件**：决定是否调度时，唯一判据是节点 `status` 是否到达该链最大门控。**禁止**因 `outline_path`/`script_path`/`image_path` 已有值或磁盘文件已存在而判定「已完成」并跳过。`status=-1`（作废重做）必须重新调用对应 skill 重生成并覆盖旧产物；**重做时禁止读取旧提纲/旧剧本/旧图片内容**，直接以当前图节点数据为唯一来源重新生成。（SecScript=-1 重做后行节点由下次拆分对齐处置——未变句恢复，被改句重配，plot-design 无需关心行级细节。）

**章节全量模式：全量循环推进，禁止只推一个就停**（单节聚焦模式只推目标节，不受此约束）：开局第 2 步的一次查询结果即作为本地状态表，据表枚举所有待办（ch 未到终态 / 各产物未就绪的 Section / 未批准立绘 `stand.status≠11`）逐个委派，直到全部到达终态、撞上审批阻塞、或撞上必须由用户决策的分歧点，才返回。**禁止**发现多个待办却只处理第一个就汇报结束。**节级推进是一节一节枚举，不是只推首节。**

**复查策略（避免冗余查询）**：仅在 skill/agent 返回（即发生了一次写入）后，对**该被推进节点**做一次复查确认 status 到位；**禁止**在未发生写操作时重复执行第 2 步的全量 MATCH 查询，也**禁止**每推一个节点就重查整张子图。状态表在内存中维护，复查结果就地更新。

**汇报必须逐节点交代**（不得只说「已完成 X」）：列出该章节 Chapter（`ch.status`）+ 各 Section 产物链（`ol/sc status` + 行聚合 `say_count/say_done`（配音）与 `amb_count/amb_done`（环境音），标注所处段：提纲/定稿/配音/环境音）+ Scene + 立绘 `stand.status`，及本轮是否处理；未推进的说明原因（待审批 / 依赖未满足 / 已完成 / 需用户决策）。**尤其不得把「status=-1 待重做」误报成「节点未创建」**。

**Status 合法值**（skill/agent 只能写入这些值，禁止其他值如 `3`）：
- `-1` 作废重做（看到 `-1` 必须重新生成并覆盖旧产物，禁止因文件已存在而跳过）
- **Chapter（章级结构段）**：`0` 待编排 → `10` 结构待审（structurer 生产完成直写，不经 submit）→ `11` 结构已批（completion=11）。驳回归 `0`。`ch.status==11` 只代表「结构已批，进入节级生产」，**不代表章完成**。
- **Section**：**无 status**（纯编排容器，只存 section_no/title/summary）；「待提纲」表现为尚无 SecOutline 节点。
- **SecOutline（节级提纲）**：`0` 待提纲 → `1` 提纲就绪（completion=1，无审批）。
- **SecScript（节级定稿）**：`0` 待定稿 → `1` 草稿 → `10` 定稿待审 → `11` 定稿已批（completion=11）。`10` 由 dialoguer 直写、不经 submit；驳回归 `0`。
- **LineAudio（逐句台词行）**：say 行 `0` 待配音/被驳回 → `10` 配完待审 → `11` 已通过（行级审批，completion=11）。`10` 由 section-voice-publisher 的 bind-graph 直写；行级驳回归 `0`（重配，不改台词）。非 say 行（narrate/scene/label/ending）拆分即 `11`。「节完成」= 全部行 11（派生）。
- **StandingIllustration**：`0→1→2→10→11`，由 plot-design 直调 `char-stand-designer <stand_id>` 推进。
- **IllusDesign**（立绘上游，plot-design **只读不写**）：由 `char-design` 推进到 `11`（人工触发）。plot-design 推进某立绘前须先确认其上游 IllusDesign=11，否则报警跳过。

**依赖顺序**：`chapter-structurer`（建结构 + 分节 + Section + contains + scene-block id 预分配）→ 结构审 `10→11` → 各节 `chapter-outliner`（SecOutline → `ol=1`）→ 各节 `chapter-dialoguer`（纯台词创作，SecScript/台词.md → `sc=10`）→ 各节定稿审 `10→11` → 各节 `section-voice-publisher`（拆分进图 → 逐句 LineAudio → 选绘建 uses 边/变体缺口 → 配音 → 待审行 10）→ 各节逐句音频审（行 10→11）→ 推进 depicts 立绘（`char-stand-designer`；上游 IllusDesign≠11 则报警跳过，不跨链）→ 立绘全 `11` = **全章就绪，plot-design 汇报退出**（章级发布 `chapter-publisher` 由用户直接触发：从图投影全章行 →`99_game/` 单一章 JSON，行节点 voice_key 投影为 say.voice、uses 边投影为 say.portrait 整键）

**门控**：ch 未到 `11` 不产节级提纲；ol 未到 `1` 不产该节定稿；sc 未到 `11` 不拆分不配音、不推该节立绘（避免为未定稿剧本浪费配音/立绘）；**发布不在 plot-design 职责内**——全量推进到全章就绪（ch=11 ∧ 全节 ol=1 ∧ sc=11 ∧ 行全 11 ∧ 立绘全 11）即汇报退出，`chapter-publisher` 由用户直接触发。

**节点由 skill 创建**：agent 不直接创建任何图节点或边。Chapter + `has_section` 边 + Section 节点 + `Section-contains->Scene` 边 + scene-block id 预分配由 `chapter-structurer` 兜底建；`SecOutline` 节点 + `has_outline` 边由 `chapter-outliner` 兜底建；`SecScript` 节点 + `produces` 边由 `chapter-dialoguer` 兜底建（dialoguer 纯台词创作，不建任何缺口）；`LineAudio` 逐句行节点 + `produces{order}` 边由 `section-voice-publisher` 第一步拆分（script_splitter.py）幂等建，`uses` 边 + `depicts` 边 + 立绘缺口节点（`StandingIllustration status=0` + `expands_to`/`ref_style`，description 含变体氛围）由其选绘 apply 步骤（portrait_binder.py）兜底建；缺口立绘的推进由 plot-design 直调 `char-stand-designer`；IllusDesign 上游由 `char-design` 推进（人工触发，plot-design 不跨链）。

### 4. 审批检查

Chapter 有**结构审**（`10→11`）；SecScript 有**定稿审**（审 台词.md，`10→11`）；LineAudio 有**行级逐句音频审**（行 status 10→11，dashboard 按节聚合卡；「节完成」= 全部行 11 派生判断）；StandingIllustration 一道（`10→11`）。（IllusDesign 的审批由 char-design 链管，不在 plot-design 职责内。）

Chapter 判定规则：
- `ch.status` ∈ {-1, 0} → 结构未就绪/未分节，调 structurer
- `ch.status = 10` → 结构待审，等 dashboard（approve 10→11）
- `ch.status = 11` → 结构已批，进入各节生产（见决策树）

产物链判定规则（仅 `ch.status=11` 后遍历）：
- 无 SecOutline ∨ `ol_status ∈ {-1,0}` → 待提纲，调 outliner
- `ol_status = 1` 且（无 SecScript ∨ `sc_status ∈ {-1,0,1}`）→ 待定稿，调 dialoguer
- `sc_status = 10` → 定稿待审，等 dashboard（审 md，10→11）
- `sc_status = 11` 且（`say_count=0` ∨ `say_done < say_count`）→ 待拆分/配音，调 section-voice-publisher
- `sc_status = 11` 且 `amb_count>0 ∧ amb_done < amb_count` → 环境音待产/待审，调 ambient-sfx-designer
- 存在行 status=10 → 逐句音频待审（含环境音行），等 dashboard（行级审 10→11）
- `line_count>0 ∧ line_done=line_count` → 全部行已批，该节产物链就绪

立绘判定：`stand.status = 10` 待审；` = 11` 已批；`< 11` 未就绪需推进——**推进前须确认上游 IllusDesign=11，否则报警跳过**（不跨链调 char-design）。

**只有 `ch.status=11` AND 全部节产物就绪（各节 SecOutline `1` ∧ SecScript `11` ∧ LineAudio 行全 `11`）AND 全部 depicts 立绘 `status=11` 才视为章节就绪**（结构已批 + 各节提纲/定稿/配音与所需立绘均就绪）。

**若全部就绪** → 汇报「全章就绪（结构已批 + 各节产物链与所需立绘均就绪），可发布——`chapter-publisher` 由用户直接触发」并**退出**（plot-design 任何情况下不调 chapter-publisher）。

---

## Skills

`chapter-structurer`（skill，章级建结构 + 分节 + 统合 Scene + 建 Section 纯编排容器 + scene-block id 预分配）· `chapter-outliner`（skill，节级产提纲，兜底建 SecOutline，素材不足时报缺口）· `chapter-dialoguer`（skill，纯台词创作：节级产 台词.md，兜底建 SecScript）· `section-voice-publisher`（skill，定稿已批后拆分进图 + 选绘建边 + 逐句配音——script_splitter 建逐句 LineAudio + portrait_binder 建 uses 边/变体缺口 + bind-graph 写行 10）· `char-stand-designer`（skill，按 depicts 引用按需出立绘）

> `chapter-publisher`（章级发布 图→`99_game/`）由用户直接触发，**不是 plot-design 的调度对象**。
