---
name: nrt-narrative-grower
description: |
  叙事图自增长：用图算法（10 种检查）识别叙事基础层缺口，产出结构化修改建议——一个 JSON 数组，每项含简短描述 + 开箱可执行 cypher。
  支持**可选聚焦入参**（角色名/id 或实体，限定检查子图）+ **多轮迭代**（每轮文件名带 round，审批写回后人工触发下一轮聚焦上轮新增节点）。范围限定**基础节点**（Character/Event/Location/Info/Choice + 8 条基础边）。
  只读图、不写图、不产 MD 草案。跑检查 → 落盘 02_剧情数据/<日期>_round<N>_<主题>_建议.json → 对话仅报路径与迭代提示。
  在需要给叙事图做体检、补全缺口、按角色/实体聚焦增长时使用。
argument-hint: [focus]
arguments:
  - focus
allowed-tools: Read, Bash, Write
---

# 叙事图自增长（nrt-narrative-grower）

用图算法扫描叙事基础层的缺口与可完善之处，产出**结构化修改建议**（JSON 数组）落盘。每条建议 = 简短自然语言描述 + 开箱可执行 cypher。支持**聚焦入参**收窄检查范围 + **多轮迭代**逐步丰富叙事图。

> **只读不写**：本 skill 仅查询图，不修改图。产出的 cypher 是供人工审阅/执行的**建议**，skill 自身不执行任何写操作、不创建节点/边、不产 MD 草案。
>
> **输出**：`02_剧情数据/<YYYY-MM-DD>_round<N>_<主题>_建议.json`（顶层 JSON 数组）。对话仅报文件路径、建议条数、迭代提示，不展开内容。
>
> **范围限定**：产出 cypher 只操作**基础节点**（Character/Event/Location/Info/Choice）+ 基础层边（relation/involved/occurred_at/at/link/evt_relation/presents/option）。美术/场景/剧情生产链节点不在自增长范围。

## 前置

```bash
CYPHER_EXEC="python ${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py"
SF_GEN="python ${CLAUDE_SKILL_DIR}/../../scripts/snowflake_base62.py"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
DATE=$(echo $TIMESTAMP | cut -dT -f1)        # YYYY-MM-DD，用于文件名
OUTPUT_DIR="02_剧情数据"                     # 建议 JSON 落盘目录（仓库根相对）
```

- Schema：[叙事基础.md](../../../00_init/Schema/叙事基础.md)（节点/边定义，含 Choice，生成 cypher 的事实来源）。
- 写 cypher 规则：见 [cypher_exec.py](../../scripts/cypher_exec.py) 顶部 docstring（内联值、MERGE 幂等、必须指定标签、查询加 LIMIT）。

---

## 流程

### 0. 解析聚焦入参 + 推导轮次

**聚焦入参 `focus`（可选）**：角色名/id 或其他基础实体名，限定本轮检查子图。

- 传入时：先查锚点 id（角色最常见）：
  ```cypher
  MATCH (c:Character) WHERE c.name='<focus>' OR c.id='<focus>' RETURN c.id AS id, c.name AS name LIMIT 1
  ```
  拿到锚点后，后续 10 条查询收窄到该实体 1-2 跳子图（模板见 [references/analyze-queries.md](references/analyze-queries.md)，每条都给「全图」与「focus 子图」两版）。锚点查不到则提示用户并停止。
- 未传时：全图扫描（向后兼容，等价于首轮体检）。

**推导轮次 `<N>`**：扫描 `${OUTPUT_DIR}/*round*_建议.json`，取现有最大 round +1（无则 1）。**主题**：focus 传入时取锚点 name，未传时用「全图」。这样同一天可跑多轮而不互相覆盖。

### 1. analyze — 跑 10 种图算法检查

用 `$CYPHER_EXEC -c "<cypher>" --json` 依次跑 10 种叙事缺口检查（Cypher + 必要 Python 后处理），详见 [references/analyze-queries.md](references/analyze-queries.md)：

temporal_gaps、character_arcs、implicit_relations、event_chains、scene_utilization、info_depth、subgraph_connectivity、relationship_evolution、bridge_scenes、narrative_density

focus 传入时各查询走「focus 子图」版（WHERE 收窄到锚点 1-2 跳）。

需 Python 后处理的（temporal_gaps 的 Day 解析等）由 LLM 读 `--json` 输出后自行计算（参照 graph_builder `discover_temporal_gaps`）。

### 2. 构造修改建议 JSON 数组

把 analyze 结果归纳为**修改建议 JSON 数组**，每项 = `{check, priority, reason, content, cypher}`（可附 `round`/`focus` 标注本轮来源）。生成规则（含补边/补节点两类 cypher 模板）见 [references/analyze-queries.md](references/analyze-queries.md) 末尾「输出格式」：

- **补边类**（implicit_relations→relation、event_chains→evt_relation、info_depth→link 等）：端点用 analyze 查出的**真实 id** `MATCH`，再 `MERGE` 边；创意字段（type/detail/role）由 LLM 推断**建议值**填入，并在 content 标注「可调整」。
- **补节点类**（temporal_gaps / character_arcs 需新增 Event；若体检发现叙事缺少某角色也可建议新增 Character）：`$SF_GEN -n 1 -q` 生成新 id，创意字段（title/time/type/description 或 name/description）LLM 推断建议值；需挂边时节点语句在前、边语句在后，`;` 分隔。
- 纯统计型检查（scene_utilization / bridge_scenes / narrative_density）若无明确补全动作则**不产出**，避免噪声。
- 全程 `MERGE`（幂等）、内联值、必须指定标签、字符串单引号转义。

### 3. 落盘 JSON

用 Write 工具写 `${OUTPUT_DIR}/${DATE}_round<N>_<主题>_建议.json`，内容为建议 JSON 数组（顶层即 `[...]`）。

**报告**：文件路径 + 建议总条数与 priority 分布（high/medium/low 各几条）+ **迭代提示**：
- 若本轮含**补节点类**建议（新增 Character/Event 等），列出建议新增的实体名，提示：「审批写回后，下轮可 `nrt-narrative-grower <新增实体名>` 聚焦为其补事件/关系。」
- 提示审批入口：dashboard `narrative_review` 逐条审，通过即把 cypher 写库；留痕 `_reviewed.json`（键=文件名#index），天然区分多轮。

---

## 多轮迭代示例

自增长设计为**人工触发的串行多轮**，每轮聚焦可逐步收敛：

1. **第 1 轮（全图）**：`nrt-narrative-grower`（无 focus）→ 体检全图，建议新增角色 X（补节点类）→ 落盘 `<日期>_round1_全图_建议.json`。
2. **审批写回**：dashboard 通过「新增角色 X」的 cypher，X 写入图。
3. **第 2 轮（聚焦 X）**：`nrt-narrative-grower X` → 检查收窄到 X，发现 X 无 involved 事件 → 建议为 X 补事件 + relation/involved 边 → 落盘 `<日期>_round2_X_建议.json`。
4. 以此类推，直到聚焦子图无明显缺口。

> 迭代闭环是**人工异步**：grower 产建议后即退出，不等待审批、不自动触发下一轮。用户 dashboard 审批写回后，手动发起下一轮。plot-design 剧情链不再内嵌自增长——outliner 报素材缺口后由用户手动跑本 skill 补全。

---

## 参考文档

- [分析查询（10 种检查）+ focus 子图限定 + 输出格式与 cypher 模板](references/analyze-queries.md)
- 节点/边定义：[00_init/Schema/叙事基础.md](../../../00_init/Schema/叙事基础.md)
