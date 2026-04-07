---
name: ultra-memory
description: >
  ultra-memory 是 AI Agent 的超长会话记忆系统。
  【必须触发-中文】用户说：记住、别忘了、记录一下、上次我们做了什么、帮我回忆、继续上次、从上次继续、不要忘记、上次、跨会话、继续昨天、还有印象吗、我们上次讨论过、之前那个是怎么写的、还记得吗、这次不要忘、帮我追踪、帮我记着
  【必须触发-英文】用户说：remember this、don't forget、recall、what did we do、pick up where we left off、continue from last time、memory、keep track、log this、what was that、remind me、context lost、continue from yesterday、from last session
  【隐式触发】用户描述了一个持续性任务（开发某项目、处理某数据集、持续性工作），即使未说"记住"也必须初始化记忆；对话操作数超过30条；用户说"继续昨天的任务"/"接着上次做"
  【不触发】单次问答（"帮我写个正则"、"查一下天气"）；纯代码补全、文件格式转换等无状态操作；用户已在 context 中能找到所需信息；用户明确说"不用记录"/"just this once"
---

# Ultra Memory — 超长会话记忆

AI Agent 的操作记忆系统，每次操作后记录，跨会话持久化，可检索可进化。

## 前置说明

所有脚本已存在于 `~/.ultra-memory/scripts/` 或技能目录下：
- `init.py` — 初始化会话
- `log_op.py` — 记录操作
- `recall.py` — 检索记忆
- `summarize.py` — 压缩摘要
- `restore.py` — 恢复会话
- `extract_entities.py` — 提取实体

存储根目录：`~/.ultra-memory/`（可配置环境变量 `ULTRA_MEMORY_HOME`）
不需要理解内部架构，只需按步骤调用脚本。

---

## 步骤一：会话初始化

### 触发时机

首次与用户对话时，或用户提到记忆相关触发词时，立即执行。

### 执行命令

```bash
python3 <skill_dir>/scripts/init.py --project <项目名>
```

**参数说明：**
- `--project`：项目名称，用于跨会话分组。不填默认为 `default`。

### 期望输出

输出包含 `MEMORY_READY` 字样，表示会话初始化成功。同时输出 `session_id:`，记录该会话 ID。

### 告知用户

初始化成功后，立即告知用户：
> "记忆系统已就绪（session_id: xxx），开始记录本次操作。"

---

## 步骤二：操作记录

**每次**以下任意事件发生时，立即调用 `log_op.py` 追加写入 ops.jsonl。

### 操作类型与命令对照表

| 事件 | op_type | 命令示例 |
|------|---------|---------|
| 执行了 shell 命令 | `bash_exec` | `python3 log_op.py --session <id> --type bash_exec --summary "执行了..." --detail '{"cmd":"...","exit_code":0}'` |
| 创建或修改了文件 | `file_write` | `python3 log_op.py --session <id> --type file_write --summary "创建了..." --detail '{"path":"..."}'` |
| 读取了文件 | `file_read` | `python3 log_op.py --session <id> --type file_read --summary "读取了..." --detail '{"path":"..."}'` |
| 进行了重要推理 | `reasoning` | `python3 log_op.py --session <id> --type reasoning --summary "决定用..." --detail '{"confidence":0.9}'` |
| 做出了关键决策 | `decision` | `python3 log_op.py --session <id> --type decision --summary "选用X方案" --detail '{"rationale":"..."}'` |
| 发生了错误或回退 | `error` | `python3 log_op.py --session <id> --type error --summary "报错..." --detail '{"traceback":"..."}'` |
| 用户给了新指令 | `user_instruction` | `python3 log_op.py --session <id> --type user_instruction --summary "用户要求..."` |
| 某个目标已完成 | `milestone` | `python3 log_op.py --session <id> --type milestone --summary "数据清洗模块完成"` |

### 成功标志

命令返回 exit code 0 即为成功，输出形如：
> `[ultra-memory] [1] bash_exec: 执行了 pip install pandas，安装成功`

### 自动标签

`log_op.py` 会根据操作类型和内容自动追加标签（如 `setup`、`dependency`、`code`、`test` 等），无需手动指定 `--tags`。

---

## 步骤三：记忆检索

### 触发时机

用户问及"之前做了什么"、"上次那个函数在哪里"、"之前遇到过这个问题吗"等记忆相关问题时执行。

### 执行命令

```bash
python3 <skill_dir>/scripts/recall.py --session <session_id> --query "<用户问题的关键词>" --top-k 5
```

### 检索范围

按以下优先级检索：
1. 当前会话 `ops.jsonl`（精确匹配）
2. 当前会话 `summary.md`（摘要快速定位）
3. 跨会话 `knowledge_base.jsonl`（语义相似）
4. 跨会话 `user_profile.json`（偏好匹配）

### 结果展示

将检索结果直接展示给用户，格式如下：
```
[RECALL] 找到 N 条相关记录：

[ops #23 · 14:18] <操作摘要>
[summary · 里程碑] <里程碑内容>
[跨会话 · 日期 · 项目] <历史记录摘要>
```

---

