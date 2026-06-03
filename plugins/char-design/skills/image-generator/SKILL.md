---
name: image-generator
description: |
  调用 OfoxAI Images API 生成角色美术图片。支持文生图和图生图（含多图引用）。
  按目标节点类型操作：DesignSheet（文生图）、IllusDesign（图生图）、StandingIllustration（图生图）。
  触发条件：(1) 需要使用 OfoxAI 生成图片 (2) 图节点 status=1 需要生成图片
  前置：art-prompter（节点 status ≥ 1），neo4j-helper（读取数据、更新图节点）。
allowed-tools: Read, Bash, Write, Edit
---

# OfoxAI 图片生成

从 Neo4j 图节点查询提示词路径，调用 OfoxAI Images API 生成图片。

脚本：`${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py`
API Key：通过 `--api-key` 传入，或环境变量 `OFOX_API_KEY`，或向上搜索 `settings.json` 的 `ofox` 字段。

## 流程

### 1. 确定目标节点

由 agent 传入目标节点 ID。通过 neo4j-helper（schema_path=`schema/02_角色美术.md`）查询节点类型和状态：

```cypher
MATCH (n {id: $node_id})
RETURN labels(n)[0] AS type, n.status AS status,
       n.prompt_path AS prompt_path, n.image_path AS image_path
```

前置检查：status 必须为 1（提示词已完成），否则跳过。

### 2. 读取提示词

根据 prompt_path 读取提示词文件内容。

- **DesignSheet**：读取 `设计图提示词.md`，提取三视图提示词完整文本
- **IllusDesign**：读取立绘设计提示词，提取完整文本
- **StandingIllustration**：读取变体提示词，提取完整文本

文件缺失时终止该节点并报告错误。

### 3. 生成图片

> **`--size` 必须显式传入**。从提示词文件规格确定，无法确定时向用户确认。

#### DesignSheet（文生图）

从提示词直接生成三视图：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py" submit "<三视图提示词>" --size 1024x1024 --quality low -o "./06_角色美术/<char_id>/设计图.png" --api-key <API_KEY>
```

#### IllusDesign（图生图）

以 DesignSheet 图片为参考图生成：

```bash
# 先查询上游 DesignSheet 的 image_path
python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py" submit "<立绘设计提示词>" --image "<DesignSheet.image_path>" --size 1024x1024 --quality low -o "./06_角色美术/<char_id>/立绘设计/<scene_id>/设计图.png" --api-key <API_KEY>
```

#### StandingIllustration（图生图）

以 IllusDesign 图片为参考图生成：

```bash
# 先查询上游 IllusDesign 的 image_path
python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py" submit "<变体提示词>" --image "<IllusDesign.image_path>" --size 1024x1024 --quality low -o "./06_角色美术/<char_id>/立绘/<scene_id>/<variant_label>/立绘.png" --api-key <API_KEY>
```

### 4. 更新图节点

通过 neo4j-helper 更新目标节点的 image_path 和 status：

> "更新 <节点类型> 节点（id 为 <node_id>），设置 image_path 为 '<图片路径>'，status 设为 2"

---

## 精灵帧表生成（特殊流程）

基于 Q版设计图 + JSON 提示词生成角色精灵帧动画表。详见 [references/sprite-sheet.md](references/sprite-sheet.md)。

---

## 脚本参数

### submit

```bash
python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py" submit "<prompt>" [options]
```

| 参数 | 必填 | 说明 |
|------|:----:|------|
| prompt | Y | 图像描述文本 |
| `--api-key` | N | API Key |
| `--model` | N | 默认 `openai/gpt-image-2` |
| `--size` | Y | 输出尺寸，gpt-image-2 最大边 3840px，两边 16 的倍数 |
| `--quality` | - | **已强制为 `low`** |
| `--n` | N | 生成数量，默认 1 |
| `--image` | N | 参考图路径，可多次指定 |
| `-o, --output` | N | 直接保存路径（跳过 wait） |

### wait / download

```bash
python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py" wait '<json|file>' ./output.png
python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py" download <url> ./output.png
```

## 错误处理

| HTTP 状态码 | 处理 |
|-------------|------|
| 400 | 检查参数格式和尺寸 |
| 401 | 检查 API Key |
| 402 | 余额不足，充值后重试 |
| 429 | 等待后重试 |
| 500 | 重试 |

## Resources

- 完整 API 参数见 [references/api-reference.md](references/api-reference.md)
- 精灵帧表详细规则见 [references/sprite-sheet.md](references/sprite-sheet.md)
