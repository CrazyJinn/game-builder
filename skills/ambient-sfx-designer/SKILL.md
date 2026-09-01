---
name: ambient-sfx-designer
description: |
  推进单节环境音行（LineAudio op=transition 转场音效 + narrate 内嵌 ambience 声景，status=0）的音频产出——「实录 foley + AudioFly 氛围」双通道：
  ① ambient_tasks.py 查待产行并预计算 track（amb-<stem>-<block>-<节点id>，杜绝手拼 key）→
  ② 类型由 md 语法决定（ambient_tasks.py 直带 kind）：转场型独立行（短事件，1~2s）走 Freesound CC0 实录检索，氛围型旁白内嵌（声景，~5s，挂 narrate 行）走 AudioFly 生成 →
  ③ Freesound 链：匿名 curl 搜索（CC0+时长过滤）→ 取最佳 1 条候选落 .tmp/ambient/ 请用户试听 → 转码落母带 + 15_声音/sfx_raw/SOURCES.md 登记；
  AudioFly 链：ambient_fly.py jobs 单候选（env/.venv-audiofly）→ 用户试听 → finalize 裁剪+淡出落母带 →
  ④ 先产物后写图：SET ambient_track + status=10 待审即止——不拷运行时副本（dashboard 逐句审批试听读母带 15_声音/；99_game/assets/sfx 只由 chapter-publisher 发布时按 status=11 收录）。
  在单节定稿已拆分、需要产出/重做环境音时使用（由 plot-design 单节聚焦在配音步之后编排）。
argument-hint: <section_id>
arguments:
  - section_id
allowed-tools: Read, Bash, Write, Edit, Skill
---

# 环境音产出（ambient 行 · 实录 foley + AudioFly 氛围）

台词.md 的 `环境音:` 行拆分进图后是 `LineAudio {op:'ambient', status:0}`——本 skill 把它们产出为音频资产，
走行级审批（10→11）与其他音频行同构。

**双通道分工**（2026-08-28 demo 验证结论）：

| 语义类型 | 通道 | 成品规格 | 依据 |
|---|---|---|---|
| 短事件（有明确起振/动作语义） | **Freesound CC0 实录** | 1~2s + 短淡出 | 扩散模型对秒级高频单发事件糊，实录真实感碾压 |
| 持续声景（底噪/氛围语义） | **AudioFly 生成** | ~5s + 2s 淡出 | AudioCaps 评测超 Stable Audio Open（FD 40.1 vs 78.24），Apache 2.0 |

**track（= 母带/manifest 统一键）**：`amb-<chapter_stem>-<scene_block_id>-<行节点id>`，由 ambient_tasks.py 预计算——**LLM 不手拼 key**。母带 `15_声音/<stem>/<block>/<track>.wav`（审批试听源）；运行时副本 `99_game/assets/sfx/<track>.wav` 由 chapter-publisher 发布时按 status=11 拷贝，本 skill 不碰 99_game。

## 参数

| 参数 | 说明 |
|------|------|
| section_id | Section 节点 ID（snowflake） |

## 流程（三段式）

### 1. 查状态 + 产 jobs

前置：该节 SecScript=11 且已拆分（图有行）。跑：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/ambient_tasks.py" --section '<section_id>' -o '.tmp/ambient-jobs-<stem>-sec<MM>.json'
```

0 条待产行（全 10/11）→ 直接汇报跳过。

### 2. 逐行确认类型 + 产出（先产物后写图）

**类型由 md 语法决定**（ambient_tasks.py 已在 jobs 里带 `kind`，无需再判）：
- `kind=transition`：独立 `环境音:` 行（转场音效，op=transition）——极短音（1~2s）运行时播完再接下一句；
- `kind=ambience`：旁白内嵌 `【环境音:…】` 标注（氛围型，挂在 narrate 行的 ambient_text）——约 5s 声景与该旁白同出。

两类共用 track 格式 `amb-<stem>-<block>-<行id>`（转场行与氛围旁白行的行 id 都在末段）。Freesound/AudioFly 分流原则不变：短事件走实录、声景走生成——**按 kind 直取**（transition→Freesound、ambience→AudioFly），个别语义明显不匹配时（如 ambience 语义其实是单次事件）以语义为准并在汇报中说明。

#### 2a. Freesound 链（transition 行）

匿名 curl 检索（无需登录；网页搜索/CDN 预览均公开，仅下载原始无损需用户账号）：

```bash
# 搜索（英文关键词，CC0 + ≤5s 过滤；关键词由 LLM 从中文语义翻写，AudioCaps 风格：声源+空间+修饰）
curl -s 'https://freesound.org/search/?q=<english+keywords>&f=license%3A%22Creative+Commons+0%22+duration%3A%5B0+TO+5%5D' -H "User-Agent: Mozilla/5.0" \
  | grep -oE 'href="/people/[^"]+/sounds/[0-9]+/"' | sort -u | head -6