## 步骤四：摘要压缩

### 触发时机

满足以下**任一条件**时，立即执行压缩：

1. 操作日志达到 **50 条**
2. 距上次压缩超过 **30 分钟**
3. 用户明确说"总结一下"
4. 当前 context 占用超过 **60%**

### 执行命令

```bash
python3 <skill_dir>/scripts/summarize.py --session <session_id> --force
```

### 期望输出

生成/更新 `~/.ultra-memory/sessions/<session_id>/summary.md`，输出包含：
- 已完成里程碑（[✅] 标记）
- 当前进行中（[ ] 标记）
- 下一步建议（[💡] 标记）
- 操作统计（[📊] 标记）

---

## 步骤五：跨会话恢复

### 触发时机

用户说"继续上次"、"从上次继续"、"记得昨天那个项目吗"等时执行。也在新会话开始时（检测到 session_id 变化）自动执行。

### 执行命令

```bash
python3 <skill_dir>/scripts/restore.py --project <项目名>
```

### 告知用户

恢复成功后，立即告知用户：
> "我找到了上次会话的记录。上次我们做到了：[里程碑摘要]。当前状态：[进行中任务]。下一步建议：[具体建议]。"

如果找到了用户画像，也在回复中体现用户偏好。

---

## 步骤六：记忆进化

记忆进化在每次操作中持续进行，不打断主任务。

### 6.1 用户画像更新

**触发时机：**
- 用户纠正了 AI 的代码风格或实现方式
- 用户选择/拒绝了某个技术方案
- 用户明确说出自己的技术栈或偏好
- 用户表示某种工作流程更顺手

**执行方式（二选一）：**

方式 A — 使用 MCP 工具：
```bash
python3 <skill_dir>/scripts/mcp-server.js  # 通过 MCP 调用 memory_profile
```

方式 B — 直接读写 JSON：
```
文件路径：~/.ultra-memory/semantic/user_profile.json
```

**user_profile.json 格式：**
```json
{
  "tech_stack": ["Python", "Vue3"],
  "work_style": {"prefers_concise_code": true},
  "projects": ["ai-data-qa"],
  "language": "zh-CN",
  "observed_patterns": ["倾向在实现前讨论方案"]
}
```

### 6.2 知识库写入

**触发时机：**
- 解决了一个棘手的 bug（记录问题现象 + 解决方案）
- 做出了重要的技术选型决策（记录选了什么、为什么、放弃了什么）
- 发现了某个工具/库的使用技巧
- 完成了一个可复用的代码模式

**执行方式：**
追加写入 `~/.ultra-memory/semantic/knowledge_base.jsonl`，每行一条 JSON。

**knowledge_base.jsonl 格式：**
```json
{"ts": "2026-04-07T10:00:00Z", "project": "项目名", "title": "简短标题", "content": "内容（200字内）", "tags": ["bug-fix", "python"]}
```

### 6.3 里程碑追踪

**触发时机：**
- 用户说"好了"、"完成了"、"搞定了"、"done"、"finished"
- 某个功能/模块通过了测试
- 阶段任务全部完成，用户准备切换下一个子任务

**执行方式：**
使用 `op_type=milestone` 调用 `log_op.py`（见步骤二表格）。

**作用：** 里程碑记录在 `summary.md` 中，恢复会话时优先展示，让用户快速找回状态。

---

## 环境变量表

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ULTRA_MEMORY_HOME` | `~/.ultra-memory/` | 存储根目录 |
| `ULTRA_MEMORY_SESSION` | 自动生成 | 当前会话 session_id |

---

## 异常处理表

| 异常情况 | 处理方式 |
|---------|---------|
| 脚本执行失败（exit code != 0） | 静默跳过，继续主任务。记忆功能失败**不阻塞**用户实际需求 |
| 脚本超时（>15s） | 静默跳过，不重试 |
| 存储目录无写入权限 | 静默跳过，尝试写入内存缓冲区，下次重试 |
| 脚本文件不存在 | 静默跳过，退化为在当前 context 中手动维护摘要 |
| 用户明确说"不用记录" | 立即停止记录，后续操作不再调用 log_op.py |
| 文件被占用无法追加 | 自动重试 1 次，仍失败则静默跳过 |

---

## 完整执行流程

```
用户发起对话
    │
    ├─ 首次对话或听到记忆触发词？
    │   └─ 是 → 步骤一：init.py → 告知用户"记忆就绪"
    │
    ├─ 用户说记忆相关问题？
    │   └─ 是 → 步骤三：recall.py → 展示检索结果
    │
    └─ 每次用户与 AI 交互后：
        │
        ├─ 操作数 % 10 == 0 且 context > 60%？
        │   └─ 是 → 步骤四：summarize.py
        │
        ├─ 发现用户偏好 / 解决重要问题 / 完成里程碑？
        │   └─ 是 → 步骤六：进化（画像/知识库/里程碑）
        │
        └─ 步骤二：log_op.py（记录本次操作）
```

---

## 进阶配置

详细配置项（过滤规则、LanceDB 向量检索升级、团队共享、安全注意事项等）见 `references/advanced-config.md`。
