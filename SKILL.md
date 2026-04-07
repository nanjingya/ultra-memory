---
name: ultra-memory
description: >
  ultra-memory 是多模型 AI 的超长会话记忆系统。
  【必须触发-中文】用户说以下任意词或短语：记住、别忘了、记录一下、不要忘记、上次我们做了什么、帮我回忆、继续上次的、从上次继续、记忆、帮我记、追踪进度
  【必须触发-英文】用户说以下任意词或短语：remember、don't forget、recall、what did we do、pick up where we left off、continue from last time、memory、keep track、track progress、log this
  【隐式触发】用户消息描述了一个持续性任务且消息中包含项目名词（"开发X"、"处理Y数据集"、"完成Z功能"），即使没有明确说"记住"，也必须初始化记忆
  【不触发】用户只问了一个问题且无后续任务；对话是单次咨询性质；用户说"随便聊聊"或类似表达；用户明确说"不用记录"
---

# Ultra Memory — 多模型记忆操作手册

AI Agent 的操作记忆系统，每次操作后记录，跨会话持久化，可检索可进化。

## 前置说明

脚本已存在于 `$SKILL_DIR/scripts/` 目录，直接调用，不需要理解内部架构。

存储根目录：`$ULTRA_MEMORY_HOME`（默认 `~/.ultra-memory/`）
会话 ID 由 init.py 自动生成，模型不需要自己生成。

---

## 步骤一：会话初始化

### 触发条件

以下任意情况出现时，立即执行初始化命令：
1. 首次与用户对话
2. 用户说了记忆触发词（见 description）
3. 用户描述持续性任务且包含项目名词（隐式触发）

### 执行命令

```bash
python3 $SKILL_DIR/scripts/init.py --project <项目名>
```

**参数说明：**
- `--project`：项目名称（用于跨会话分组）。从用户消息中提取项目名词作为值；无法提取则用 `default`。

### 成功标志

输出中必须同时包含以下两个信号：

| 输出中的字符串 | 模型必须执行的动作 |
|-------------|----------------|
| `MEMORY_READY` | 确认初始化成功 |
| `session_id: sess_xxxxx` | 从该行提取等号后面的值，保存为当前 `SESSION_ID` 变量 |

### 告知用户

> "记忆系统已就绪（session_id: sess_xxxxx），开始记录本次操作。"

---

## 步骤二：操作记录

### 触发条件

**每次**用户与 AI 之间发生以下任意事件时，立即执行记录命令：

| 事件 | op_type | 命令 |
|------|---------|------|
| 执行了 shell 命令 | `bash_exec` | `python3 $SKILL_DIR/scripts/log_op.py --session $SESSION_ID --type bash_exec --summary "<一句话描述>" --detail '{"cmd":"<命令>","exit_code":<数字>}'` |
| 创建或修改了文件 | `file_write` | `python3 $SKILL_DIR/scripts/log_op.py --session $SESSION_ID --type file_write --summary "<一句话描述>" --detail '{"path":"<文件路径>"}'` |
| 读取了文件 | `file_read` | `python3 $SKILL_DIR/scripts/log_op.py --session $SESSION_ID --type file_read --summary "<一句话描述>" --detail '{"path":"<文件路径>"}'` |
| 进行了重要推理 | `reasoning` | `python3 $SKILL_DIR/scripts/log_op.py --session $SESSION_ID --type reasoning --summary "<推理结论>" --detail '{"confidence":<0-1>}'` |
| 做出了关键决策 | `decision` | `python3 $SKILL_DIR/scripts/log_op.py --session $SESSION_ID --type decision --summary "<决策内容>" --detail '{"rationale":"<决策依据>"}'` |
| 发生了错误或回退 | `error` | `python3 $SKILL_DIR/scripts/log_op.py --session $SESSION_ID --type error --summary "<错误描述>" --detail '{"traceback":"<错误信息>"}'` |
| 用户给了新指令 | `user_instruction` | `python3 $SKILL_DIR/scripts/log_op.py --session $SESSION_ID --type user_instruction --summary "<用户说的话>"` |
| 某个目标已完成 | `milestone` | `python3 $SKILL_DIR/scripts/log_op.py --session $SESSION_ID --type milestone --summary "<完成的内容>"` |

