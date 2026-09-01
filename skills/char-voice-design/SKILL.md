---
name: char-voice-design
description: |
  推进 VoiceDesign 图节点（角色基线音色设计）**多候选流程**：查询状态 → 生成 instruct + 统一长句 ref_text → 先合成 3 个候选 ref（voice_clone_runner design-candidates）+ 每候选 3 个情绪试听（voice_clone_runner audition，Qwen3 Base Voice Clone，均 env/.venv-qwen）落盘验证 → 后写图（MERGE 兜底建节点+has_voice_design 边，写内容+ref_audio_path+candidates_path+status=10 候选待选）。
  依据 Character 基础属性 + LanguageStyle + Info/Event，按声线三要素（音色基底/演绎方式/情绪域）生成**简明**自然语言 instruct（1-2 句、≤60 字，措辞遵循 Qwen VoiceDesign 官方原则：简洁/具体/客观，禁比喻修辞），并做同场角色频谱避让。同一 instruct × 3 次随机采样出候选（人工在 dashboard 审批中心试听 ref+情绪试听后「采用」其一，固化为 <char>_ref.wav，status 保持 10 走二审）。怪物（enemy）跳过（无台词）。在需要设计角色基线音色、或 VoiceDesign status∈{-1,0} 需推进时使用。
argument-hint: <char_id>
arguments:
  - char_id
allowed-tools: Read, Bash, Write, Edit
---

> **status=-1 = 作废重做**：当 VoiceDesign 被 sync 级联重置为 `status=-1` 时（角色属性变更沿 `has_voice_design`(sync=true) 触发），即使 instruct/ref_text 已有值，也**必须重新生成并覆盖**。`-1` 与 `0` 都视为"需生成"起点；`-1` 明确表示旧声音设计作废，**禁止因属性已有值而跳过**，也禁止读旧 instruct/旧 ref_audio（ref_audio 必须删旧文件重新合成）。

> **命名消歧**：`VoiceDesign` = 图节点（本 skill 的产物）；`Qwen VoiceDesign` = TTS 模型（合成候选 ref 的引擎）。

# 角色声音设计

推进 VoiceDesign（角色基线音色设计）图节点：生成 instruct + 统一长句 ref_text 设计描述，合成 **3 个候选 ref（同一 instruct × 3 次随机采样，24kHz）+ 每候选 3 个情绪试听（平静/高兴/愤怒，各配不同语义文本，Qwen3 Base Voice Clone）**，交 dashboard 审批中心人工采用。

**status 流转**：`0` 待设计 → `1` instruct 完成（仅文本）→ `10` 候选固化（生产完成，**直接待审，无需 submit**；由 `candidates_path` 分两态：非空=**候选待选**——dashboard 逐候选试听后「采用」（固化 `<char>_ref.wav` + 清理临时文件夹 + 删 candidates_path，status 保持 10）；空=单 ref 待审——通过 `11` / 驳回回 `0`）→ `11` 批准。下游配音（voice-publisher / section-voice-publisher）要求 `11`。`2` 为历史兼容值（旧流程的生产完成态）：存量节点 status=2 时可在 dashboard 编辑器手动「提交审批」迁到 10，**本 skill 一律写 10、不写 2**。

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| char_id | 角色节点 ID（snowflake Base62） | 必传 |

## 流程（三段式：查状态 → 完成任务（先产出物） → 保存结果（后写图））

### 1. 查询目标节点状态 + 生成素材

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查询角色 + LanguageStyle + 已有 VoiceDesign + 叙事素材（Info/Event）+ **同场角色**（频谱避让用）：

```cypher
MATCH (c:Character {id: '<char_id>'})
OPTIONAL MATCH (c)-[:has_voice_style]->(ls:LanguageStyle)
OPTIONAL MATCH (c)-[:has_voice_design]->(vd:VoiceDesign)
OPTIONAL MATCH (c)-[:link]->(info:Info)
OPTIONAL MATCH (c)-[iv:involved]->(evt:Event)
OPTIONAL MATCH (c)-[:involved]->(e2:Event)-[:link]->(evtInfo:Info)
RETURN c, ls, vd,
       collect(DISTINCT info { .title, .content, .knowledge_level }) AS infos,
       collect(DISTINCT evtInfo { .title, .content, .knowledge_level }) AS event_infos,
       collect(DISTINCT evt { .title, .description, .type, .time }) AS events,
       collect(DISTINCT iv.role) AS event_roles;
```

