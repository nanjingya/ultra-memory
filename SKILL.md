---
name: ultra-memory
description: >
  给 AI Agent 提供超长会话记忆能力，5层记忆架构：操作日志 → 摘要 → 语义 → 实体索引 → 向量语义，做到不遗忘、可检索、跨会话持久化。零外部依赖，支持所有 LLM 平台（Claude Code、OpenClaw、GPT-4、Gemini、Qwen等）。
  【中文触发词】当用户提到"记住我说的""别忘了""上次我们做了什么""帮我回忆""会话记录""记忆""不要忘记""记录一下""跨会话""继续昨天""还有印象吗"时，必须触发。
  【英文触发词】当用户说 "remember this"、"don't forget"、"what did we do"、"recall"、"session memory"、"keep track"、"log this"、"what was that"、"remind me"、"memory"、"context lost"、"continue from yesterday" 时，必须触发。
  【隐式触发场景】以下情况即使用户未明确提及记忆，也应主动触发：(1) 用户说"继续昨天的任务"/"接着上次做"；(2) 对话操作数超过30条，context 使用率逼近阈值；(3) 任务被描述为跨天/跨周期的长期工程；(4) 用户提到"我们上次讨论过"但当前 context 中找不到相关内容。
  【不触发场景】以下情况不应触发，避免过度干扰：(1) 单次简短问答（"帮我写个正则"）；(2) 用户已在当前 context 内能找到所需信息；(3) 用户明确说"不用记录""just this once"；(4) 纯代码补全、文件格式转换等无状态任务。
  本 skill 自动初始化5层记忆架构并管理整个记忆生命周期。
  适用于：长编码任务、写长篇小说、跨天继续工作、AI数据标注流水线、项目管理型对话等需要持久记忆的场景。
---

# Ultra Memory — 超长会话记忆 Skill

## 设计目标

解决目前市面上记忆方案的核心缺陷：
- **claude-mem**：只记录压缩摘要，丢失操作细节
- **memory-lancedb-pro**：跨会话检索好，但会话内实时追踪弱
- **全量上下文法**：精度高但延迟 10s+，token 爆炸
- **本 Skill 的差异化**：三层架构 + 操作日志层，既记得住，又检索得快

---

## 架构总览：三层记忆模型

```
┌─────────────────────────────────────────────────┐
│  Layer 3: 跨会话语义层 (Semantic Store)           │
│  向量检索 · 用户偏好 · 项目知识 · 持久化 KV       │
├─────────────────────────────────────────────────┤
│  Layer 2: 会话摘要层 (Session Summary)            │
│  阶段性压缩 · 里程碑快照 · 决策记录               │
├─────────────────────────────────────────────────┤
│  Layer 1: 操作日志层 (Operation Log)  ← 核心差异化│
│  每步工具调用 · 文件变更 · 命令执行 · 推理链       │
└─────────────────────────────────────────────────┘
```

每层的文件存储位置：
- Layer 1: `~/.ultra-memory/sessions/<session_id>/ops.jsonl`
- Layer 2: `~/.ultra-memory/sessions/<session_id>/summary.md`
- Layer 3: `~/.ultra-memory/semantic/` (KV + embeddings index)

---

## 初始化流程

在会话开始或用户首次触发时，执行：

```bash
python3 ~/.openclaw/workspace/skills/ultra-memory/scripts/init.py
# 或（Claude Code 环境）
python3 <skill_dir>/scripts/init.py
```

这会：
1. 创建本次会话的目录结构
2. 生成唯一 `session_id`（时间戳 + hash）
3. 从 Layer 3 加载相关历史上下文到当前 context
4. 输出 `MEMORY_READY` 确认信号

---

## Layer 1：操作日志层（最重要）

### 记录时机

**每次**以下操作发生后，立即追加写入 `ops.jsonl`：

| 操作类型 | 触发场景 | 记录内容 |
|---------|---------|---------|
| `tool_call` | 调用任何 MCP 工具 | 工具名、入参、出参摘要、耗时 |
| `file_write` | 创建/修改文件 | 文件路径、变更类型、内容摘要 |
| `file_read` | 读取文件 | 文件路径、读取目的 |
| `bash_exec` | 执行 shell 命令 | 命令内容、stdout 前200字符、exit code |
| `reasoning` | 重要推理节点 | 推理摘要（50字内）、置信度、备选方案 |
| `user_instruction` | 用户给出新指令 | 指令原文、解析意图 |
| `decision` | 做出重要决策 | 决策内容、依据、放弃的方案 |
| `error` | 发生错误或回退 | 错误信息、处理方式 |

### 日志格式（ops.jsonl 每行一条）

