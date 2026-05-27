---
name: 角色概念设计
description: "从 Neo4j 图数据库提取角色信息，根据用户自然语言中指定的设计目标，生成角色美术设定（外貌特征、色彩标签、体态气质）和角色语言风格（口吻、词汇偏好、情绪模式）。触发条件：(1) 需要生成角色美术设定 (2) 需要生成角色语言风格 (3) 角色设计阶段"
allowed-tools: Read, Bash, Write, Edit, Agent
---

# 角色设计

从 Neo4j 图数据库提取角色信息，结合用户自然语言中的设计目标，生成结构化的**角色美术设定**和**角色语言风格**文档。

### 3. 判断产出

根据角色类型和用户指定的设计目标决定生成内容：

| 角色类型 | 美术设定 | 语言风格 |
|---------|---------|---------|
| 主角(char) | 完整版 | 生成 |
| NPC | 完整版 | 生成 |
| 怪物(enemy) | 简化版 | 不生成 |

用户明确指定了设计目标时，以用户要求为准。

### 4. 生成文档

为每个角色生成对应文档，写入 `05_角色设计/` 目录：

```
05_角色设计/
├── 角色设计总览.md
├── char/
│   └── char_001/
│       ├── 美术设定.md
│       └── 语言风格.md
├── npc/
│   └── npc_001/
│       ├── 美术设定.md
│       └── 语言风格.md
└── enemy/
    └── enemy_001/
        └── 美术设定.md
```

**命名规则**：第一层=角色类型（char/npc/enemy），第二层=角色ID，文件名=`美术设定.md` / `语言风格.md`

按模板生成（模板见 references/）：
- `美术设定.md` — 按 [template-角色美术设定.md](references/template-角色美术设定.md)，主角/NPC 用完整版，怪物用简化版
- `语言风格.md` — 按 [template-角色语言风格.md](references/template-角色语言风格.md)，仅主角和 NPC

**数据映射**（图数据 → 模板字段）：

| 图数据来源 | 映射到模板字段 |
|-----------|-------------|
| char 节点属性（姓名、性别、阵营等） | 身份概要、外貌特征（基础） |
| char 节点 description | 角色核心关键词、视觉气质定义 |
| relation 边（type, detail） | 阵营归属、社交定位（影响色彩/气质） |
| involved 边 → Event 节点 | 体态气质（行为推导）、情绪模式（情境来源） |
| link 边 → Info 节点 | 核心创伤、背景故事补充 |
| 用户额外约束 | 覆盖对应字段的创作方向 |

已有文件时仅更新内容，每次更新重新生成总览。

### 5. 更新总览

更新 `05_角色设计/角色设计总览.md`（结构见 [references/overview-structure.md](references/overview-structure.md)）

### 6. 更新 Neo4j status 与路径

将已处理角色的 status 更新为 `1`（角色设计完成），同时写入产出文档的相对路径。

**通过 neo4j-helper skill 以自然语言执行更新**：

> "更新编号为 <角色编号> 的角色节点，设置 status 为 1，art_design_path 为 '05_角色设计/<类型>/<角色编号>/美术设定.md'，voice_style_path 为 '05_角色设计/<类型>/<角色编号>/语言风格.md'"

其中 `<类型>` 从编号前缀推断（char_→char, npc_→npc, enemy_→enemy）。怪物不生成语言风格，`voice_style_path` 不设置。批量更新时逐个执行。若角色已有 status >= 1，跳过不降级。

## 参考文档

- [总览结构](references/overview-structure.md)
- [角色美术设定模板](references/template-角色美术设定.md)
- [角色语言风格模板](references/template-角色语言风格.md)
- [neo4j-helper SKILL](../neo4j-helper/SKILL.md) — 图数据库自然语言查询能力（所有 Neo4j 交互通过此 skill 以自然语言完成）
