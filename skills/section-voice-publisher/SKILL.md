---
name: section-voice-publisher
description: |
  把单节已批定稿（SecScript.status=11 的 台词.md）拆分进图、逐句选立绘并克隆 TTS 语音：
  ① 拆分对齐进图（script_splitter.py：台词.md ↔ 已有 LineAudio 逐句行对齐——新增建节点+produces{order 中点}、修改沿用节点置 0、删除 DETACH DELETE、级联作废未变句恢复，幂等）→
  ② 挑行（图查 say 行 status∈{0,-1}——待配/被驳回/stale/级联作废均归一于此）+ 产选绘候选池（portrait_binder candidates：每 (scene_block, who) 沿 Scene-depicts→expands_to 列已有立绘；池空按场景事件 wears 优先、兜底 has_costume 选定 IllusDesign）→
  ③ LLM 逐句判别 emotion（12 词表）+ clone_mode（icl/xvec 演绎通道）+ 产 tts_text 配音变体（原文加省略号/叹号等语气符号）+ 选立绘 stand（按台词氛围为每句 say 行选 StandingIllustration，池中无贴切变体则提新变体）→
  ④ apply 确定性建边（portrait_binder apply：`LineAudio-[:uses {sync:false}]->stand` 每句一条 + 新变体兜底建 StandingIllustration(status=0) + expands_to/ref_style + Scene-depicts->IllusDesign）→
  ⑤ Qwen3 单 venv（env/.venv-qwen，voice_clone_runner.py）：ensure-ref 出/复用 ref → publish 按 Qwen3 Base Voice Clone 逐句克隆（输入 tts_text 变体承载情绪，clone_mode 逐句选演绎通道：icl=ref 韵律迁移缺省 / xvec=仅说话人向量文本主导演绎；emotion 仅作图标注）→
  母带落 15_声音/<chapter_stem>/<scene_block_id>/<key>.wav（按章节/场景块归档，key 自身即含两段信息） → bind-graph 写回图行节点（voice_key/emotion/tts_text/clone_mode/attempts/text_sha1/status=10 待审）。不拷运行时副本——dashboard 逐句审批试听直接读母带，99_game/assets/ 只由 chapter-publisher 发布时按 status=11 收录（立绘整键由发布期沿 uses 边投影）。
  voice key = <char>-<chapter_stem>-<scene_block_id>-<行节点id>（节点 id 即行身份，插入/删除行不漂移）。在单节定稿已批、需要拆分/选绘/配音或重配被驳回/已改句时使用（由 plot-design 单节聚焦触发）。
argument-hint: <section_id>
arguments:
  - section_id
allowed-tools: Read, Bash, Write, Edit
---

# 节级拆分进图 + 配音发布（SecScript 定稿 → 逐句 LineAudio → 行级 TTS）

把**单节已批定稿**（`SecScript.status=11` 的 `台词.md`）先**拆分对齐进图**（逐句 LineAudio 节点 + `SecScript-[:produces {order}]->LineAudio`），再对图中 say 行按需克隆 TTS 语音，行级结果写回图节点属性：
按本节出场角色 `VoiceDesign`，用 [voice_clone_runner.py](scripts/voice_clone_runner.py) ensure-ref 出/复用 ref_audio → 同脚本 `publish` 逐句 clone（Qwen3 Base Voice Clone，输入 tts_text 变体承载情绪，均 env/.venv-qwen）→ 母带落 `15_声音/<chapter_stem>/<scene_block_id>/`（按章节归档），再用 [voice_bundler.py](scripts/voice_bundler.py) `bind-graph` 给每个（重）生成行写节点属性（`status=10` 待审）。**不拷运行时副本**：dashboard 逐句审批试听直接读母带 `15_声音/`；`99_game/assets/voices|sfx` 只由 chapter-publisher 发布时按 `status=11` 收录（`voice_bundler.py publish`），未批音频不进成品目录。