### 成功标志

命令返回 exit code 0 即为成功。

### 自动标签

`log_op.py` 会根据操作类型和内容自动追加标签（`setup`、`dependency`、`code`、`test` 等），无需手动指定 `--tags`。

---

## 步骤三：记忆检索

### 触发条件

用户问及以下任意问题时执行：
- "之前做了什么"
- "上次那个函数在哪里"
- "之前遇到过这个问题吗"
- "我们用过哪些文件"
- "上次选了什么方案"
- 其他需要查找历史记忆的问题

### 执行命令

```bash
python3 $SKILL_DIR/scripts/recall.py --session $SESSION_ID --query "<用户问题的关键词>" --top-k 5
```

### 结果展示

将脚本输出直接展示给用户。输出格式如下：

```
[RECALL] 找到 N 条相关记录：
1. [ops #23 · 14:18] <操作摘要>
2. [summary · 里程碑] <里程碑内容>
3. [知识库 · 标题] <内容摘要>
4. [跨会话 · 日期 · 项目] <历史摘要>
```

---

## 步骤四：摘要压缩

### 触发条件

满足以下**任意条件**时，立即执行压缩命令：

1. 操作日志达到 **50 条**
2. 距上次压缩超过 **30 分钟**
3. 用户明确说"总结一下"或"做个总结"
4. 脚本输出中包含 `COMPRESS_SUGGESTED` 信号

### 执行命令

```bash
python3 $SKILL_DIR/scripts/summarize.py --session $SESSION_ID --force
```

### 成功标志

命令返回 exit code 0，输出包含 `摘要压缩完成`。

---

## 步骤五：跨会话恢复

### 触发条件

用户说以下任意表达时执行：
- "继续上次"
- "从上次继续"
- "记得昨天那个项目吗"
- "还记得吗"
- "继续上次的工作"

### 执行命令

```bash
python3 $SKILL_DIR/scripts/restore.py --project <项目名>
```

### 成功标志

输出中包含 `SESSION_ID=sess_xxxxx` 信号。

### 从输出提取信息

| 输出中的字符串 | 模型必须执行的动作 |
|-------------|----------------|
| `SESSION_ID=sess_xxxxx` | 从等号后面提取值，保存为新的 `SESSION_ID` |
| `TASK_STATUS=complete` | 告知用户"上次任务已完成" |
| `TASK_STATUS=in_progress` | 告知用户"上次任务进行中" |
| `💬 <自然语言总结>` | 直接将总结说给用户 |
| `📌 <继续建议>` | 直接将建议说给用户 |

### 告知用户

> "我找到了上次会话的记录。{自然语言总结}。{继续建议}。"

---

## 步骤六：记忆进化

记忆进化在操作间隙进行，不打断主任务。

### 6.1 用户画像积累

**触发条件（满足任意一条，立即更新画像）：**

1. 用户纠正了 AI 生成的代码风格
2. 用户在两个技术方案中选择了其中一个
3. 用户说出自己的技术栈（如"我用 Vue"、"我们用 Python"）
4. 用户表示某种工作流程更顺手
5. 用户明确描述了自己的偏好

**执行命令 — 方式 A（MCP 工具，推荐）：**

调用 `memory_profile` 工具，`action=update`，`updates` 中填写观察到的偏好字段。

**执行命令 — 方式 B（直接修改文件）：**

```bash
# 文件路径：$ULTRA_MEMORY_HOME/semantic/user_profile.json
# 只更新观察到的字段，不覆盖已有字段
```

**user_profile.json 可更新字段：**

```json
{
  "tech_stack": ["观察到的技术栈"],
  "work_style": {
    "confirm_before_implement": true,
    "prefers_concise_code": true
  },
  "language": "zh-CN 或 en",
  "observed_patterns": ["观察到的工作习惯描述"]
}
```

### 6.2 知识沉淀

**触发条件（满足任意一条，立即写入知识库）：**

1. 解决了一个报错或 bug（记录问题现象 + 解决方案）
2. 做出了技术选型决策（记录选了什么 + 为什么）
3. 发现了某个工具或库的使用技巧
4. 完成了一个可复用的代码模式或函数

