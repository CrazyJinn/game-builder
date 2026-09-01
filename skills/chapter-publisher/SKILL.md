---
name: chapter-publisher
description: |
  把全章各节产物就绪（各节 SecOutline=1 ∧ SecScript=11 ∧ 该节全部台词行 LineAudio=11，且所属 Chapter.status=11）的章节从图发布到运行时 `99_game/`：
  用 generate_portrait_map.py（产出 chapter-map：bgm 段）+ merge_sections_to_chapter.py --chapter --chapter-map 把全章图行（SecScript-produces{order}->LineAudio 逐句行，按节序/order 投影）合并为单一章 JSON（say.portrait 沿 `LineAudio-[:uses]->StandingIllustration` 边投影为 guid 整键 `<char>-<costume>-<variant>-<stand_id>`——stand_id 全局唯一解决同角色换装同名覆盖；缺 uses 边的 say 行打警告、portrait 空串；BGM 从图 Scene-has_bgm->BgmTrack 注入 scene-block）拷到 99_game/data/chapters/ + status=11 的立绘/背景资源 + status=2 的 BgmTrack 音频到 99_game/assets/ + 更新 manifest + 产出章资源清单 chapter_packs.json（Web 按章分包依据）。
  在全章各节定稿+逐句音频审批通过且所需立绘就绪、需发布到 Godot 运行时时使用；由用户直接触发（不在 plot-design 职责内，plot-design 推进到全章就绪即止）。
argument-hint: <chapter_id>
arguments:
  - chapter_id
allowed-tools: Read, Bash, Write, Edit
---

# 章节发布（Chapter + 各 Section → 99_game）

把审阅通过的章节从**图**（LineAudio 逐句行，台词.md 为人机界面）发布到**运行时区**（`99_game/`）：
**从图投影全章各节台词行合并为一个章 JSON** 落到 `99_game/data/chapters/`（Godot 只读 JSON，运行时不感知节层；行节点 id 等图字段被投影丢弃，say.voice 取自行节点 voice_key），拷贝章节涉及的立绘/背景图片/BGM 音频到 `99_game/assets/`，更新 `manifest.json`，并产出**章资源清单** `chapter_packs.json`（Web 按章分包导出依据）。
发布是**确定性转换+拷贝**（非 LLM 创作），幂等——重复发布覆盖旧文件，无副作用。

## 参数

| 参数 | 说明 |
|------|------|
| chapter_id | Chapter 节点 ID（snowflake） |

## 流程

### 1. 查询章节与各节 + 前驱状态

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查 Chapter + 各 Section + 编排子图：