同场角色（查其已有 VoiceDesign 的 instruct，避免撞声）：

```cypher
MATCH (c:Character {id: '<char_id>'})-[:involved]->(e:Event)<-[:involved]-(other:Character)-[:has_voice_design]->(vd:VoiceDesign)
RETURN DISTINCT other.name AS name, vd.instruct AS instruct, vd.description AS description LIMIT 5;
```

- **目标节点判定**：
  - 若 `vd` 为空 → 生成新 snowflake id 作为 `VD_ID`（`python "${CLAUDE_SKILL_DIR}/../../scripts/snowflake_base62.py" -n 1 -q`），本次将新建；若存在 → `VD_ID = vd.id`，按 status 决定起点（`-1`/`0` 需重做）。
  - status≥10 → 已生产完成（`10` 且 `candidates_path` 非空 = **已在候选待选**，产物已落盘等 dashboard 采用；`11` 已批准），除非 `-1` 重做否则直接汇报跳过；`1`（历史中间态，仅文本）→ 视为未完成，走完整流程重新产出。
- **角色类型判断**：

  | 角色类型 | VoiceDesign |
  |---------|--------------|
  | 主角(char) / NPC | 生成 |
  | 怪物(enemy) | **不生成**（无台词无需配音，直接汇报跳过，不写任何节点） |

- 记下角色名 `c.name`（ref_audio_path 与下游 profiles JSON 的键用角色名）。

### 2. 完成任务（生成设计描述 + 合成 ref_audio —— 先产出物）

**2a. 生成三段内容**。读 [references/template-声音设计.md](references/template-声音设计.md)（**措辞原则（Qwen 官方：简洁/具体/客观）** + 声线三要素 + 六维素材映射 + 候选与试听节 + 反模式/范例），按 [references/声线变体库.md](references/声线变体库.md)（变体频段表 + 同场避让规则）校准，生成：

- `instruct`：**1-2 句自然语言、≤60 字**（Qwen VoiceDesign 消费），覆盖音色基底 / 演绎方式 / 情绪域三要素（内含六维：年龄/性别/音色/气质/语速/尾音）。超长时删修饰词与比喻、不删维度；禁比喻修辞、同义词堆砌、行为叙事（详见模板「措辞原则」与反例）。
- `ref_text`：**全角色统一通用长句**（不按角色定制、不内嵌语癖）：`上午我把书桌上的三份文件整理好，然后把水杯和钥匙放进背包，中午在城南餐厅吃了一顿面，下午再准时把报告直接交给负责人。`（54 字中性陈述、约 10~12 秒，覆盖翘舌/平舌/前后鼻音/复韵母；理由见模板 ref_text 节）。
- `description`：1-2 句音色气质概要（含依据来源，便于回溯）。

**2b. 合成候选与试听并验证落盘**。两步同 venv（env/.venv-qwen，两子命令分进程各自加载模型）：

**① 重做清理**（status∈{-1,0} 重跑**必做**——两步脚本均为「文件存在即复用」，不删旧文件就不会重新合成）：

```bash
rm -rf '14_声音设计/<角色名>/candidates'
rm -f '14_声音设计/<角色名>/<角色名>_ref.wav'
```

**② design-candidates**（Qwen 同一 instruct × 3 次采样出候选 ref 24k + manifest）：

```bash
# 写 99_game/data/.cache/voice-candidates-<角色名>.json，内容：
# { "<角色名>": { "instruct": "<instruct>", "ref_text": "<ref_text>", "candidates_dir": "14_声音设计/<角色名>/candidates", "count": 3 } }

env/.venv-qwen/Scripts/python.exe "${CLAUDE_SKILL_DIR}/../section-voice-publisher/scripts/voice_clone_runner.py" design-candidates \
  --profiles '99_game/data/.cache/voice-candidates-<角色名>.json'
```