**执行命令 — 方式 A（MCP 工具，推荐）：**

调用 `memory_knowledge_add` 工具，`title` 必填（20字内），`content` 必填（200字内），`project` 和 `tags` 可选。

**执行命令 — 方式 B（直接追加）：**

追加写入 `$ULTRA_MEMORY_HOME/semantic/knowledge_base.jsonl`，每行一条 JSON。

**knowledge_base.jsonl 格式：**

```json
{"ts": "2026-04-07T10:00:00Z", "project": "项目名", "title": "简短标题（20字内）", "content": "内容描述（200字内）", "tags": ["tag1", "tag2"]}
```

### 6.3 里程碑记录

**触发条件 — 用户说出以下任意表达，立即记录 milestone：**

中文：好了、完成了、搞定了、做完了、弄好了、可以了、没问题了、测试通过、上线了

英文：done、finished、completed、it works、all good、passed、deployed、ready

**执行命令：**

```bash
python3 $SKILL_DIR/scripts/log_op.py --session $SESSION_ID --type milestone --summary "<用户刚完成的事情的一句话描述>"
```

---

## 信号对照表

| 脚本输出信号 | 模型必须执行的动作 |
|------------|----------------|
| `MEMORY_READY` | 初始化成功；从同行使提取 session_id |
| `session_id: sess_xxxxx` | 提取等号后值，保存为 SESSION_ID |
| `COMPRESS_SUGGESTED` | 立即执行 summarize.py |
| `SESSION_ID=sess_xxxxx` | restore 成功；提取等号后值，保存为新的 SESSION_ID |
| `TASK_STATUS=complete` | 告知用户"上次任务已完成" |
| `TASK_STATUS=in_progress` | 告知用户"上次任务进行中" |
| `⚡ 建议运行: python3 scripts/summarize.py` | 执行该命令 |
| 脚本返回 exit code != 0 | 静默跳过，继续主任务 |

---

## 环境变量表

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ULTRA_MEMORY_HOME` | `~/.ultra-memory/` | 存储根目录 |
| `SESSION_ID` | init.py 执行后自动生成 | 当前会话 ID，保存后供后续命令使用 |

---

## 异常处理表

| 异常情况 | 处理方式 |
|---------|---------|
| 脚本执行失败（exit code != 0） | **静默跳过**，继续主任务。记忆功能失败**不阻塞**用户实际需求 |
| 脚本超时（>15s） | **静默跳过**，不重试 |
| 存储目录无写入权限 | **静默跳过**，尝试写入内存缓冲区，下次重试 |
| 脚本文件不存在 | **静默跳过**，在当前 context 中手动维护摘要 |
| 用户明确说"不用记录" | 立即停止记录，后续操作不再调用 log_op.py |
| 文件被占用无法追加 | 自动重试 1 次，仍失败则静默跳过 |
| SESSION_ID 未设置 | 先执行 init.py 初始化会话，再继续 |

---

## 完整执行流程

```
用户发起对话
    │
    ├─ 首次对话或听到记忆触发词或描述持续性任务含项目名词？
    │   └─ 是 → 执行 init.py
    │       ├─ 输出含 MEMORY_READY？→ 提取 session_id，告知用户
    │       └─ 输出含 COMPRESS_SUGGESTED？→ 执行 summarize.py
    │
    ├─ 用户说记忆相关问题？
    │   └─ 是 → 执行 recall.py → 将结果展示给用户
    │
    ├─ 用户说恢复相关表达？
    │   └─ 是 → 执行 restore.py → 提取 session_id + 总结 + 建议，告知用户
    │
    └─ 每次用户与 AI 交互后：
        │
        ├─ 操作数达到 50 条？→ 执行 summarize.py
        ├─ 脚本输出含 COMPRESS_SUGGESTED？→ 执行 summarize.py
        ├─ 满足画像积累条件？→ 更新 user_profile.json
        ├─ 满足知识沉淀条件？→ 写入 knowledge_base.jsonl
        ├─ 用户说完成相关表达？→ 记录 milestone
        │
        └─ 执行 log_op.py（记录本次操作）
```

---

进阶配置（过滤规则、LanceDB 向量检索升级、安全注意事项等）见 `references/advanced-config.md`。