```cypher
// (1) Chapter 本体 + 前驱校验
MATCH (ch:Chapter {id:'<chapter_id>'})
RETURN ch.title AS title, ch.chapter_no AS no, ch.status AS status;
// (2) 各 Section（按 section_no）+ 产物链（SecOutline/SecScript + 逐句行聚合）+ 前驱校验
MATCH (ch:Chapter {id:'<chapter_id>'})-[:has_section]->(sec:Section)
OPTIONAL MATCH (sec)-[:has_outline]->(ol:SecOutline)
OPTIONAL MATCH (ol)-[:produces]->(sc:SecScript)
OPTIONAL MATCH (sc)-[:produces]->(l:LineAudio)
RETURN sec.section_no AS no, sec.title AS title,
       ol.status AS ol_status, ol.outline_path AS outline_path,
       sc.status AS sc_status, sc.script_path AS script_path,
       count(l) AS line_count,
       sum(CASE WHEN coalesce(l.status, 0) = 11 THEN 1 ELSE 0 END) AS line_done
ORDER BY sec.section_no;
// (3) 全章 background 图层（Chapter→has_section→Section→contains→Scene→has_layer→SceneLayer）
MATCH (ch:Chapter {id:'<chapter_id>'})-[:has_section]->(:Section)-[:contains]->(s:Scene)
OPTIONAL MATCH (s)-[:has_layer]->(sl:SceneLayer {layer_type:'background'})
RETURN DISTINCT s.name AS scene_name, sl.image_path AS bg_image, sl.status AS bg_status;
// (3b) 全章 BGM（Scene-has_bgm->BgmTrack；status=2 才拷贝/注入，<2 警告跳过）
MATCH (ch:Chapter {id:'<chapter_id>'})-[:has_section]->(:Section)-[:contains]->(s:Scene)-[:has_bgm]->(b:BgmTrack)
RETURN DISTINCT s.name AS scene_name, b.name AS track, b.status AS bgm_status, b.audio_path AS audio_path;
// (4) 本章被引用立绘（LineAudio-uses->stand：选绘行级直连——拷贝清单=被引用清单，与 requires 同源；
//     回溯角色/着装算 guid 整键 <char>-<costume>-<variant>-<stand_id>）
MATCH (ch:Chapter {id:'<chapter_id>'})-[:has_section]->(:Section)-[:has_outline]->(:SecOutline)
      -[:produces]->(:SecScript)-[:produces]->(l:LineAudio)-[:uses]->(stand:StandingIllustration)
MATCH (char:Character)-[:has_appearance|has_voice_style|has_costume|produces|outfit_for|expands_to|ref_style*1..5]->(stand)
OPTIONAL MATCH (illus:IllusDesign)-[:expands_to]->(stand)
OPTIONAL MATCH (costume:CostumeStyle)-[:outfit_for]->(illus)
RETURN DISTINCT char.name AS char_name, stand.id AS stand_id, stand.variant_label AS variant, costume.name AS costume_name, stand.image_path AS image_path, stand.status AS status;
// (4b) 选绘缺口计数（say 行无 uses 边——发布将打警告、portrait 空串、运行时占位图兜底）
MATCH (ch:Chapter {id:'<chapter_id>'})-[:has_section]->(:Section)-[:has_outline]->(:SecOutline)
      -[:produces]->(:SecScript)-[:produces]->(l:LineAudio)
WHERE l.op = 'say' AND NOT (l)-[:uses]->(:StandingIllustration)
RETURN count(l) AS say_no_stand;
```

**前驱校验**：
- `ch.status` 必须 = `11`（结构已批）；**每节产物链必须就绪：`ol_status=1` ∧ `sc_status=11` ∧ `line_count>0 ∧ line_done=line_count`**（提纲完成 + 定稿已批 + 该节全部台词行声音已批）——章真正可发布 = `Chapter.status==11` AND 全部节产物就绪。任一不满足则停止并提示先在 dashboard 推进/审批对应节（含定稿审 10→11、拆分配音、逐句音频审）。
- 被引用立绘（uses 边目标）：`status=11` 且 `image_path` 非空的才拷贝；`status≠11` 的逐个**警告**（运行时该变体走占位图），不阻断发布（让已就绪资源先上线）。`say_no_stand>0` 时**警告** N 句缺选绘（该批句运行时保持上一张/占位图）。
- background SceneLayer：同理，`status=11` 且 `image_path` 非空才拷贝。
- BgmTrack：`status=2` 且 `audio_path` 文件存在的才拷贝/注入；`<2` 或文件缺失逐个**警告**（该场景运行时无 BGM，静默），不阻断发布。
- 环境音行（可选附加查询）：`MATCH (ch:Chapter {id:'<chapter_id>'})-[:has_section]->(:Section)-[:has_outline]->(:SecOutline)-[:produces]->(:SecScript)-[:produces]->(l:LineAudio) WHERE l.status=11 AND l.ambient_track IS NOT NULL RETURN DISTINCT l.ambient_track AS track`——本章已批环境音的 track 清单（chapter_packs 用；拷贝由下步 (e) publish 统一做）。以 ambient_track 字段存在为准、不看 op（转场音效 op=transition 与 narrate 内嵌声景 ambience 都算）。注意环境音行未全批会卡各节产物链就绪判定（行 gate），与 say 同规。

### 2. 合并拍平 + 拷贝资源到 99_game/

**章 stem**：用 [voice_bundler.chapter_stem_from_meta](../section-voice-publisher/scripts/voice_bundler.py)(no, title) 构造 `chapter<NN>_<章概述>`（NN=`chapter_no` 零填充，章概述取 `ch.title` 核心主题，清洗 Windows 非法字符）——与 section-voice-publisher 共用此函数，保证节级 voice key 的 stem 与章 JSON 文件名**单一源、不漂移**。运行时文件名用 `<stem>.json`。合并输入 = 全章图行（工具内部按 section_no 节序 + produces.order 行序投影）。