**③ audition**（每候选 3 情绪试听「平静/高兴/愤怒」，Qwen3 Base Voice Clone——README「Voice Design then Clone」流程：`create_voice_clone_prompt(ref, ref_text)` + `generate_voice_clone`；**无 instruct 通道，情绪靠试听句文本语义自适应**）：

```bash
env/.venv-qwen/Scripts/python.exe "${CLAUDE_SKILL_DIR}/../section-voice-publisher/scripts/voice_clone_runner.py" audition \
  --manifest '14_声音设计/<角色名>/candidates/candidates.json'
```

产物落 `14_声音设计/<角色名>/candidates/`（临时文件夹，dashboard 采用后整夹删除；设计阶段不产 16k 文件）：`<角色名>_c1..c3_ref.wav`（3 候选，24kHz 原生）+ `<角色名>_cN_平静/高兴/愤怒.wav`（9 试听）+ `candidates.json`（manifest，audition 回填路径）。

**校验**：`candidates.json` 存在；3 个 `_cN_ref.wav` 与 9 个 `_cN_<情绪>.wav` 各 >10KB（`ls -la '14_声音设计/<角色名>/candidates/'`）。**任一失败则停止、不写图**，报告失败原因与排查指引（env/.venv-qwen 环境 / settings.json `voice.model_dir`，见 [15_声音/README.md](../../../15_声音/README.md)）。

### 3. 保存结果（后写图，节点不存在则兜底创建）

产出物就绪后才写图（status 固定 `10`：候选固化即待选即待审，**不写 1 也不写 2**）：

```cypher
MERGE (v:VoiceDesign {id: '<VD_ID>'})
  ON CREATE SET v.status = 0;
MATCH (c:Character {id: '<char_id>'}), (v:VoiceDesign {id: '<VD_ID>'})
MERGE (c)-[r:has_voice_design]->(v) SET r.sync = true;
MATCH (v:VoiceDesign {id: '<VD_ID>'})
SET v.name = '<角色名>声音设计',
    v.instruct = '...',
    v.ref_text = '...',
    v.ref_audio_path = '14_声音设计/<角色名>/<角色名>_ref.wav',
    v.candidates_path = '14_声音设计/<角色名>/candidates/candidates.json',
    v.description = '...',
    v.status = 10;
```

> `ref_audio_path` 提前写惯例正式路径（此刻文件尚不存在，无害——下游配音门是 status=11；dashboard「采用」时固化为该路径，下游 voice_clone_runner publish 以 24k 原生直接消费，无重采样副产物）。不写 `clone_prompt_path`：Qwen3 Base clone 的 prompt 在合成时内存构建、不落盘 `.pt`，该字段为遗留兼容字段（见 [声音.md](../../../00_init/Schema/声音.md) 废弃说明）。

### 4. 汇报

列出：角色名、VD_ID、新建/复用、instruct 全文、ref_text、候选数（3）与试听数（9，Qwen3 Base 引擎）、manifest 路径（candidates.json）、status=10（候选待选）。附提示：到 dashboard 审批中心（声音审）逐候选试听 ref + 3 情绪试听 →「采用」（固化为 `<角色名>_ref.wav` 并清理临时文件夹，status 仍 10）→ 二审通过→11（下游配音要求 11）/驳回→0；三个候选都不理想可驳回后重跑本 skill（候选会重新采样覆盖）。注意向用户说明：**试听与下游配音同引擎（Qwen3 Base Voice Clone）、同 ref+ref_text**——试听即成品引擎的真实预览；情绪演绎靠文本语义自适应（配音期由 tts_text 变体承载），试听句的韵律表现可直接外推到成品。

## 参考文档

- [声音设计模板](references/template-声音设计.md)——措辞原则（Qwen 官方：简洁/具体/客观，≤60 字硬约束）+ instruct 三要素组织 + 素材映射 + 反模式 + 合规短版/过度设计对照范例
- [声线变体库](references/声线变体库.md)——变体频段表（御姐/少年/萝莉/叔音…）+ 同场角色频谱避让规则
- 基线音色 Schema：[00_init/Schema/声音.md](../../../00_init/Schema/声音.md)（VoiceDesign 节点 + has_voice_design 边 + status=10 两态 + 审批门）
- 现有 instruct 范例：见模板「范例」节（陆择/顾盈/伊芙）