> **拆分幂等**（script_splitter.py 对齐算法）：台词.md 与图行按签名（op+who+text）difflib 对齐——未变行原样保留（级联 -1 的未变 say 行且 wav 在 → 恢复 10，**resubmit 微调回路下未变行连 status 都不动**，已批 11 保持）；text 变化行沿用节点置 0（voice key 不变覆盖 wav）；md 新增行建新节点（order 取上下句中点，**单句插入不丢任何行**）；md 删除行 DETACH DELETE。order 中点耗尽时全节重排（order 不进 voice key，安全）。
> **行身份 = 节点雪花 id**（voice key 末段，永不复用）——md 插入/删除/移动行不改变其他行的 key，旧 wav 不成孤儿。

## 参数

| 参数 | 说明 |
|------|------|
| section_id | Section 节点 ID（snowflake）。沿产物链查 SecScript + 所属 Chapter（算 stem）+ 逐句行 |

## 前置条件

- 本节 `SecScript.status=11`（定稿已批）；否则停止，提示先走 chapter-dialoguer + 定稿审。
- 所属 `Chapter.status=11`（结构已批）。
- 本节出场角色的 `VoiceDesign.status=11`（声音已批）。未就绪（无 VoiceDesign 或 status≠11）角色**警告跳过**（该角色 say 行保持 status=0 待配，运行时静默不播），提示先经 `char-design` 跑 `char-voice-design` 并审批，不阻断其他角色配音。

## 流程

### 1. 查 Section 产物链 + 所属 Chapter + 本节角色 VoiceDesign

```cypher
// (1) Section → SecOutline → SecScript（沿产物链取定稿）+ 所属 Chapter（算 stem）
MATCH (ch:Chapter)-[:has_section]->(sec:Section {id:'<section_id>'})-[:has_outline]->(:SecOutline)-[:produces]->(sc:SecScript)
RETURN sc.script_path AS script_path, sc.status AS sc_status, sc.id AS sc_id,
       ch.chapter_no AS no, ch.title AS title, ch.status AS ch_status;
```

- `sc_status≠11` → 停止（先定稿审）。
- 出场角色 = 图行 distinct `who`（首拆图无行时读 `台词.md` 的说话行 `who` 集合），其 VoiceDesign 沿图关系查（出场角色 → 在本节场景发生的事件中 involved）：

```cypher
// (2) 本节出场角色 VoiceDesign——图关系遍历，不按名字列表猜
MATCH (sec:Section {id:'<section_id>'})-[:contains]->(s:Scene)<-[:has_scene]-(loc:Location)
MATCH (loc)<-[:occurred_at]-(e:Event)<-[:involved]-(c:Character)
OPTIONAL MATCH (c)-[:has_voice_design]->(v:VoiceDesign)
RETURN DISTINCT c.name AS char, v.status AS vstatus, v.instruct AS instruct,
       v.ref_text AS ref_text, v.ref_audio_path AS ref_audio_path;
```

- `vstatus≠11` 的角色警告跳过（不写进 profiles）。
- **stem 构造**：由 `voice_bundler.chapter_stem_from_meta(no, title)` 算（`chapter<NN>_<title>`，NN=chapter_no 零填充），与 chapter-publisher 产出的章 JSON 文件名一致——本 skill 与 chapter-publisher 共用此函数，杜绝 stem 漂移。

### 2. 拆分对齐进图（幂等——每次配音前必跑）

```bash
python "${CLAUDE_SKILL_DIR}/scripts/script_splitter.py" split \
  --section '<section_id>' \
  --report '.tmp/split-<stem>-sec<MM>.json'
```

- 前置：SecScript=11（脚本自校验）。解析失败（md 格式违例）→ 脚本报**行号+原文**，就地修 md 后重跑（**不要**绕过拆分直接配音）。
- 读报告：`created/updated/deleted/restored/reordered` 计数与 warnings（Scene 缺失等）。**首次拆分** = 全部 created；**微调重拆** = 仅 updated（被改句）；**级联重拆** = restored（恢复 10）+ 0（重配）。
- 报告 warnings 里的 Scene 缺失 → 提示用户先跑 scene-designer 建场景（stages 边缺不阻塞配音）。