# 逐候选详情页确认许可并取 CDN 预览直链
curl -s "https://freesound.org/people/<user>/sounds/<id>/" -H "User-Agent: Mozilla/5.0" \
  | grep -oE '(https://cdn\.freesound\.org/previews/[^"]+-hq\.mp3)|(Creative Commons 0)'
# 下载 2~3 个候选到 .tmp/ambient/（128k mp3 试听质量；先 curl -o 再转 wav）
```

- 候选下载后**停下请用户试听**（`.tmp/ambient/`）。
**单候选制**（用户 2026-08-29 定）：每行只出 1 个候选试听，不做多选一——不满意就换检索词/换 seed 重出下一版，迭代到满意为止。
- 选定后：mp3 转 wav（`env/.venv-audiofly` 的 soundfile 可读 mp3）+ 裁剪（峰值截取 1~2s，可复用 `ambient_fly.py finalize --kind transition --cut <秒>`，传 mp3 转出的临时 wav）+ 落母带路径。
- **SOURCES.md 登记**（Steam 商售合规留存）：在 `15_声音/sfx_raw/SOURCES.md` 追加一行 `| <文件 stem> | <声音名> | <作者> | <详情页 URL> | CC0 | <成品 track> | 备注 |`（成品 track 列填本行 amb-… 键——dashboard 批准后按此列自动删除原始素材，登记文本保留）。
- **无损升级可选不阻塞**：先以预览版落盘写图（流水线不断）；SKILL 汇报里注明「用户可事后登录 freesound.org 下载无损原件覆盖同名母带，track 不变图不动」。
- curl 失败/限流 → 降级：报告搜索结果页链接请用户手选，不硬造。

#### 2b. AudioFly 链（ambience 行，env/.venv-audiofly）

```bash
# ① 生成单候选（10s 原生段 .tmp/ambient/<track>_c1.wav；模型 ~8GB 一次加载批量跑，count 默认 1）
env/.venv-audiofly/Scripts/python.exe "${CLAUDE_SKILL_DIR}/scripts/ambient_fly.py" jobs '.tmp/ambient-jobs-<stem>-sec<MM>.json'
# ② 用户选定后 finalize（氛围：前 5s + 2s 淡出；转场语义误判可 --kind transition --cut 1.5）
env/.venv-audiofly/Scripts/python.exe "${CLAUDE_SKILL_DIR}/scripts/ambient_fly.py" finalize \
  '.tmp/ambient/<track>_c<N>.wav' '15_声音/<stem>/<block>/<track>.wav' --kind ambience
```

prompt 由 LLM 从中文语义翻写为**英文**（AudioCaps 风格：声源+空间+氛围修饰，如「雨点骤然砸落」→ `Rain suddenly starts falling on a city street, rapidly growing heavier, raindrops hitting wet asphalt`），回填 jobs JSON 的 `prompt` 字段后再跑 ①。

候选生成后**停下请用户试听**，满意 → finalize → 母带就位；不满意 → 调 prompt 措辞或换 `--seed` 重出（单候选迭代制，不并排出多个）。

### 3. 写图 + 汇报（产物落盘校验后才写）

```bash
# 校验：ls 母带文件存在且 >10KB，任一缺失停止不写图
python .claude/scripts/cypher_exec.py --stdin --multi <<'EOF'
MATCH (l:LineAudio {id:'<node_id>'}) SET l.ambient_track='<track>', l.attempts=coalesce(l.attempts,0)+1, l.status=10;
EOF
```

不拷运行时副本——dashboard 逐句审批试听直接读母带 `15_声音/`，`99_game/assets/sfx/` 只由 chapter-publisher 发布时按 `status=11` 收录。

收尾：`rm -f '.tmp/ambient-jobs-<stem>-sec<MM>.json'`（候选 wav 保留至用户选定后由下一轮清理）。

汇报：每行 track / 判型 / 通道来源 / status=10，提示到 dashboard 审批中心逐句审（环境音行卡：🔊 徽章 + 母带试听 + 通过/驳回）；驳回 → status=0，重跑本 skill 只重做该行。

## 重做

- **status=-1 级联**后重拆：ambient 行「track 在且母带 wav 在 → 恢复 10，否则 0」（script_splitter 恢复逻辑，音频复用不重产）。
- **text 变化**（stale）：置 0 重产，track 沿用覆盖母带——描述改了但行身份不变。
- 重做判定**只看 status，不看文件**；`-1` 必须重新生成覆盖，禁止读旧 prompt/旧 wav。

## 参考文档

- 行模型：[00_init/Schema/剧情.md](../../../00_init/Schema/剧情.md)（LineAudio op=transition / ambience 挂 narrate / ambient_track / status）
- track 解析与母带路径：[voice_bundler.py](../section-voice-publisher/scripts/voice_bundler.py)（split_voice_key / voice_master_path / make_ambient_track）
- AudioFly 环境（env/.venv-audiofly 重建）与能力边界：[demo/README.md](../../../demo/README.md)
- Freesound 素材登记：[15_声音/sfx_raw/SOURCES.md](../../../15_声音/sfx_raw/SOURCES.md)
