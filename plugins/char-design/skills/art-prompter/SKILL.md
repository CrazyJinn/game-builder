---
name: art-prompter
description: |
  根据图节点数据生成 AI 绘图提示词，直接写入图节点。三种模式：DesignSheet / IllusDesign / StandingIllustration。
  触发条件：(1) 生成设计图提示词 (2) 生成立绘设计提示词 (3) 生成立绘变体提示词
  前置：concept-designer（数据节点 status ≥ 1），neo4j-helper（读取数据、更新图节点）。
allowed-tools: Read, Bash, Write, Edit
---

# 美术提示词生成

根据图节点数据生成提示词，写入图节点的 `prompt` 字段。按目标节点类型分三种模式。

## 编写原则

自然语言优先，按 **主体→细节→风格** 组织，不使用负面提示词。提示词语言：**中文**。

模板参考：[template-设计图提示词.md](references/template-设计图提示词.md)、[template-立绘提示词.md](references/template-立绘提示词.md)

---

## 模式A：DesignSheet 提示词（status 0→1）

1. 通过 neo4j-helper 查询 DesignSheet 的上游 AppearanceStyle 和 CostumeStyle 节点
2. 从 `00_init/美术风格.md` 读取全局风格参数
3. 前置检查：AppearanceStyle.status = 1
4. 按模板生成提示词
5. 更新 DesignSheet 节点：`prompt = <提示词文本>`，`status = 1`

---

## 模式B：IllusDesign 提示词（status 0→1）

1. 查询 IllusDesign 的三个上游：DesignSheet、CostumeStyle、Scene
2. 前置检查：DesignSheet.status = 2
3. 综合上游数据生成场景适配提示词，写入 adaptation_notes
4. 更新 IllusDesign 节点：`prompt = <提示词文本>`，`adaptation_notes = <适配说明>`，`status = 1`

---

## 模式C：StandingIllustration 提示词（status 0→1）

1. 查询上游 IllusDesign 和 LanguageStyle
2. 前置检查：IllusDesign.status = 2
3. 提示词只描述表情和动作（外貌不重复，以 IllusDesign 图片为参考）
4. 更新 StandingIllustration 节点：`prompt = <提示词文本>`，`status = 1`

---

## 变体数量规则

| 优先级 | 变体数 | 典型变体 |
|-------|-------|---------|
| P0 主角 | 10 | 默认, 微笑, 生气, 悲伤, 惊讶, 思考, 坚定, 恐惧, 战斗, 受伤 |
| P0 核心 NPC | 10 | 根据角色定制 |
| P1 重要 NPC | 6 | 根据角色定制 |
| P2 背景 NPC | 2 | 默认 + 1 个关键表情 |

## 参考文档

- [设计图提示词模板](references/template-设计图提示词.md)
- [立绘提示词模板](references/template-立绘提示词.md)