### 2b. （已并入 portrait_binder）选绘候选与建边

> 演出层（立绘选择）在配音判断期完成：候选池查询与新变体兜底建、uses 边建立全部由 [portrait_binder.py](scripts/portrait_binder.py) 承担（3a 的 `candidates` + 3c 的 `apply`），本 skill **不手写选绘 cypher**。

### 3. 算 tasks（挑行 → LLM 判 emotion + 产 tts_text 变体 → 写 tasks JSON）

#### 3a. 挑行算任务（图查 say 行 status=0）

```bash
python "${CLAUDE_SKILL_DIR}/scripts/voice_bundler.py" tasks-from-graph \
  --section '<section_id>' \
  -o '.tmp/voice-tasks-<stem>-sec<MM>.json'
```

`tasks-from-graph`：图查 `say 且 status∈{0,-1}` 的行（待配/被驳回/stale 拆分时已归一为 0；-1=拆分恢复判定之外的作废行）→ 按 produces.order 遍历切块推导 scene_block_id → 产出 `{char: [{key, text, scene_id, node_id, clone_mode}]}`——**不含 emotion/tts_text**（下一步做）；`clone_mode` 透传图上现值（上轮 bind 终值或人工在 dashboard 改的值）作 3b 判别初值，null=从未判过（缺省 icl）。key = `<char>-<stem>-<scene_block_id>-<节点id>`。`--nodes <id,...>` 可只挑指定行（dashboard 重生成 deeplink 用）。

挑行后紧接着产**选绘候选池**（3b 的 LLM 读它做选绘判断）：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/portrait_binder.py" candidates \
  --section '<section_id>' \
  -o '.tmp/portrait-candidates-<stem>-sec<MM>.json'