```bash
# 确保目标目录存在
mkdir -p 99_game/data/chapters 99_game/assets/portraits 99_game/assets/scenes 99_game/assets/bgm

# (a.0) 章映射 chapter-map：bgm 段（Scene-has_bgm->BgmTrack，仅 status=2 进 map）。
#       portraits 段已废弃——立绘整键由 merge 沿 LineAudio-[:uses]->stand 边在投影期直接解析
python 99_game/tools/generate_portrait_map.py '<chapter_id>' -o '99_game/data/.cache/chapter-map-<stem>.json'

# (a) 剧本：从图投影全章台词行 → 99_game/data/chapters/<stem>.json（Chapter→Section(section_no)→
#     SecScript-produces{order}->LineAudio；前置校验各节产物就绪；
#     say.portrait 沿 uses 边投影为 guid 整键（缺边 say 行警告 + 空串）；--chapter-map 注入
#     scene-block.bgm；requires.portraits = 投影整键并集；
#     行节点 id 等图字段投影丢弃，say.voice = 行节点 voice_key）
python 99_game/tools/merge_sections_to_chapter.py \
  --chapter '<chapter_id>' \
  --chapter-map '99_game/data/.cache/chapter-map-<stem>.json' \
  -o '99_game/data/chapters/<stem>.json'
python 99_game/tools/validate_chapter.py '99_game/data/chapters/<stem>.json' 99_game/data/剧本.schema.json
#   validate FAIL → 中断发布，报警（剧本 schema 不合，回 台词.md 修对应节并重新走拆分/审批）
#   注：合并工具内置 scene-block id 章内唯一性校验（重复则报错）——若报 id 重复，说明 structurer 预分配环节 id 冲突，需回上游修正。

# (b) 立绘：绿幕原图 → opencv 抠绿+发丝精修+头位归一化 → 99_game/assets/portraits/<整键>.png
#     4角采样自适应抠绿（替代硬编码色）+ grabCut 发丝精修 + despill 去绿边；以人物高/7.5 头长为尺度、
#     YuNet 双眼中心为锚点缩放平移，使同角色各变体头部（眼线）落在画布同一水平线（800x1200 RGBA）。原图 06_/ 不动。
#     <整键> = <char>-<costume_short>-<variant>-<stand_id>（与 manifest 键、合并 JSON requires.portraits 一致——
#     三处同经 portrait_key.make_key，键源数据 = uses 边回溯）
python 99_game/tools/process_portrait.py '<image_path>' -o '99_game/assets/portraits/<整键>.png'

# (c) 背景：SceneLayer.image_path → 99_game/assets/scenes/<Scene.name>.png
cp '<bg_image>' '99_game/assets/scenes/<scene_name>.png'

# (d) BGM：status=2 的 BgmTrack.audio_path → 99_game/assets/bgm/<track 名>.wav
cp '13_BGM/<track 名>.wav' '99_game/assets/bgm/<track 名>.wav'

# (e) 音频（voices + sfx 一步）：按章查已批（status=11）音频行 → 母带拷运行时
#     voice key → 99_game/assets/voices/<key>.wav；ambient_track（amb- 前缀，含 narrate 内嵌
#     声景）→ 99_game/assets/sfx/<track>.wav。源=母带 15_声音/<stem>/<block>/，幂等，
#     母带缺失警告不阻断。**99_game/assets 只经发布收已批音频**——生成期无 sync，
#     dashboard 逐句审批试听直接读母带
python .claude/skills/section-voice-publisher/scripts/voice_bundler.py publish --chapter '<chapter_id>'
```

> 源路径（`image_path`/各节 `script_path`）是项目根相对，`cp`/合并时 cwd 应在项目根。立绘目标路径用 guid 整键 `<char>-<costume>-<variant>-<stand_id>`（来自第 1 步 uses 边查询的整键计算），与 manifest 的 portraits 键、合并后 JSON 的 `meta.requires.portraits` 三处对齐。整键由 merge_sections_to_chapter.py / manifest_builder.py 经 [portrait_key.make_key](../../../99_game/tools/portrait_key.py) 同源生成。
> 缺源文件（`image_path` 指向的图不存在）则**警告跳过**该资源，不中断。

