# ultra-memory

> **超长会话记忆系统** — 给 AI Agent 提供不遗忘、可检索、跨会话持久化的记忆能力。
> 零外部依赖，支持所有 LLM 平台：Claude Code、OpenClaw、GPT-4、Gemini、Qwen 等。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/)
[![Node 18+](https://img.shields.io/badge/Node-18+-yellow.svg)](https://nodejs.org/)

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **5 层记忆架构** | ops 日志 → 摘要 → 语义 → 实体索引 → 向量语义 |
| **零外部依赖** | 纯 Python stdlib + 可选增强 |
| **结构化实体** | 自动提取函数/文件/依赖/决策/错误/类，精确召回 |
| **分层压缩** | O(log n) 上下文增长，永不爆 context |
| **跨语言检索** | 中英文同义词双向映射（"数据清洗" ↔ "clean_df"） |
| **全平台支持** | MCP Server / REST API / Claude Code Skill |
| **自动时间权重** | 越新的记忆权重越高，24h 半衰期 |

---

## 安装

### OpenClaw（推荐）

```bash
npx clawhub@latest install ultra-memory
```

或在 OpenClaw Settings → MCP Servers 添加：

```json
{
  "mcpServers": {
    "ultra-memory": {
      "command": "node",
      "args": ["$(npm root -g)/ultra-memory/scripts/mcp-server.js"]
    }
  }
}
```

### Claude Code

将 `SKILL.md` 内容复制到项目根目录，或配置 skill 路径。

### 任意 LLM 平台（REST API）

```bash
# 启动 REST 服务器
py -3 platform/server.py --port 3200

# 验证
curl http://127.0.0.1:3200/health
```

加载 `platform/tools_openai.json` 工具定义，工具调用转发到 `POST http://127.0.0.1:3200/tools/{name}`。

### npm 安装

```bash
npm install -g ultra-memory
ultra-memory  # 启动 MCP Server
```

---

## 架构：5 层记忆模型

```
┌─────────────────────────────────────────────────────────┐
│  Layer 5: 向量语义层 (TF-IDF / sentence-transformers)   │
│  模糊召回："找情感相似的段落"                             │
├─────────────────────────────────────────────────────────┤
│  Layer 4: 结构化实体索引 (entities.jsonl)                │
│  精确召回："用过的函数"、"做过的决策"、"报过的错"           │
├─────────────────────────────────────────────────────────┤
│  Layer 3: 跨会话语义层 (semantic/)                       │
│  知识库 · 用户偏好 · 项目索引                             │
├─────────────────────────────────────────────────────────┤
│  Layer 2: 会话摘要层 (summary.md)                        │
│  里程碑 · 关键决策 · 进行中任务                           │
├─────────────────────────────────────────────────────────┤
│  Layer 1: 操作日志层 (ops.jsonl)  ← 核心差异化           │
│  每步操作append-only · 时间权重 · 上下文窗口               │
└─────────────────────────────────────────────────────────┘
```

---

## 工具接口

| 工具 | 功能 |
|------|------|
| `memory_init` | 初始化会话，创建三层记忆结构 |
| `memory_log` | 记录操作（自动提取实体） |
| `memory_recall` | 5 层统一检索 |
| `memory_summarize` | 触发摘要压缩（含元压缩） |
| `memory_restore` | 恢复上次会话上下文 |
| `memory_profile` | 读写用户画像 |
| `memory_status` | 查询会话状态与 context 压力 |
| `memory_entities` | 查询结构化实体索引 |
| `memory_extract_entities` | 全量重提取实体 |

---

## 使用示例

### 场景 1：长编码任务不丢失上下文

```
用户: 帮我开发一个 Python 数据清洗工具

Claude: [ultra-memory] 会话已创建，开始记录每次操作...
       你之前做过 ai-data-qa 项目，我们可以复用那里的评分逻辑。
...（50条操作后）...
Claude: [自动摘要压缩] 已完成：数据加载、清洗函数、单元测试。
        当前进行中：导出模块。context 已优化，继续...
```

### 场景 2：跨天继续任务

```
用户（第二天）: 继续昨天的工作

Claude: [记忆恢复] 你昨天在开发数据清洗工具：
        ✅ 已完成：加载模块、clean_df()、基础测试
        🔄 进行中：导出模块，写到一半
        💡 下一步：继续 export.py 的 to_csv() 方法
```

### 场景 3：精确回忆操作细节

```
用户: 之前那个处理空值的逻辑是怎么写的？

Claude: [检索 ops #23] 在 src/cleaner.py 的 clean_df() 中：
        空值处理：字符串列填充 ""，数值列填充 0。
        代码在第 45-52 行。要展示吗？
```

---

## 存储结构

```
~/.ultra-memory/                   # 默认存储目录（可配置）
├── sessions/
│   └── <session_id>/
│       ├── ops.jsonl              # Layer 1: 操作日志（append-only）
│       ├── summary.md             # Layer 2: 会话摘要
│       ├── meta.json             # 元数据
│       ├── tfidf_cache.json      # Layer 5: TF-IDF 索引缓存
│       └── embed_cache.json      # Layer 5: sentence-transformers 缓存
├── semantic/
│   ├── entities.jsonl            # Layer 4: 结构化实体
│   ├── knowledge_base.jsonl      # Layer 3: 知识库
│   ├── user_profile.json         # 用户画像
│   └── session_index.json        # 会话索引
└── archive/                       # 归档会话（可配置）
```

---

## 与主流方案对比

| 能力 | Claude Code | mem0 | MemGPT | ultra-memory |
|------|:-----------:|:----:|:------:|:-----------:|
| 零外部依赖 | ✅ | ❌ | ❌ | **✅** |
| 结构化实体 | ❌ | 部分 | ❌ | **✅** |
| 分层压缩 O(log n) | 实验性 | ❌ | 固定层 | **✅** |
| 向量语义搜索 | ❌ | ✅ | ❌ | **✅**（可选） |
| 跨语言检索 | ❌ | ⚠️ | ❌ | **✅** |
| 全平台支持 | ❌ | ⚠️ | ⚠️ | **✅** |
| Context 注入可控 | ❌ | ❌ | ❌ | **✅** top-K |

---

## 开发者

**NanJingYa** — https://github.com/nanjingya

GitHub: https://github.com/nanjingya/ultra-memory

Issues: https://github.com/nanjingya/ultra-memory/issues

---

## 许可

MIT License
