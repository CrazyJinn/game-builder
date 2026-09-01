# 着装设定模板

> 为角色的事件场景设计着装方案，写入 CostumeStyle 图节点。
> Schema 定义见 `00_init/Schema/角色美术.md`。

---

## 各字段规则

**服装（garment）**：服装信息的**唯一数据源**，标签合成组合 = 材质 + 颜色 + 类型，也可以按需额外添加领型、滚边、层次、剪裁、质感氛围等。dashboard 按子维度选择后自动合成，如 `棉白衬衫`；多件用分号分隔，如 `棉白衬衫;蕾丝黑内衣` → `CostumeStyle.garment`

**着装风格 / 鞋类 / 配饰类型**：分别用 `outfit_style` / `footwear` / `accessory_type` 标签表达，配饰具体样式同理用自定义标签值补充。

**体态**：着装不再单独设计体态。IllusDesign 复用 DesignSheet 的静态站姿（角色默认体态已在外貌层 `appearance`）。标志性道具（咖啡杯、水壶、手账本等）的**类型**放入 `accessory_type` 标签，具体样式用自定义标签补充，不写入任何体态描述。
