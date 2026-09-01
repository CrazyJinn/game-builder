---
name: chapter-dialoguer
description: |
  推进 Section 图节点的定稿段：读 structurer 的章级设计简报 + outliner 的本节提纲 outline.md → 创作逐句对话 → 产出节级 台词.md（人读/人改的唯一定稿格式：场景二级标题「## <scene_block_id> <Scene 名>（<时段>）」、说话行「角色名:台词」**不写 [表情] 标注**——专注台词创作，演出层（表情/立绘变体）与台词分离、旁白行「旁白:叙述」、选择/分支/结局标记）→ 兜底建 SecScript 产物节点（SecOutline-[:produces]->SecScript）写 script_path + status=10（定稿待审，直写不经 submit）。
  台词.md 是正式定稿格式：dashboard 定稿审渲染它；审批通过（sc=11）后由 section-voice-publisher 第一步拆分进图（script_splitter.py → 逐句 LineAudio 节点）再配音。BGM 不归本 skill（BgmTrack 由 scene-design 编排 bgm-designer 管理）。
  前驱 SecOutline.status=1（提纲就绪）。创作中若发现 outline 戏剧性破碎（分支无本质差异/scene 无情绪推进），产出「结构性问题报告」回退 outliner，不写 status。
argument-hint: <section_id>
arguments:
  - section_id
allowed-tools: Read, Bash, Write, Edit
---

> **status=-1 = 作废重做**：当本节 SecScript 节点被重置为 `status=-1` 时（如 SecOutline/Section/Chapter 属性变更沿 produces/has_outline/has_section 级联），即使 `台词.md` 已落盘，也**必须重新创作并覆盖**（重走 0→10）。`-1` 明确表示有旧产物要覆盖，**禁止因文件已存在而跳过，也禁止读旧台词内容**，直接以当前图节点数据 + 本节 outline.md + 章级设计简报为唯一来源重新创作。

# 节细节对话（SecScript 定稿段 · status 0→10）

剧情创作流程的**第三段**（节级）。读 `chapter-structurer` 的**章级设计简报**（情感弧/戏剧意图）+ `chapter-outliner` 的**本节提纲 outline.md**，创作逐句对话，产出节级 **`台词.md`**——人读/人改的定稿 Markdown（**机器可解析**：审批通过后由 section-voice-publisher 拆分进图）。落盘 `25_剧本/`（**创作/审阅区，非运行时**）。

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| section_id | Section 节点 ID（snowflake） | 必传 |

## 流程（三段式：查状态 → 完成任务 → 保存结果）

> 本 skill 是 SecScript 产物节点的创建点 + 定稿段 status 的唯一写入点；台词.md 由本 skill 直接创作产出。编剧是高自由度创作任务，**无纯产出子 skill**——创作与写图都在本 skill 内完成。

### 1. 查询目标节点状态

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查询。

#### 1a. 解析 Section + SecOutline + SecScript + 前驱校验

```cypher
MATCH (ch:Chapter)-[:has_section]->(sec:Section {id:'<input>'})
OPTIONAL MATCH (sec)-[:has_outline]->(ol:SecOutline)
OPTIONAL MATCH (ol)-[:produces]->(sc:SecScript)
RETURN sec.id AS id, sec.section_no AS section_no, sec.title AS title,
       ol.outline_path AS outline_path, ol.status AS ol_status,
       sc.id AS sc_id, sc.script_path AS script_path, sc.status AS sc_status,
       ch.chapter_no AS chapter_no
LIMIT 1
```

**前驱校验**：`ol_status = 1`（提纲就绪，`outline_path` 非空），否则停止并提示先完成本节提纲段（`chapter-outliner`）。`sc_status` 为 `10/11` → 定稿已待审/已批，停止并提示。

#### 1b. 读设计简报 + 本节提纲 + 查创作上下文

**先读两份创作依据**：
- Read `25_剧本/chapter<NN>_<章概述>/设计简报.md`（NN = chapter_no 零填充，<章概述> 取章 title）——取出情感弧线 / 戏剧意图 / 设计支柱（本节在弧线中的位置靠分节规划定位），本节对话的情感基调全靠它。
- Read **本节** `outline.md`（`SecOutline.outline_path`）——场景分段（Scene 名/时段/scene-block id 契约值）、分支拓扑（choice/label/ending）必须如实体现到台词.md（见格式规范）；`authoring` 散文（方向/情感弧/约束/职责/节拍/母题锚点/衔接）是创作指引，不进台词；「BGM 倾向」是散文参考（BGM 由 scene-design 编排管理，与本 skill 无关）。

