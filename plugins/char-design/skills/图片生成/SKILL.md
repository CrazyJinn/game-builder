---
name: 图片生成
description: 调用 OfoxAI Images API 生成图片。紧接美术提示词流程，从 Neo4j 查询提示词路径，生成角色设计图和立绘。支持文生图和图生图（含多图引用），兼容 gpt-image-2 / dall-e-3 / dall-e-2。触发条件：(1) 需要使用 OfoxAI 生成图片 (2) 角色图片生成阶段 (3) 用户指定使用 ofoxai 或 GPT Image / DALL-E 模型生成图片 (4) 精灵帧表生成（基于JSON提示词+Q版设计图生成角色动画帧表）
allowed-tools: Read, Bash, Write, Edit, Agent
---

# OfoxAI 图片生成

紧接美术提示词流程，从 Neo4j 查询角色提示词路径，调用 OfoxAI Images API 生成角色设计图和立绘。

脚本路径: `scripts/ofoxai_api.py`（相对于 skill 目录）
API Key 在项目根目录 `settings.json` → `ofox` 字段，脚本自动读取。



### 阶段3：读取提示词

根据阶段2查到的路径读取提示词文件：

- **设计图**：读取 `design_prompt_path` 指向的文件，提取「三视图提示词」部分的完整文本
- **立绘**：读取 `stand_painting_prompt_path` 指向的文件，提取各变体的变体名和对应提示词

文件缺失时终止该角色的生成并记录到 unable_to_process。

### 阶段4：生成图片

> **尺寸参数（强制）**：每次调用 `submit` 时必须通过 `--size` 显式传入图片尺寸。尺寸从提示词文件的规格信息中确定。若无法明确尺寸，**必须向用户确认**后再调用，禁止省略 `--size` 或使用默认值。

根据产出类型执行生成：

#### 设计图（文生图）

从提示词文件提取「三视图提示词」的完整文本，调用文生图：

```bash
python scripts/ofoxai_api.py submit "<三视图提示词>" --size 1024x1024 --quality low -o "./06_角色美术/<角色ID>/设计图.png"
```

#### 立绘（图生图）

立绘以已生成的设计图为参考图，逐变体生成：

1. 确认参考图存在：`06_角色美术/<角色ID>/设计图.png`（若设计图未生成，先执行设计图生成）
2. 从 `stand_painting_prompt_path` 文件读取变体列表
3. 逐个调用图生图：

```bash
python scripts/ofoxai_api.py submit "<变体提示词>" --image "./06_角色美术/<角色ID>/设计图.png" --size 1024x1024 -o "./06_角色美术/<角色ID>/立绘/<变体名>.png"
```

**立绘规格**（从提示词文件头部读取）：
- 尺寸：默认 1024x1024
- 背景：纯白
- 生成方式：图生图（以设计图为参考）

### 阶段5：更新总览

更新 `06_角色美术/角色美术总览.md`：

- 设计图生成完成：将角色索引中设计图状态从「提示词」改为「初稿」，填写文件名
- 立绘变体生成完成：逐个将变体状态从「提示词」改为「初稿」，填写文件名

### 阶段6：更新 Neo4j

将已处理角色的信息更新到 Neo4j。

**通过 neo4j-helper skill 以自然语言执行更新**：

> "更新编号为 <角色编号> 的角色节点，设置 status 为 3，design_image_path 为 '06_角色美术/<角色编号>/设计图.png'"

批量更新时逐个执行。

---

## 精灵帧表生成（特殊流程）

基于 Q版设计图 + JSON 提示词，生成角色精灵帧动画表。每个动作需按方向拆分为独立任务。

1. 读取精灵帧目录文件（如 `精灵帧目录.md`），获取动画列表
2. 筛选状态为"提示词"的动画，读取对应 JSON 文件
3. **方向拆分**（见下方规则），每个方向作为独立任务
4. 定位参考图：角色目录下的 Q版设计图
5. 为每个方向构建提示词（见提示词构建模板）
6. 提交图生图任务 → 下载保存到精灵帧文件夹
7. 更新 `精灵帧目录.md` 中该动画状态为"初稿"

**方向拆分规则：**

JSON 中 `direction` 和 `camera` 字段以 ` | `（空格管道空格）分隔两个方向值：

```json
"direction": "正面 | 背面"
"camera": "3/4 front left view | 3/4 back left view"
```

拆分为两个独立生成任务：

| 任务 | direction | camera |
|------|-----------|--------|
| 正面 | 正面 | 3/4 front left view |
| 背面 | 背面 | 3/4 back left view |

> **注意**：pose descriptions 中也可能出现 `|`（如 `双手|双臂微微抬起`），这是肢体描述的并列关系，不要拆分。方向分隔符特征是 **两侧有空格**（` | `），pose 中的 `|` 无空格。

**提示词构建模板：**

将拆分出来的方向填入 JSON ，每个方向使用对应的 camera 值，之后将提示词格式化为一串不带换行符的json string

**参考图选择：**

使用`精灵帧概览.md`中的参考图

**输出命名：** `{角色id}_{动作类型}_{方向}_{YYYY-MM-DD}_{序号}.png`

| 动画名称 | 动作类型标识 |
|---------|------------|
| 待机 | idle |
| 移动 | move |
| 普通攻击 | attack |
| 终极技能 | ultimate |
| 技能1 | skill1 |
| 技能2 | skill2 |
| 翻滚闪避 | dodge |
| 受击 | hit |
| 死亡 | death |
| 加快技能CD | skill_cd |

示例：`char_002_move_front_2026-05-01_01.png`

---

## 脚本用法

### submit — 提交生成任务

```bash
# 文生图
python scripts/ofoxai_api.py submit "提示词" --size 1024x1024 --quality low

# 图生图（单图）
python scripts/ofoxai_api.py submit "编辑指令" --image ./ref.png --size 1024x1024

# 多图引用
python scripts/ofoxai_api.py submit "合成指令" --image ./ref1.png --image ./ref2.png --size 1024x1024

# 直接保存（跳过 wait 步骤）
python scripts/ofoxai_api.py submit "提示词" --size 1024x1024 -o ./output.png
```

| 参数 | 必填 | 说明 |
|------|:----:|------|
| prompt | Y | 图像描述文本 |
| `--model` | N | 默认 `openai/gpt-image-2` |
| `--size` | N | 默认 `1024x1024`，gpt-image-2 最大边 3840px，两边 16 的倍数 |
| `--quality` | N | 默认 `low`。gpt-image: `low`/`medium`/`high` |
| `--n` | N | 生成数量，默认 1 |
| `--image` | N | 参考图路径，可多次指定 |
| `--response-format` | N | `b64_json`（默认）或 `url` |
| `-o, --output` | N | 直接保存到指定路径（跳过 wait 步骤） |

### wait — 保存结果

```bash
python scripts/ofoxai_api.py wait '<json_response>' ./output.png
python scripts/ofoxai_api.py wait ./result.json ./output.png
```

### download — 下载图片

```bash
python scripts/ofoxai_api.py download <url> ./output.png
```

## 错误处理

| HTTP 状态码 | 处理方式 |
|-------------|---------|
| 400 | 检查参数格式和尺寸约束 |
| 401 | 检查 API Key |
| 402 | 余额不足，充值后重试 |
| 429 | 等待后重试 |
| 500 | 重试 |

## 参考

- 完整 API 参数见 [references/api-reference.md](references/api-reference.md)
- 图片尺寸规格见项目 CLAUDE.md