```json
{
  "ts": "2026-04-02T14:23:01Z",
  "seq": 42,
  "type": "tool_call",
  "tool": "bash_tool",
  "summary": "执行 pip install pandas，安装成功",
  "detail": {
    "cmd": "pip install pandas --break-system-packages",
    "exit_code": 0,
    "stdout_preview": "Successfully installed pandas-2.2.0"
  },
  "tags": ["setup", "python", "dependency"]
}
```

### 写入方式

使用追加写入（append-only），永远不覆盖，保证操作历史完整性。

```bash
# Claude 在每次操作后调用
python3 ~/.openclaw/workspace/skills/ultra-memory/scripts/log_op.py \
  --session <session_id> \
  --type tool_call \
  --summary "执行了bash命令" \
  --detail '{"cmd": "...", "exit_code": 0}'
```

---

## Layer 2：会话摘要层

### 压缩时机

满足以下**任一条件**时触发摘要压缩：

1. 操作日志达到 **50 条**
2. 距上次压缩超过 **30 分钟**
3. 用户明确说"总结一下目前进展"
4. 当前 context 占用超过 **60%**

### 摘要内容结构（summary.md）

```markdown
# 会话摘要 — <session_id>
更新时间: 2026-04-02 14:30

## 目标
用户希望完成: <当前任务总目标>

## 已完成里程碑
- [✅ 14:10] 初始化项目结构，创建了 src/ 和 tests/ 目录
- [✅ 14:18] 安装依赖 pandas/numpy，配置 venv
- [✅ 14:25] 实现数据清洗函数 clean_df()，通过单元测试

## 当前进行中
- [ ] 实现评分函数 score_quality()，已完成60%
- [ ] 待处理: 边界情况处理（空值、超长文本）

## 关键决策记录
- 选用 LanceDB 而非 Chroma：原因是本地部署更稳定
- 评分维度采用 ZL/GN 双维度：对齐用户现有工作流程

## 用户偏好（本次会话观察到）
- 倾向简洁代码，不喜欢过度注释
- 喜欢在实现前先确认方案

## 错误与回退
- 14:22 bash 命令权限不足，已加 sudo 重试成功

## 操作日志范围
ops.jsonl 第 1-50 条（已压缩）
```

### 压缩后处理

压缩完成后：
- 将 summary.md 最新版本置入 context 开头
- 将 ops.jsonl 中已压缩的条目标记 `compressed: true`（不删除）
- 向 Layer 3 异步写入本次会话新增的语义知识

---

## Layer 3：跨会话语义层

### 存储内容

```
~/.ultra-memory/semantic/
├── user_profile.json        # 用户偏好、工作方式、常用技术栈
├── project_registry.json    # 已知项目列表及核心信息
├── knowledge_base.jsonl     # 语义知识条目（可向量化检索）
└── session_index.json       # 历史会话索引，按主题分类
```

### user_profile.json 格式

```json
{
  "last_updated": "2026-04-02",
  "tech_stack": ["Python", "Vue3", "TypeScript"],
  "work_style": {
    "prefers_concise_code": true,
    "confirm_before_implement": true,
    "scoring_framework": "ZL/GN"
  },
  "projects": ["ai-data-qa", "FusionUI", "ultra-memory"],
  "language": "zh-CN",
  "observed_patterns": [
    "倾向在实现前讨论方案",
    "喜欢类比解释复杂概念"
  ]
}
```

### 会话开始时的上下文注入

```markdown
<!-- ULTRA-MEMORY CONTEXT INJECTION -->
**已知背景（来自记忆层）：**
- 用户技术栈: Python / Vue3 / TypeScript
- 当前活跃项目: ai-data-qa, FusionUI
- 上次会话(2026-04-01): 完成了数据清洗模块，遗留问题是边界值处理
- 用户偏好: 简洁代码风格，倾向先确认方案再实现
<!-- END INJECTION -->
```

---

## 检索接口

### 自然语言查询

当用户问"之前我们做了什么""上次那个函数叫什么名字"时，按以下优先级检索：

1. **当前会话 ops.jsonl**（精确匹配，最近50条）
2. **当前会话 summary.md**（摘要快速定位）
3. **Layer 3 semantic search**（跨会话模糊检索）

```bash
python3 ~/.openclaw/workspace/skills/ultra-memory/scripts/recall.py \
  --query "数据清洗函数" \
  --session <session_id> \
  --top-k 5
```

### 检索结果格式

```
[RECALL] 找到 3 条相关记录：

[ops #23 · 14:18] 创建了 clean_df() 函数，位于 src/cleaner.py，
                  实现了空值填充和文本截断逻辑

[summary · 里程碑] ✅ 数据清洗模块完成，通过 3 个单元测试

[跨会话 · 2026-03-28] 上上次会话中也有类似函数 preprocess_text()，
                       当时放在 utils/ 目录
```

---

## 防遗忘机制

### Context 压力检测