任一缺失则停止并提示先跑上游（structurer / outliner）。

再查图：

```cypher
// 出场角色 + 语言习惯（创作对话的核心依据）——图关系遍历，不按名字列表猜：
// 本节包含的场景 ← 地点 ← 在此地发生的_event ← 参与的角色
MATCH (sec:Section {id:'<input>'})-[:contains]->(s:Scene)<-[:has_scene]-(loc:Location)
MATCH (loc)<-[:occurred_at]-(e:Event)<-[:involved]-(char:Character)
OPTIONAL MATCH (char)-[:has_voice_style]->(voice:LanguageStyle)
RETURN DISTINCT char.name AS name, char.description AS description, char.character_tags AS tags,
       voice.vocabulary AS vocabulary, voice.rhythm AS rhythm,
       voice.habits AS habits, voice.emotion_patterns AS emotion_patterns,
       voice.description AS voice_desc
LIMIT 20
```

### 2. 完成任务（创作细节对话）

读本节 outline.md 逐场景段，据章级设计简报（情感弧/戏剧意图）+ 角色 LanguageStyle，创作逐句对话写入 `台词.md`。

#### 台词.md 格式规范（正式定稿格式，机器可解析）

```markdown
# <节标题>

## <scene_block_id> <Scene 名>（<时段>）

环境音:<短事件语义描述（转场型：极短音播完自动接下一句台词/旁白，1~2 秒）>
旁白:<叙述文本，一行一句>
<角色名>:<台词>
旁白:<叙述文本>【环境音:<持续声景语义描述（氛围型：与该旁白同出，约 5 秒）>】

**选择**
- <选项文本> → <去向：label 名 / 场景:<scene_block_id> / 结局:<kind>>
- <选项文本> → <去向>

**分支:<label 名>**

<角色名>:<台词>
旁白:<叙述>

**结局**:<BE|TE|HE|NE>——<落点一句话>
```

1. **场景二级标题**：`## <scene_block_id> <Scene 名>（<时段>）`——scene_block_id 照搬 structurer 预分配值（如 `s00_酒店`，章内唯一），Scene 名/时段照搬提纲契约值。括号时段仅供人读（运行时时段以 Scene.time_of_day 为准，拆分进图不存）。
2. **说话行**：`角色名:台词`——一行一句，冒号用**半角**，角色名用 Character.name 原名（「旁白」是保留字）。**禁止写 `[表情]` 标注**（如 `[微笑]`）：本 skill 专注台词创作，演出层（立绘变体选择）与台词**彻底分离**——由 section-voice-publisher 配音判断期为每句 say 行按台词氛围选定（`LineAudio-[:uses]->StandingIllustration` 边），md 不承载任何演出标注。**残留 `[表情]` 会在拆分时报错**（parse_md 拒绝带方括号的说话行，报行号+原文）。pos 不进 md（拆分时定）。
3. **旁白行**：`旁白:叙述`——一行一句，承载环境/动作/心理等非台词叙述。
4. **环境音两型**（都只写声音语义、不写资产名；下游按型分流：转场短事件 → Freesound 实录，氛围声景 → AudioFly 生成）：
   - **转场型**（独立行）：`环境音:语义描述`——极短声音（1~2 秒）运行时**播完再接下一句**台词/旁白（如推门风铃/开门吱呀/远处闷雷）。进图为独立 `op=transition` 行（转场音效），与旁白同级别。用于场景切换的声音信号、或某句前的短促事件音。
   - **氛围型**（旁白内嵌）：`旁白:叙述正文【环境音:语义描述】`——约 5 秒的持续声景与该旁白**同出**（如雨声/街道底噪/电流嗡鸣/引擎轰鸣逼近）。拆分时标注剥离挂到该旁白行节点（图上同一节点，`ambient_text` 字段），投影为旁白前自动触发 sfx。**一行至多一个内嵌标注**；正文剥离标注后不得为空。
   **克制使用**——只标记叙事上有意义的声音（不是每段旁白都配），与「短节克制手法」取向一致。
