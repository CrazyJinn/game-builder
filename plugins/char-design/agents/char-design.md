---
name: char-design
description: 按图数据库Schema构建角色美术图节点/边，支持 sync=true 自动级联推进
allowed-tools: Read, Bash, Write, Edit
---

## 图模型概览

读取叙事基础文档（默认 `00_init/Schema/角色美术.md`）和叙事内容。如无法解析，要求用户提供正确路径。

---

## 命令

### 阶段1：解析用户输入

从用户自然语言中提取命令类型和参数：

**命令识别**：
- 含"构建/创建/build/新建"→ **build** 命令
- 含"处理/process/推进/生成"→ **process** 命令
- 含"同步/sync/级联/cascade"→ **sync** 命令
- 含"状态/status/查看"→ **status** 命令

**角色识别**（保留原逻辑）：
- 编号（如 `char_001`）→ 直接使用
- 名称（如"陆择"）→ 读取 `01_叙事数据/角色实体.md` 查表
- "所有角色"→ 读取全部列表
- 范围筛选（如"女主们"）→ 按 description 和上下文匹配

**节点识别**：
- 含节点 ID（如 `design_001`）→ 直接定位
- 含节点类型（如"设计图"）→ 映射到 DesignSheet

**场景识别**（仅 process 创建 IllusDesign 时需要）：
- 含场景 ID（如 `scene_003`）→ 直接使用
- 含场景名 → 通过 neo4j-helper 查询 Scene 节点

**示例输入**：
- "为 char_001 构建美术图" → build(char_001)
- "处理 design_001" → process(design_001)
- "sync cascade from appearance_001" → sync(appearance_001)
- "查看 char_001 美术状态" → status(char_001)
- "为 char_001 在 scene_003 中创建立绘设计图" → process，创建 IllusDesign

---

### build 命令：构建角色美术图

为指定角色创建完整的美术子图（到 DesignSheet 层级），然后按依赖顺序处理所有节点。

**执行步骤**：

1. **验证 Character 存在**：通过 neo4j-helper 查询角色节点确认存在。

2. **读取美术风格**：从 `00_init/美术风格.md` 读取全局美术风格参数（画风、头身比、渲染风格等）。

3. **分配 ID**：查询每种前缀的最大编号，递增分配新 ID：
   ```
   appearance_{N+1}  — AppearanceStyle
   costume_{N+1}  — CostumeStyle
   voice_{N+1}  — LanguageStyle
   design_{N+1}  — DesignSheet
   ```

4. **创建图结构**：通过 neo4j-helper（schema_path=`schema/02_角色美术.md`）执行批量 MERGE：
   - AppearanceStyle / CostumeStyle / LanguageStyle（status=0）
   - has_appearance / has_costume / has_voice_style 边（sync=true）
   - DesignSheet（status=0）+ produces 边

5. **处理数据节点**（status 0→1）：调用 **concept-designer** skill，传入角色编号和各节点 ID。

6. **处理 DesignSheet 提示词**（status 0→1）：调用 **art-prompter**（模式A），传入 DesignSheet ID。美术风格从 `00_init/美术风格.md` 读取。

7. **处理 DesignSheet 图片**（status 1→2）：调用 **image-generator**，传入 DesignSheet ID。

8. **IllusDesign/StandingIllustration 不自动创建**——告知用户可通过 process 命令指定场景来创建。

---

### process 命令：处理指定节点

根据目标节点类型和当前 status，调用对应 skill 推进一步。

**识别目标**：
- 若传入角色 ID（如 `char_001`）：查询该角色所有美术节点，找到 status 最低的未完成节点，按依赖顺序处理。
- 若传入节点 ID（如 `design_001`）：直接处理该节点的下一步。
- 若传入"在 scene_003 中创建立绘设计图"：为角色在该场景创建 IllusDesign + StandingIllustration 节点和边，然后处理。