每隔 10 次操作检查一次 context 使用率：

```
context 使用率 < 40%  → 无操作
context 使用率 40-60% → 提示用户，询问是否压缩
context 使用率 > 60%  → 自动触发 Layer 2 压缩
context 使用率 > 80%  → 紧急压缩 + 警告，保留最近 20 条 ops
```

### 会话恢复

当检测到用户重启会话（新 context）时，自动：

1. 读取上次 `summary.md` + 最近 10 条 `ops.jsonl`
2. 生成恢复提示注入 context 开头
3. 告知用户："我记得上次我们在做 X，当时的状态是..."

```bash
python3 ~/.openclaw/workspace/skills/ultra-memory/scripts/restore.py \
  --project <project_name>
```

---

## 与现有方案的对比

| 能力 | claude-mem | lancedb-pro | **ultra-memory** |
|-----|-----------|-------------|-----------------|
| 操作级日志 | ❌ | ❌ | ✅ 每步追踪 |
| 摘要压缩 | ✅ | ⚠️ 基础 | ✅ 结构化 |
| 跨会话持久化 | ⚠️ 依赖文件 | ✅ 向量DB | ✅ KV + 索引 |
| 会话恢复 | ❌ | ⚠️ 手动 | ✅ 自动注入 |
| 检索接口 | ❌ | ✅ 9个工具 | ✅ 统一recall |
| Context 压力管理 | ❌ | ❌ | ✅ 自动压缩 |
| 用户画像积累 | ❌ | ❌ | ✅ profile更新 |
| 轻量部署（无向量DB）| ✅ | ❌ 需LanceDB | ✅ 可降级 |

---

## 部署模式

### 模式A：轻量模式（纯文件，无依赖）

适合个人使用，零配置：
- Layer 1: JSONL 文件
- Layer 2: Markdown 文件
- Layer 3: JSON 文件 + 简单关键词检索

```bash
# 安装（OpenClaw）
cp -r ultra-memory ~/.openclaw/workspace/skills/
```

### 模式B：增强模式（LanceDB 向量检索）

适合重度使用 / 商业场景：

```bash
pip install lancedb sentence-transformers --break-system-packages
# 配置后 Layer 3 自动升级为向量检索
python3 scripts/setup_vector.py
```

### 模式C：MCP 服务模式

将 ultra-memory 封装为 MCP Server，供 Claude Code / OpenClaw 通过标准协议调用：

```bash
node scripts/mcp-server.js --port 3100
```

提供以下 MCP 工具：
- `memory_log` — 记录操作
- `memory_recall` — 检索记忆
- `memory_summarize` — 触发压缩
- `memory_restore` — 会话恢复
- `memory_profile` — 读写用户画像

---

## 使用示例

### 场景1：长编码任务不丢失上下文

```
用户: 帮我开发一个 Python 数据清洗工具
Claude: [ultra-memory 初始化] 会话 sess_20260402_abc 已创建，开始记录...
        我注意到你之前做过 ai-data-qa 项目，可以复用那里的评分逻辑...
        [每次操作后自动写入 ops.jsonl]
...（50条操作后）...
Claude: [自动摘要] 已完成里程碑: 数据加载、清洗函数、单元测试。
        当前进行中: 导出模块。context 已优化，继续...
```

### 场景2：跨天继续任务

```
用户（第二天）: 继续昨天的工作
Claude: [自动恢复] 我记得昨天（2026-04-01）我们在开发数据清洗工具：
        ✅ 已完成: 加载模块、clean_df()、基础测试
        🔄 进行中: 导出模块，写到一半
        下一步建议: 继续 export.py 的 to_csv() 方法
        要从这里继续吗？
```

### 场景3：精确回忆操作细节

```
用户: 我们之前那个处理空值的逻辑是怎么写的？
Claude: [检索 ops #23] 在 src/cleaner.py 的 clean_df() 中，
        空值处理是：字符串列填充 ""，数值列填充 0，
        代码在 line 45-52。要我展示吗？
```

---

## 进阶配置

详见 `references/advanced-config.md`（原 `advanced-config.md`），包含：
- 自定义记录过滤规则（排除敏感内容）
- 团队共享记忆配置（多人协作）
- 记忆衰减策略（老旧记忆降权）
- 与 n8n / LangGraph 集成方案
- 商业部署安全注意事项

---

## 注意事项

1. **隐私**：ops.jsonl 可能包含代码和命令，注意不要记录密码/API Key。`log_op.py` 内置了敏感词过滤。
2. **存储**：轻量模式下每个会话约 50-200KB，建议定期清理 30 天前的会话。
3. **性能**：写入操作为异步追加，不阻塞主流程。
4. **降级**：如果脚本不可用，Claude 应退化为在 CLAUDE.md 中手动维护摘要。
