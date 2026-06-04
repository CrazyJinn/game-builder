---
name: concept-designer
description: |
  从 Neo4j 提取角色信息，生成美术设定和语言风格，直接写入 AppearanceStyle / CostumeStyle / LanguageStyle 图节点。
  触发条件：(1) 需要生成角色美术设定 (2) 需要生成角色语言风格 (3) 数据节点 status=0
  前置：neo4j-helper（读取角色数据、更新图节点）。
allowed-tools: Read, Bash, Write, Edit
---

# 角色设计

从 Neo4j 提取角色信息，生成美术设定和语言风格，直接写入图节点。不生成文档文件。

## 流程

### 1. 获取角色数据

通过 neo4j-helper 查询角色的完整信息：
- Character 节点属性 + relation / involved / link 等边
- 关联的 AppearanceStyle / CostumeStyle / LanguageStyle 节点（通过 has_appearance / has_costume / has_voice_style 边）

仅处理 status=0 的节点。

### 2. 判断产出

| 角色类型 | 美术设定 | 语言风格 |
|---------|---------|---------|
| 主角(char) / NPC | 完整版 | 生成 |
| 怪物(enemy) | 简化版 | 不生成 |

### 3. 生成并写入图节点

按模板（见 references/）生成内容，直接通过 neo4j-helper 写入图节点字段。

**更新 AppearanceStyle 节点**（status → 1）：

| 内容 | 图节点属性 |
|------|----------|
| 外貌描述 | appearance |
| 主色调 | color_direction |
| 形状语言 | shape_language |
| 视觉气质 | visual_tone |
| 第一印象 | first_impression |
| 记忆点 | memory_points |

**更新 CostumeStyle 节点**（status → 1）：

| 内容 | 图节点属性 |
|------|----------|
| 默认着装 | default_outfit |
| 材质方向 | material_direction |
| 体态气质 | posture |
| 配饰 | accessories |

**更新 LanguageStyle 节点**（怪物跳过，status → 1）：

| 内容 | 图节点属性 |
|------|----------|
| 语言风格概要 | description |

## 参考文档

- [角色美术设定模板](references/template-角色美术设定.md)
- [角色语言风格模板](references/template-角色语言风格.md)
