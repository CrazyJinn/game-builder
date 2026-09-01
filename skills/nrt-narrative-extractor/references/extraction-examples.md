# 提取示例

## 示例 1：对话片段 → 节点 + 边 CSV

**输入**：
> 老莫在集市上对罗兰说："南方营地被魔物成群扫荡了，那些东西在往北走。"罗兰问："北边呢？"老莫："差不多。不过北边夏天下灰色的雪——那不正常。"

**提取过程**：

1. "南方营地被魔物成群扫荡了" → 结论层：南方营地被扫荡（知识层 1）
2. "那些东西在往北走" → 结论层：魔物向北迁徙（知识层 1），因果链：南方扫荡→向北迁徙
3. "北边夏天下灰色的雪" → 结论层：北边夏季降灰色雪（知识层 2）

**CSV 输出**：

nodes_info.csv:
```csv
id,title,content,knowledge_level
<snowflake_id>,南方营地被魔物成群扫荡,"老莫告知：南方营地被魔物成群扫荡，魔物在往北走",1
<snowflake_id>,魔物正在从南向北移动,魔物正在从南向北移动,1
<snowflake_id>,北边夏季降灰色雪,"北边夏天下灰色的雪，异常气象",2
```

nodes_location.csv:
```csv
id,name,description
<snowflake_id>,南方营地,被魔物成群扫荡的营地
<snowflake_id>,集市,老莫传递消息的地点
```

edges_link.csv:
```csv
from_id,to_id,type,detail,time
<snowflake_id>,<snowflake_id>,涉及,事件发生地,
<snowflake_id>,<snowflake_id>,涉及,消息传递地,
<snowflake_id>,<snowflake_id>,因果,南方扫荡导致魔物向北迁徙,
```

**实体 .md 输出**：

角色实体.md:
```markdown
| id | 姓名 | 性别 | description | character_tags | 上下文 |
|------|------|------|-------------|----------------|--------|
| <snowflake_id> | 老莫 | | 集市上传消息的人 | | 集市上传消息的人 |
```

场景实体.md:
```markdown
| id | 名称 | description |
|------|------|-------------|
| <snowflake_id> | 南方营地 | 被魔物成群扫荡的营地 |
| <snowflake_id> | 集市 | 老莫传递消息的地点 |
```

## 示例 2：角色背景片段 → 节点 + 关系 CSV

**输入**：
> "塞西莉亚和塞莉丝特是双胞胎修女，幼时被主教奥古斯都收养。塞西莉亚足不出户，纯洁不懂世事。塞莉丝特外出参加任务后逐渐觉醒自我意识。"

**提取过程**：

1. "双胞胎修女" → 已有角色关系
2. "幼时被主教收养" → 结论层：被教会收养（知识层 2）
3. "塞西莉亚纯洁不懂世事" → 结论层（知识层 2）
4. "塞莉丝特觉醒自我意识" → 结论层（知识层 2）

**CSV 输出**：

nodes_char.csv:
```csv
id,name,gender,description,birth_year,character_tags
<snowflake_id>,塞西莉亚,女,足不出户的修女，纯洁不懂世事,,纯洁,与世隔绝
<snowflake_id>,塞莉丝特,女,外出参加任务后觉醒自我意识的修女,,觉醒,自我意识
<snowflake_id>,奥古斯都,男,主教，收养了双胞胎修女,,主教,收养者
```

nodes_info.csv:
```csv
id,title,content,knowledge_level
<snowflake_id>,塞西莉亚和塞莉丝特被教会收养,"幼时被主教奥古斯都收养，双胞胎修女",2
<snowflake_id>,塞西莉亚纯洁不懂世事,"足不出户，纯洁不懂世事，长期不外出",2
<snowflake_id>,塞莉丝特觉醒自我意识,"外出参加任务后逐渐觉醒自我意识",2
```

edges_relation.csv:
```csv
from_id,to_id,type,detail,start_time,end_time
<snowflake_id>,<snowflake_id>,亲属,双胞胎修女,,
<snowflake_id>,<snowflake_id>,亲属,养父女关系,,
<snowflake_id>,<snowflake_id>,亲属,养父女关系,,
```

edges_link.csv:
```csv
from_id,to_id,type,detail,time
<snowflake_id>,<snowflake_id>,涉及,被收养,
<snowflake_id>,<snowflake_id>,涉及,被收养,
<snowflake_id>,<snowflake_id>,涉及,性格描述,
<snowflake_id>,<snowflake_id>,涉及,觉醒经历,
```

## 示例 3：只言片语 → 最小输出

**输入**：
> "教会的人来了之后，人的表情就变了。"

**提取**：结论层：教会到来导致居民行为异常（知识层 2）

**CSV 输出**：

nodes_info.csv:
```csv
id,title,content,knowledge_level
<snowflake_id>,教会到来导致居民异常,"教会的人来了之后，人的表情就变了",2
```

## 示例 4：事件片段 → 完整节点 + 边

**输入**：
> "2024年4月11日，陆择正式加入星耀电竞战队，成为战队队长。入职当天他在战队基地认识了经理林薇。"

**提取过程**：

1. "陆择正式加入星耀电竞" → 事件（行动），时间 2024-04-11
2. "成为战队队长" → 信息：陆择是队长（知识层 1）
3. "在战队基地认识了林薇" → relation: 认识

**CSV 输出**：

nodes_char.csv:
```csv
id,name,gender,description,birth_year,character_tags
<snowflake_id>,陆择,男,星耀电竞战队队长，沉默寡言的天才选手,,沉默寡言,队长
<snowflake_id>,林薇,女,星耀电竞经理,,经理
```

nodes_event.csv:
```csv
id,title,time,description,type
<snowflake_id>,陆择加入星耀电竞,2024-04-11,陆择正式加入星耀电竞战队，成为队长,行动
```

nodes_location.csv:
```csv
id,name,description
<snowflake_id>,星耀电竞基地,星耀电竞战队所在地
```

edges_involved.csv:
```csv
from_id,to_id,role,detail
<snowflake_id>,<snowflake_id>,当事人,加入战队
<snowflake_id>,<snowflake_id>,参与者,在基地认识陆择
```

edges_occurred_at.csv:
```csv
from_id,to_id,detail
<snowflake_id>,<snowflake_id>,入职地点
```

edges_relation.csv:
```csv
from_id,to_id,type,detail,start_time,end_time
<snowflake_id>,<snowflake_id>,同事,战队队长与经理,2024-04-11,
```

edges_link.csv:
```csv
from_id,to_id,type,detail,time
<snowflake_id>,<snowflake_id>,涉及,陆择身份,2024-04-11
<snowflake_id>,<snowflake_id>,涉及,事件关联信息,
```

nodes_info.csv:
```csv
id,title,content,knowledge_level
<snowflake_id>,陆择是星耀电竞队长,陆择担任星耀电竞战队队长,1
```