5. **选择块**：`**选择**` + 选项列表 `- 选项文本 → 去向`（去向 = label 名 / `场景:<scene_block_id>` / `结局:<kind>`）。**本块暂不进图**（choice 建模后续设计）——按提纲如实记录拓扑去向，供人读与后续 choice 设计。
6. **分支行**：`**分支:<label 名>**` 加粗行标示分支正文起点（进图 op=label）。
7. **结局行**：`**结局**:<kind>——<落点一句话>`（进图 op=ending）。
8. **覆盖完整**：提纲全部场景段、分支、结局都要写，不得增删场景/分支。
9. **情感递进**：每个场景内部情绪有起伏（不是平铺），对齐设计简报情感弧线的该段位置。
10. **机器可解析（硬约束）**：台词.md 是 section-voice-publisher 拆分进图（`script_splitter.py parse_md`）的输入——行型严格依赖行首标记（`##`/`**`/`旁白:`/`环境音:`/`角色名:`），**台词正文中不得出现行首 `##`、`**`、`- ` 等行型前缀**（换行重写）；无法解析的行会在拆分时报错（行号+原文），拆分前必须修 md。「旁白」「环境音」均为保留字，角色不得使用这两个名字。
11. **Write 落盘**：`25_剧本/chapter<NN>_<章概述>/sec<MM>_<节概述>/台词.md`（与该节 outline.md 同目录）。`SecScript.script_path` 指向此 `.md` 路径。Write 自动创建章/节目录。

#### 创作质量自检（发现 outline 破碎 → FAIL 报告）

创作完成后自检，若发现**根本问题在 outline 而非台词**——即 outline 戏剧性破碎，再怎么写也写不出合格对话：
- 分支 options 无戏剧本质差异（outliner 的本质差异门控漏过的 flavor 级分支）
- scene 间无情绪推进（提纲本身平铺，无 turning point/climax）
- 拓扑死胡同或 ending 缺落点

→ **触发创作质量 FAIL**：**不落盘定稿、不写 SecScript status**，产出「结构性问题报告」返回，列出破碎点（哪个 choice/scene/拓扑 + 为什么写不出合格对话）。由 plot-design 接住后把 `SecOutline.status` 归 `0`（待提纲），重调 `chapter-outliner` 重做本节提纲。**与 outliner 素材不足报告对称**——不硬凑烂对话交付。

> 通过自检才进段 3 写图。

### 3. 保存结果（写图：MERGE 兜底建 SecScript + produces 边 + 写 script_path/status）

`--multi` 单事务；`sc_id` 用 `snowflake_base62.py` 新生成（已存在 SecScript 时复用其 id）：

```cypher
// 1. MERGE 兜底建 SecScript 产物节点
MERGE (sc:SecScript {id:'<sc_id>'})
SET sc.name = '<节标题>定稿',
    sc.script_path = '<script_path>',   // 25_剧本/.../台词.md
    sc.status = 10;            // 定稿待审（直写不经 submit）

// 2. 兜底建 produces 边（SecOutline→SecScript，sync=true：改提纲级联作废定稿+全部台词行）
MATCH (ol:SecOutline {id:'<ol_id>'}), (sc:SecScript {id:'<sc_id>'})
MERGE (ol)-[r:produces]->(sc) SET r.sync = true;
```

> BGM 不在本 skill 职责内：BgmTrack（Scene-has_bgm->BgmTrack）由 **scene-design agent 编排 `bgm-designer`** 统一管理（缺口兜底、描述生成、wav 归档检测），plot-design 与本 skill 均不查不调。

**status 写入**：固定 `SecScript.status=10`（定稿待审，等 dashboard `approve`→`11`）；创作质量 FAIL → 不写 status（见段 2 末尾）。

最后汇总：定稿 `SecScript.script_path`（台词.md）、`SecScript.status=10`、说话行/旁白行/场景段计数。若触发创作质量 FAIL，汇总「结构性问题报告」而非定稿路径。

## 参考文档

- 剧情 Schema：[00_init/Schema/剧情.md](../../../00_init/Schema/剧情.md) — Section/产物链（SecOutline/SecScript/LineAudio 逐句行）/produces{order}/stages 边
- 上游：[chapter-structurer](../chapter-structurer/SKILL.md)（章级设计简报）/ [chapter-outliner](../chapter-outliner/SKILL.md)（本节提纲 → SecOutline status=1）
- 下游：[section-voice-publisher](../section-voice-publisher/SKILL.md)（sc=11 后拆分进图 + 配音）；拆分解析器 [script_splitter.py](../section-voice-publisher/scripts/script_splitter.py)（parse_md——格式规范的机器侧权威）
