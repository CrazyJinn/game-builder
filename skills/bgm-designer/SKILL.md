---
name: bgm-designer
description: |
  推进 BgmTrack 图节点的描述段（人工生成链的 skill 侧半程）：查 Scene/BgmTrack 状态 →（无节点则自行兜底建 BgmTrack(status=0)+has_bgm 边）→ 依 Scene 氛围与章节设计简报生成音乐描述文字 prompt（乐器/节奏/情绪/时长/结构，供 Suno 类外部工具）→ 写图 prompt/description + status=1 → **把文字产出给用户**并明示归档路径 13_BGM/<name>.wav。
  音频由用户手动生成并放入预制路径（手工放入文件夹即合格，无审批）；再次触发本 skill（或 dashboard 编辑器）检测文件存在置 status=2。由 scene-design agent 编排触发（Scene → SceneLayer → BgmTrack 链），也可由用户直接触发。
argument-hint: <scene_name_or_bgm_id>
arguments:
  - scene_name_or_bgm_id
allowed-tools: Read, Bash, Write
---

# 背景音乐设计（BgmTrack 描述段 · status 0→1→2）

BGM 资产链的 skill 侧半程：**生成一段音乐描述文字**给用户 → 用户在外部工具（Suno 类）手动生成 .wav → 归档到预制路径 `13_BGM/<name>.wav` → 检测文件存在置 `status=2`。**本 skill 不生成音频**——生成与归档是用户的手工环节（手工放入即合格，无 dashboard 审批）。

> 关联：`Scene -[:has_bgm]-> BgmTrack` 1:1（sync=false，BGM 独立资产）。**缺口节点（Scene 无关联 BgmTrack）由本 skill 自行兜底建**（BGM 是场景资产，需求源于 Scene 本身）；本 skill 由 **scene-design agent 编排**（plot-design 不查不调 BgmTrack）。发布时 `chapter-publisher` 把 status=2 的 track 拷 `99_game/assets/bgm/` + manifest.bgm 图驱动更新 + 注入章 JSON scene-block.bgm。

## 参数

| 参数 | 说明 |
|------|------|
| scene_name_or_bgm_id | Scene 名（如 `酒店-客房`）或 BgmTrack 节点 ID（snowflake）。按 Scene 名推进其关联 BgmTrack；按 id 直接推进。 |

## 流程（三段式：查状态 → 完成任务 → 保存结果）

### 1. 查询目标节点状态

```cypher
// 按 Scene 名或 BgmTrack id 定位 BgmTrack
MATCH (b:BgmTrack)
WHERE b.id = '<input>' OR EXISTS {
  MATCH (s:Scene {name:'<input>'})-[:has_bgm]->(b)
}
RETURN b.id AS id, b.name AS name, b.status AS status, b.description AS description,
       b.prompt AS prompt, b.audio_path AS audio_path
LIMIT 5
```

- **status=0**：进入段 2 生成描述。
- **status=1**（描述已产出）：检查 `audio_path` 文件是否存在（见段 3b 置 2 的逻辑）；不存在则提醒用户归档路径，退出。
- **status=2**（音频已归档）：已就绪，汇报退出。
- **无节点**（按 Scene 名定位且无关联 BgmTrack；按 id 定位不存在时报错退出）：**自行兜底建**——BGM 是场景资产（需求源于 Scene 本身，非剧本）。`bgm_id` 用 `snowflake_base62.py -n 1 -q` 新生成；name 依 Scene 氛围起一个短名（如「晨离」，即 manifest 键/章 JSON track 名/wav 文件名主体）：

```cypher
// 兜底建（sync=false——BGM 独立资产不随场景编辑级联）
MERGE (b:BgmTrack {id:'<bgm_id>'})
  ON CREATE SET b.status = 0
SET b.name = '<track 名>';
MATCH (s:Scene {name:'<scene_name>'}), (b:BgmTrack {id:'<bgm_id>'})
MERGE (s)-[r:has_bgm]->(b) SET r.sync = false;
```

建完进入段 2 生成描述。

顺手查场景上下文（供创作依据）：

```cypher
MATCH (s:Scene)-[:has_bgm]->(b:BgmTrack {id:'<bgm_id>'})
RETURN s.name AS scene_name, s.atmosphere AS atmosphere, s.time_of_day AS time_of_day,
       s.description AS description;
```

### 2. 完成任务（生成音乐描述文字）

依据：Scene 的 atmosphere/time_of_day/description（**主依据**——BGM 是场景资产）+ 所属章节的设计简报情感弧（若可定位：`MATCH (ch:Chapter)-[:has_section]->(:Section)-[:contains]->(s:Scene)` 找章，Read `ch.brief_path`）。

产出**一段给外部生成工具的音乐描述 prompt**（中文，80–150 字），覆盖：
- **情绪基调**：该场景要传递的核心情绪（如「晨间慵懒、轻佻暧昧」）
- **乐器与织体**：主奏/配器建议（如「电钢琴 + 轻刷镲 + 低音贝斯」）
- **节奏与速度**：BPM 区间、律动感（如「中慢速 80-95、松散摇摆」）
- **结构**：循环友好（开头即可进入主题、尾句可接回头）、时长建议（1–2 分钟循环）
- **避免**：显著旋律人声、突兀高潮（背景音乐不抢台词）

### 3. 保存结果

#### 3a. 写图（status=1）

```cypher
MATCH (b:BgmTrack {id:'<bgm_id>'})
SET b.description = '<音乐定位描述，1-2 句>',
    b.prompt = '<段 2 产出的生成用文字>',
    b.mode = 'play',        // 可选，缺省 play
    b.loop = true,          // 可选，缺省 true
    b.status = 1;           // 文字描述已产出（等用户手动生成 wav）
```

#### 3b. 文件检测置 2（status=1 再次触发时，或用户报告已归档时）

```bash
ls '13_BGM/<name>.wav'
```

文件存在 → `SET b:BgmTrack {id:'<bgm_id>'} SET b.status = 2, b.audio_path = '13_BGM/<name>.wav'`；
不存在 → 提醒用户归档路径与文件名（`13_BGM/<name>.wav`，name 即 BgmTrack.name）。

## 汇报

列出：BgmTrack name/id、status 变化、**给用户的生成文字（prompt 全文，用户复制到外部工具）**、归档路径 `13_BGM/<name>.wav`（明确提示：生成后手动放入该路径，再触发本 skill 或在 dashboard 置 status=2）、关联 Scene。

## 参考文档

- 声音 Schema（BgmTrack 字段与 has_bgm 边）：[00_init/Schema/声音.md](../../../00_init/Schema/声音.md)
- 发布衔接：[chapter-publisher](../chapter-publisher/SKILL.md)（status=2 的 track 拷 assets/bgm + manifest 注入）