### 3. 更新 manifest

跑 manifest_builder（查 status=11 立绘 + Scene，生成逻辑名→`assets/...` 映射，与上一步拷贝目标一致）：

```bash
python 99_game/tools/manifest_builder.py
```

**补 manifest.bgm 段**（图驱动）：把本章 status=2 且已拷贝的 BgmTrack 写入 `{track 名: assets/bgm/<track 名>.wav}`（与 manifest_builder 保留的手写键合并；cg 仍手写；**sfx 已由 manifest_builder.collect_sfx 图驱动收集**——查 `ambient_track IS NOT NULL 且 status=11` 行自动写 `sfx[track]`，无需手补）：

```bash
# 用一段小 python 或手动编辑 manifest.json 合并本章 BGM 键（示例）
python - <<'EOF'
import json
from pathlib import Path
mp = Path('99_game/data/manifest.json')
m = json.loads(mp.read_text(encoding='utf-8'))
m.setdefault('bgm', {}).update({'<track 名>': 'assets/bgm/<track 名>.wav'})  # 本章每个已拷贝 track
mp.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
EOF
```

**补 manifest.voices 段**：节级配音（section-voice-publisher）已把 `audio.key` 写进各节台词行，投影合并时成为章 JSON 的 `say.voice`；manifest 的 voices 段在此补（读合并后章 JSON 的 `say.voice` 推导，节级阶段章未合并无法写）：

```bash
# 写 manifest.voices 段（{key: assets/voices/<key>.wav}）
python .claude/skills/section-voice-publisher/scripts/voice_bundler.py manifest '99_game/data/chapters/<stem>.json' --ext wav
# 导出本章 voice 键 CSV，供下一步 chapter_packs.voices
python .claude/skills/section-voice-publisher/scripts/voice_bundler.py list '99_game/data/chapters/<stem>.json' > '99_game/data/.cache/voices-<stem>.csv'
```

### 4. 产出章资源清单 chapter_packs.json（Web 分包依据）

把本章用到的立绘/背景逻辑名记入 `99_game/data/chapter_packs.json`，供导出工具按章把资源分组打成 `<stem>.pck`（pck 内路径与全局 manifest 一致，挂载后 `res://` 全局路径命中）。**分包粒度仍是章 stem**（运行时不感知节层）。

数据源 = 合并后章 JSON 的 `meta.requires.portraits`（投影期已沿 uses 边解析为 guid 整键，最稳，与 lines 引用同源）+ 第 1 步全章背景 + 第 3 步导出的 voice 键 + 章内各 scene-block 的 bgm：
- `portraits`：guid 整键 `<char>-<costume>-<variant>-<stand_id>`（直接取合并 JSON 的 requires.portraits）
- `scenes`：`<Scene.name>`（has_layer background）
- `voices`：voice 键 `<char>-<stem>-<scene_id>-<line_id>`（第 3 步 `voice_bundler list` 导出的 CSV）
- `bgm`：BGM 逻辑名 `<track>`（合并时从图 Scene-has_bgm 注入各 scene-block 的 `bgm.track`，去重；漏传则 Web 章包缺音乐）

```bash
python 99_game/tools/chapter_packs_updater.py '<stem>' \
  --portraits '<整键1>,<整键2>' --scenes '<scene1>,<scene2>' \
  --voices "$(cat '99_game/data/.cache/voices-<stem>.csv')" \
  --bgm '<track1>,<track2>'
```

工具幂等：覆盖该 stem 条目，保留其他章。空列表（该章无立绘/背景）也要写入，保持清单完整。

### 5. 汇报

列出：发布的章 JSON 路径（`99_game/data/chapters/<stem>.json`）、合并的节数、拷贝的立绘清单（guid 整键 `<char>-<costume>-<variant>-<stand_id>`）、背景清单（`<Scene.name>`）、BGM 清单（`bgm.track` 去重）、跳过/缺失的资源警告、manifest 更新结果、章清单更新结果（该章 portraits/scenes/bgm 条数）。
附运行时入口提示：`GameManager.start_new_game('<stem>', '<首节首 scene-block id>')`（stem = 不含后缀的章名，如 `chapter00_序章`；首 scene-block id 取 section_no=0 节的第一个段 id）。

