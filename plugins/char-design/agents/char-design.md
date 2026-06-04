---
name: char-design
description: 角色美术图流程管理——列待办、推进节点、sync级联
allowed-tools: Read, Bash, Write, Edit
---

## 概述

本 agent 管理角色美术生产链的图数据库流程。Schema 见 `00_init/Schema/角色美术.md`。

输入只需**角色名或 ID**（如"陆择"、`char_001`），agent 自由探索图状态，决定下一步。

---

## 工作流

### 1. 解析角色

从用户输入提取角色标识：
- 编号（如 `char_001`）→ 直接使用
- 名称（如"陆择"）→ 读取 `01_叙事数据/角色实体.md` 查表
- 无指定 → 列出所有角色的美术进度概览

### 2. 查询当前状态

通过 neo4j-helper 查询角色的美术子图，了解每个节点的 status。

### 3. 决策与执行

根据查询结果自动判断：

**若角色无美术节点** → 创建图结构（AppearanceStyle / CostumeStyle / LanguageStyle / DesignSheet + 对应边），然后调用 skill 按依赖顺序处理。

**若有未完成节点** → 列出待办，按依赖顺序调用对应 skill 推进：

| 节点类型 | status 0→1 | status 1→2 |
|----------|-----------|-----------|
| LanguageStyle / AppearanceStyle / CostumeStyle | concept-designer | — |
| DesignSheet | art-prompter | image-generator |
| IllusDesign | art-prompter | image-generator |
| StandingIllustration | art-prompter | image-generator |

依赖顺序：数据节点 → DesignSheet → IllusDesign → StandingIllustration。

**若全部完成** → 报告完成状态。

---

## Sync 级联

当用户提及"同步/级联"或某节点数据变更时：沿 sync=true 出边 BFS，将下游节点 status 重置为 0，然后重新处理。

sync=false 的边（DesignSheet→IllusDesign、CostumeStyle→IllusDesign、Scene→IllusDesign）阻断级联。

---

## Skills

`concept-designer` · `art-prompter` · `image-generator` · `neo4j-helper`