```

`candidates`：对待判 say 行按 (scene_block, who) 查候选立绘——沿 `Scene-depicts->IllusDesign-expands_to->stand` 列**场景内已有变体**（含未出图 status<11 的，附 variant_label/status/description）；该 (scene, who) 无 depicts 时按「场景事件 wears 优先、兜底 has_costume」选定 IllusDesign 再列其变体。`lines` 带每行 `current_stand`（现 uses 目标——重配句参考上轮选绘，语义同 clone_mode 初值）。报 `0 行待判` 时**跳过选绘**（3b 不判 stand、3c 跳过）。warnings 里的「无着装 IllusDesign」= 该角色着装链未建，apply 无法为其建边——汇报并继续其他角色。

#### 3b. LLM 逐句判别 emotion + clone_mode + 产 tts_text 变体 + 选立绘（本 skill 的核心判断步骤）

**读本节 `台词.md` 全文**（对话上下文）+ **选绘候选池** `portrait-candidates-<stem>-sec<MM>.json`（3a 产出），对 tasks 里的每个任务句做四件事：

1. **判别 emotion**（12 词表选一）：`平静` / `高兴` / `悲伤` / `愤怒` / `震惊` / `无奈` / `调侃` / `温柔` / `冷漠` / `紧张` / `恐惧` / `坚定`。判别依据：该句台词文本 + 前后对话语境 + 该角色在此刻的情绪走向。
2. **产 tts_text 配音变体**：在台词原文基础上做**仅标点/停顿级修饰**——按情绪加省略号（迟疑/喃喃）、叹号（惊讶/愤怒）、问号强化、破折号拖音、逗号停顿；**禁止增删改任何汉字**（运行时字幕显示原文 text，变体发声必须与字幕字面一致——加字会音字不符出戏）。原文已足够口语化时 `tts_text` 等于原文。强烈语气诉求（语气词/引导词，如「哼」「咦」「你说」）不写在变体里，而是建议作者写进台词.md 原文（text 层改动走 stale 自动重配，字幕同步）。驳回句重配时变体保持原文级（标点至多微调），靠**同文本重采样**的韵律随机性换演绎——仍不满意说明是 ref 音色问题，回 char-voice-design 层调 instruct。
3. **判别 clone_mode**（演绎通道，二选一，缺省 `icl`）：
   - `icl`（ICL）：ref codec + ref_text 进 prompt，ref 韵律迁移——音色最稳；但**平静 ref 的韵律会压制文本语气信号**，迟疑/强情绪句演绎乏力。
   - `xvec`（仅说话人向量）：丢 ref 韵律，**文本语义完全主导语气演绎**；音色无损失（demo/hesitation_demo.py 变体 C 验证），官方注明克隆相似度可能略降。
   - 判别依据：**迟疑/结巴/喃喃（省略号密集）、强情绪起伏（惊呼/崩溃/嘶喊/狂喜）、句内情绪反差大的句子 → `xvec`；平稳叙述、信息交付、日常应答 → `icl`**。emotion 词表与 clone_mode **不做固定映射**——同为「震惊」，轻讶短句 icl 足够、长嘶喊才需要 xvec；综合文本形态（标点密度/句长/情绪强度）与上下文判定。
   - tasks 项透传的 clone_mode 是**初值**：人工在 dashboard 改过的非缺省值视为意志表达，**除非与语境明显矛盾否则保留**；重配句参考上一轮模式——上轮 icl 被驳回/作废的非平静句优先改判 xvec（反之亦然）。

4. **选立绘（stand）**：为 tasks 里**每个**任务句选一张立绘（`台词.md` 演出层已与台词分离——选绘在此判定，即使与上一句相同也每句都写）：
   - **优先复用候选池已有变体**：`"stand": "<stand_id>"`。判据：该句台词氛围 + 前后语境 + 角色情绪走向与哪个 `variant_label`/`description` 最贴；重配句参考候选池透传的 `current_stand`（上轮选绘），人工未反对则倾向保持。候选含 status<11（未出图）的也可选——出图由 plot-design 后续推进，不阻塞配音。
   - **池中无贴切变体（含池空、候选全不搭）→ 提新变体**：`"stand": {"variant_label": "<2~4 字简短词>", "description": "<该变体氛围一句话：情绪强度/神态/身体张力，供出图把握——写氛围而非台词复述>"}`。variant_label 避免与候选池已有标签重复（apply 会按标签去重复用已有节点）。
   - **节奏原则**：同一段落情绪内保持同一 stand（不为每句强行换）；情绪转折/强反应处换变体；也不许整节只选一个变体敷衍——变体区分度是立绘表现力来源。
   - 旁白/narrate 行不选（tasks 只含 say 行）。**任何任务句不得缺 stand 字段**（3c 的 apply 会拒绝整个 tasks）。

**编辑 tasks JSON**（Edit 工具改第 3a 产出的文件）给每个任务项写入 `"emotion": "<词表项>"`、`"tts_text": "<变体>"`、`"stand": "<stand_id 或 {variant_label, description}>"`，xvec 句另写 `"clone_mode": "xvec"`（icl 句可省略，bind-graph 归一化缺省 icl）。emotion 仅作图标注与 dashboard 筛选展示（Qwen Base clone 无 instruct 通道，不参与合成参数）；**情绪表达由 tts_text 变体承载，演绎通道由 clone_mode 承载，立绘选择由 uses 边承载**；缺 tts_text 回落原文。

> 重生成（被驳回/stale）句也要重判重写——驳回往往因为语气不对（**选绘同理**：氛围变了 stand 也要重判）。

### 3c. 应用选绘（确定性建边）

```bash
python "${CLAUDE_SKILL_DIR}/scripts/portrait_binder.py" apply \
  --section '<section_id>' \
  --tasks '.tmp/voice-tasks-<stem>-sec<MM>.json'