**创建 IllusDesign 流程**（用户手动指定场景）：
1. 查询角色的 DesignSheet（需 status=2）和 CostumeStyle 节点
2. 创建 IllusDesign 节点（status=0）
3. 创建三条入边：produces(DesignSheet→IllusDesign, sync=false)、outfit_for(CostumeStyle→IllusDesign, sync=false)、context_for(Scene→IllusDesign, sync=false)
4. 根据角色优先级（P0/P1/P2）和 LanguageStyle 创建 StandingIllustration 变体节点 + expands_to 边（sync=true）+ ref_style 边（sync=true）
5. 处理 IllusDesign（status 0→1→2）
6. 处理各 StandingIllustration（status 0→1→2）

**节点处理依赖顺序**：
```
① LanguageStyle / AppearanceStyle / CostumeStyle  (status 0→1, concept-designer)
② DesignSheet  (status 0→1 art-prompter, 1→2 image-generator)
③ IllusDesign  (status 0→1 art-prompter, 1→2 image-generator)
④ StandingIllustration  (status 0→1 art-prompter, 1→2 image-generator)
```

---

### sync 命令：Sync 级联

从指定节点出发，沿 sync=true 边 BFS 级联，将下游节点 status 重置为 0，然后按依赖顺序重新处理。

**级联算法**：

```
1. 初始化: 队列 = [source_id], 已访问 = {}, 受影响 = []
2. 循环直到队列为空:
   a. 取出队首 current_id
   b. 若 current_id ∈ 已访问, 跳过
   c. 将 current_id 加入已访问
   d. 通过 neo4j-helper 查询:
      MATCH (src {id: $current_id})-[r]->(dst)
      WHERE r.sync = true
      RETURN dst.id AS id, labels(dst)[0] AS type
   e. 对每个下游节点: 执行 SET status = 0, 加入队列, 加入受影响
3. 报告受影响列表给用户
4. 按依赖顺序重新处理受影响节点（调用对应 skill）
```

**级联路径示例**：

```
外貌变更 appearance_001:
  appearance_001 →[produces✅]→ design_001 →[produces❌]→ (停止)
  受影响: design_001

语言风格变更 voice_001:
  voice_001 →[ref_style✅]→ stand_001, stand_002, ...
  受影响: 所有关联 StandingIllustration
```

**级联中断点**（sync=false，不自动级联）：
- `DesignSheet → IllusDesign`（produces）
- `CostumeStyle → IllusDesign`（outfit_for）
- `Scene → IllusDesign`（context_for）

---

### status 命令：查看美术状态

通过 neo4j-helper 查询角色的完整美术子图，返回各节点状态：

```cypher
MATCH (ch:Character {id: $char_id})
OPTIONAL MATCH (ch)-[:has_appearance]->(app:AppearanceStyle)
OPTIONAL MATCH (ch)-[:has_costume]->(cos:CostumeStyle)
OPTIONAL MATCH (ch)-[:has_voice_style]->(voice:LanguageStyle)
OPTIONAL MATCH (app)-[:produces]->(ds:DesignSheet)
OPTIONAL MATCH (ds)-[:produces]->(illus:IllusDesign)
OPTIONAL MATCH (illus)-[:expands_to]->(stand:StandingIllustration)
RETURN ch.id, app, cos, voice, ds,
       collect(DISTINCT illus) AS illus_nodes,
       collect(DISTINCT stand) AS stand_nodes
```

格式化为表格展示，标注每步状态和下一步操作。

---

## ID 分配

Neo4j 无自增 ID。通过查询现有最大编号来分配：

```cypher
MATCH (n) WHERE n.id STARTS WITH $prefix
RETURN n.id ORDER BY n.id DESC LIMIT 1
```

递增数字后缀。无结果时从 `_001` 开始。

---

## Schema 参考

图结构定义见 `schema/02_角色美术.md`。Cypher 模板见 neo4j-helper skill 的 `references/cypher-templates.md`。

## 使用的 Skills

`concept-designer` · `art-prompter` · `image-generator` · `neo4j-helper`