## Web 发布前的额外步骤（导出阶段，非本 skill）

剧本加密 + 按章分包在**导出时**做（本 skill 只产明文 + 清单，保持桌面/开发期可读）：

1. **加密剧本**（挡自动扒包，可选但 Web 推荐）：覆盖式加密，运行时 ChapterLoader 检测 magic 头自动解密。
   ```bash
   pip install -r 99_game/tools/requirements.txt   # 需 cryptography
   python 99_game/tools/encrypt_chapter.py '99_game/data/chapters/<stem>.json' '99_game/data/chapters/<stem>.json'
   ```
   ⚠️ 加密后无法再 `validate_chapter.py`（明文），故加密必须在本 skill 流程之后。
2. **按章分包 + Web 导出**（2026-08-30 起有完整流水线）：`python 99_game/tools/publish_web.py` 一键完成「字体子集化 → 导出 Web 主包（exclude assets/chapters/full.ttf）→ build_chapter_packs.gd 按清单产各章 `<stem>.pck` → 恢复字体」；产物上传 R2 用 `deploy_r2.py`（详见两个脚本头部注释）。分包机制：主 pck 不含任何章资源，开局/读档/跨章由 ChapterPackLoader 下载章包挂载（带进度 UI）。

## 与 section-voice-publisher 的边界

`voice` 字段（`say.voice`）由 [section-voice-publisher](../section-voice-publisher/SKILL.md) 在**节级定稿后**经 `bind-graph` 写进行节点 `voice_key`，本 skill 图投影合并时自动带进章 JSON：

- **生产时序**：chapter-dialoguer（台词.md → SecScript=10→11）→ **section-voice-publisher**（拆分进图 → 节级 TTS + bind-graph 写行节点 → 行 status=10→逐句审→11）→ **chapter-publisher**（图投影台词行[voice=voice_key] + 立绘/BGM + 补 manifest.voices / chapter_packs.voices）。
- 本 skill 合并时 say 行节点已含 voice_key（投影把 `voice_key` 投为 `say.voice`）→ 合并后章 JSON 每 say 自带 voice，**无需再注入**。
- **本 skill 末尾补 manifest.voices + chapter_packs.voices**（节级阶段章未合并，这两处无法写；合并后用 voice_bundler 读章 JSON 推导补齐，见第 3、4 步）。
- **行身份稳定寻址**：voice key 末段是 LineAudio 行节点雪花 id——台词.md 插入/删除/移动行不影响其他行 key；某句台词被改（stale 重配）后重跑该节 section-voice-publisher 覆盖对应 wav 即可，无全节重配。
- chapter JSON 的 `meta.requires` 不含 voices（voice 键按行节点 id 算，不进 requires）。

## 参考文档

- 台词.md 格式（人读定稿）与图行投影：[script_splitter.py](../section-voice-publisher/scripts/script_splitter.py)（parse_md——格式规范的机器侧权威）+ [merge_sections_to_chapter.py](../../../99_game/tools/merge_sections_to_chapter.py)（graph_lines_to_doc 图行投影）
- 节合并工具：[99_game/tools/merge_sections_to_chapter.py](../../../99_game/tools/merge_sections_to_chapter.py)（图行 → 1 章 JSON）
- manifest 生成器：[99_game/tools/manifest_builder.py](../../../99_game/tools/manifest_builder.py)
- 章资源清单更新器：[99_game/tools/chapter_packs_updater.py](../../../99_game/tools/chapter_packs_updater.py)
- 剧本加密（Web）：[99_game/tools/encrypt_chapter.py](../../../99_game/tools/encrypt_chapter.py) ↔ 运行时 [99_game/scripts/util/ScriptCipher.gd](../../../99_game/scripts/util/ScriptCipher.gd)
- 章包加载（运行时）：[99_game/scripts/autoload/ChapterPackLoader.gd](../../../99_game/scripts/autoload/ChapterPackLoader.gd)
- 剧情 Schema（Chapter/Section/has_section/contains/depicts）：[00_init/Schema/剧情.md](../../../00_init/Schema/剧情.md)