```

`apply`（先全量校验后单事务写图）：读 tasks 每项的 `stand` 字段 → ①新变体兜底建（同 IllusDesign 下同 variant_label 已有则**复用**不重建；否则 `StandingIllustration{variant_label, description, status=0}` + `expands_to` + `ref_style`）②`Scene-[:depicts {sync:false}]->IllusDesign` 补建（每 (scene, illus) 一次）③该行旧 uses 边 DELETE 后 `MERGE (l)-[u:uses]->(st) SET u.sync=false`（幂等替换，**不动 status/voice_key**——重选立绘不重配音）。

- 读报告：`lines_bound`（应 = 本轮任务句数）/ `new_variants`（新变体清单——进段 7 汇报，plot-design 后续沿 depicts 推进出图）/ `reused_variants` / `warnings`（跨着装引用、缺 description 等，非阻断）。
- **校验失败**（缺 stand / stand_id 不存在 / 行不属于本节）→ 报告逐条列出坏项且**未写图**，回 3b 补齐 tasks 后重跑 apply（无图副作用）。
- 3a 报 `0 行待判` 时本步跳过（无新判断，已建边保持）。

### 4. 构造单节 profiles.json

把第 1 步查到的就绪角色 VoiceDesign（`instruct/ref_text/ref_audio_path` 三字段）写成 `.tmp/voice-profiles-<stem>-sec<MM>.json`，格式 `{char: {instruct, ref_text, ref_audio_path}}`。

### 5. 批量克隆 wav（单 venv）

> 两步同 venv `env/.venv-qwen`（Python 3.14 + Qwen3-TTS）——项目唯一声音链 venv，重建依赖清单见 `15_声音/requirements/qwen.txt`。

#### 5a. Qwen VoiceDesign ensure-ref（env/.venv-qwen）

```bash
env/.venv-qwen/Scripts/python.exe "${CLAUDE_SKILL_DIR}/scripts/voice_clone_runner.py" ensure-ref \
  --profiles '.tmp/voice-profiles-<stem>-sec<MM>.json'
```

`ref_audio_path` 文件存在则复用，否则 Qwen VoiceDesign 合成（`14_声音设计/<char>/<char>_ref.wav`，24kHz）。正常情况下 ref_audio 已由 char-voice-design 在设计阶段合成，此处多为 [reuse]。

#### 5b. Qwen3 Base Voice Clone 逐句合成（env/.venv-qwen，输入 tts_text 变体承载情绪）

```bash
env/.venv-qwen/Scripts/python.exe "${CLAUDE_SKILL_DIR}/scripts/voice_clone_runner.py" publish \
  '.tmp/voice-tasks-<stem>-sec<MM>.json' \
  --profiles '.tmp/voice-profiles-<stem>-sec<MM>.json' \
  --out-dir '15_声音'   # 母带 <out-dir>/<chapter_stem>/<scene_block_id>/<key>.wav（24kHz 原生，路径段从 key 解析）
```

逐句 try/except：单句失败记入 failed 列表（退出码 1 + stderr 逐条列出）——**失败句不 bind**（保持待配下轮重挑），成功句正常。汇报必须包含 failed 清单。`clone_mode=xvec` 的句子用仅说话人向量 prompt（每角色按模式懒构建，同角色 icl/xvec 可混排，全 icl 节零额外开销）。

### 6. 行级结果写回图节点（bind-graph）

```bash
python "${CLAUDE_SKILL_DIR}/scripts/voice_bundler.py" bind-graph \
  --tasks '.tmp/voice-tasks-<stem>-sec<MM>.json' \
  --keys '<成功句的 key 逗号列表，失败句排除>'
```

`bind-graph`（单事务）：给每个成功行节点写 `voice_key / emotion / tts_text / clone_mode=归一化终值（=本句实际合成模式，下轮重配的判别初值）/ attempts=旧+1 / text_sha1=sha1(原文) / status=10`（配完待审，dashboard 逐句音频审）。5b 无失败时省略 `--keys`（默认全部）。

### 6b. 收尾清理（bind-graph 之后必做）

```bash
rm -f '.tmp/split-<stem>-sec<MM>.json' '.tmp/voice-profiles-<stem>-sec<MM>.json' \
      '.tmp/portrait-candidates-<stem>-sec<MM>.json' '.tmp/voice-tasks-<stem>-sec<MM>*.json'
