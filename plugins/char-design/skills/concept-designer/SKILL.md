---
name: concept-designer
description: |
  从 Neo4j 提取角色信息，生成角色美术设定（外貌特征、色彩标签、体态气质）和语言风格（口吻、词汇偏好、情绪模式）。
  将结果写入 AppearanceStyle / CostumeStyle / LanguageStyle 三个独立图节点。
  触发条件：(1) 需要生成角色美术设定 (2) 需要生成角色语言风格 (3) 角色设计阶段
  前置：neo4j-helper（读取角色数据、更新图节点）。
allowed-tools: Read, Bash, Write, Edit
---

# 角色设计

从 Neo4j 提取角色信息，结合用户指定的设计目标，生成美术设定和语言风格文档，并更新对应的图节点。

## 流程

### 1. 获取角色数据

通过 neo4j-helper 查询待设计角色的完整信息（schema_path=`schema/01_叙事基础.md`）：
- Character 节点属性（姓名、性别、阵营、description 等）
- relation 边（角色关系）
- involved 边 → Event 节点（参与事件）
- link 边 → Info 节点（关联信息）

同时查询关联的美术节点当前状态（schema_path=`schema/02_角色美术.md`）：
- AppearanceStyle 节点（通过 has_appearance 边）
- CostumeStyle 节点（通过 has_costume 边）
- LanguageStyle 节点（通过 has_voice_style 边）

仅处理 status=0 的节点。已有 status ≥ 1 的跳过不降级。

### 2. 判断产出

| 角色类型 | 美术设定 | 语言风格 |
|---------|---------|---------|
| 主角(char) | 完整版 | 生成 |
| NPC | 完整版 | 生成 |
| 怪物(enemy) | 简化版 | 不生成 |

用户明确指定了设计目标时，以用户要求为准。

### 3. 生成文档

写入 `05_角色设计/` 目录：

```
05_角色设计/
├── char/
│   └── char_001/
│       ├── 美术设定.md
│       └── 语言风格.md
├── npc/...
└── enemy/
    └── enemy_001/
        └── 美术设定.md
```

命名规则：第一层=角色类型（char/npc/enemy），第二层=角色ID。已有文件时仅更新内容。

按模板生成（见 references/）：
- `美术设定.md` — 按 [template-角色美术设定.md](references/template-角色美术设定.md)
- `语言风格.md` — 按 [template-角色语言风格.md](references/template-角色语言风格.md)

**数据映射**：

| 图数据来源 | 映射到模板字段 |
|-----------|-------------|
| Character 节点属性 | 身份概要、外貌基础 |
| Character.description | 核心关键词、视觉气质 |
| relation 边 | 阵营归属、社交定位 |
| involved → Event | 体态气质、情绪模式 |
| link → Info | 核心创伤、背景故事 |
| 用户额外约束 | 覆盖对应字段 |

### 4. 更新图节点

通过 neo4j-helper（schema_path=`schema/02_角色美术.md`）分别更新三个独立图节点。**不修改 Character 节点**。

**更新 AppearanceStyle 节点**：

> "更新 AppearanceStyle 节点（id 为 <appearance_id>），设置 appearance、color_direction、shape_language、visual_tone、first_impression、memory_points 字段，status 设为 1"

字段映射（从美术设定.md 提取）：

| 美术设定字段 | 图节点属性 |
|------------|----------|
| 外貌描述 | appearance |
| 主色调 | color_direction |
| 形状语言 | shape_language |
| 视觉气质 | visual_tone |
| 第一印象 | first_impression |
| 记忆点 | memory_points |

**更新 CostumeStyle 节点**：

> "更新 CostumeStyle 节点（id 为 <costume_id>），设置 default_outfit、material_direction、posture、accessories 字段，status 设为 1"

字段映射：

| 美术设定字段 | 图节点属性 |
|------------|----------|
| 默认着装 | default_outfit |
| 材质方向 | material_direction |
| 体态气质 | posture |
| 配饰 | accessories |

**更新 LanguageStyle 节点**（怪物跳过）：

> "更新 LanguageStyle 节点（id 为 <voice_id>），设置 path 为 '05_角色设计/<类型>/<角色编号>/语言风格.md'，description 为语言风格概要，status 设为 1"

## 参考文档

- [角色美术设定模板](references/template-角色美术设定.md)
- [角色语言风格模板](references/template-角色语言风格.md)