```

本轮四个中间文件（拆分报告 / profiles / 选绘候选池 / tasks，含 retry 轮变体）用后即删——`.tmp/` 是生产链临时区（gitignored），不留跨轮残留。

> **不碰** manifest.voices / chapter_packs.voices：章 JSON 还没合并，此时写入会污染或残缺。这两处由 chapter-publisher 合并完成后统一补（读合并后章 JSON 推导，覆盖式写入）。

### 7. 汇报与审批去向

status=10 的行进 dashboard 审批中心「逐句音频审」（按节分组）：每 say 行一张卡（原文/变体对照 + 判别 emotion 徽章 + wav 试听 + 单句通过=11/驳回=0），**节级「通过」gate = 该节全部行 status=11**。单句驳回 → 行 status=0 + 卡片下方「重生成」deeplink 唤起 plot-design 单节聚焦重跑本 skill（`--nodes <被驳回行id>` 只重做该句）。整节驳回 → 该节 say 行全置 0（重配，台词不变）。

## 重做与对齐

- **行身份不漂移**：voice key 末段是 LineAudio 节点雪花 id——台词.md 插入/删除/移动行不会使其他行的 key 失效，旧 wav 不成孤儿。台词被改的行在重拆时判 stale 置 0 自动重配；人工微调走 dashboard「重新提交审批」（仅 sc→10，**不动行节点**），重批后重拆只重做被改句，未变句审批结果原样保留。
- **status=-1 级联**：SecScript/上游被 sync 级联 → 该节全部行 -1。重跑本 skill：拆分对齐把「text_sha1 匹配且 wav 在」的行恢复 10（音频复用不重配），其余置 0 重配；若 SecScript 本身 -1，先经 dialoguer 重做定稿升 11，再重跑本 skill。
- **批量强制重做（演绎质量迁移等）置 0 不置 -1**：-1 会被拆分对齐的恢复机制判定「wav 在即复用旧音频」恢复 10，重配不发生；置 0 才是「待配重做，覆盖母带」的归一入口（挑行 status∈{0,-1} 均可挑中，但 -1 行先经拆分恢复分诊）。

## 汇报

列出：节 script_path、stem、拆分对齐统计（created/updated/deleted/restored/reordered）、本轮挑行统计（待配 N 句，复用保持 M 句）、**选绘统计（建边 N 句 / 新变体 M 清单 / 复用 K——新变体为 status=0 缺口，由 plot-design 按 depicts 推进 char-stand-designer 出图）**、各角色产出 wav 数（`{char: N}`）与**通道分布（icl N / xvec M）**、跳过的角色（无 VoiceDesign 或未就绪）、**failed 清单（char/key/错误）**、bind 的行数、行级 status=10 计数。提示用户去 dashboard 审批中心做逐句音频审。

## 参考文档

- 拆分对齐：[script_splitter.py](scripts/script_splitter.py)（parse_md/align/split——台词.md↔图行对齐与 order 中点的唯一实现）
- 选绘建边：[portrait_binder.py](scripts/portrait_binder.py)（candidates/apply——候选池与 `LineAudio-[:uses]->StandingIllustration` 边的唯一实现）
- 挑行与绑定：[voice_bundler.py](scripts/voice_bundler.py)（make_voice_key / tasks-from-graph --nodes / bind-graph）
- 基线音色设计：[char-voice-design](../char-voice-design/SKILL.md)（VoiceDesign 生成）
- 合并衔接：[chapter-publisher](../chapter-publisher/SKILL.md)（voice_key 随图投影进章 JSON + 补 manifest/chapter_packs）
- 声音 Schema：[00_init/Schema/声音.md](../../../00_init/Schema/声音.md)（含 BgmTrack）
