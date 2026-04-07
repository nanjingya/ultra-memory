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
| **零外部依赖** | 纯 Python stdlib，可选 sentence-transformers 增强 |
| **RRF 多路融合** | BM25 + TF-IDF + 向量三通道倒数排名融合，消除量纲不一致 |
| **本地 Cross-Encoder** | `cross-encoder/ms-marco-MiniLM-L-6-v2` 精排，完全离线，零 API |
| **Weibull 衰减** | `exp(-(age/λ)^0.75)` 长期记忆保留比简单指数高 2.7 倍（7天后） |
| **三层记忆分级** | core / working / peripheral 自动分类，gc 可清理外围记忆 |
| **Snippet 截取** | recall 输出相关片段而非全量，Token 消耗减少 ~70% |
| **反馈环防护** | 自动过滤记忆注入标记，防止自引用噪音积累 |
| **结构化实体** | 自动提取函数/文件/依赖/决策/错误/类，精确召回 |
| **分层压缩** | O(log n) 上下文增长，永不爆 context |
| **跨语言检索** | 中英文同义词双向映射（"数据清洗" ↔ "clean_df"） |
| **全平台支持** | MCP Server / REST API / Claude Code Skill / OpenClaw |
| **管理 CLI** | list / search / stats / export / gc / tier 六个子命令 |
| **Bearer Token 认证** | REST API 可选 token 保护，支持环境变量注入 |

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

## 架构：5 层记忆模型 + RRF 检索引擎

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 5: 向量语义层 (TF-IDF / sentence-transformers)           │
│  模糊召回 · all-MiniLM-L6-v2 · 增量缓存                         │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: 结构化实体索引 (entities.jsonl)                        │
│  精确召回：函数 / 文件 / 依赖 / 决策 / 错误 / 类                  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: 跨会话语义层 (semantic/)                               │
│  知识库 · 用户画像 · 冲突检测 · 时间旅行查询                       │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 会话摘要层 (summary.md)                                │
│  里程碑 · 关键决策 · 三层记忆统计 · 元压缩 O(log n)              │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: 操作日志层 (ops.jsonl)  ← append-only 核心            │
│  Weibull衰减 · tier分层 · 上下文窗口 · 反馈环防护                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 召回时
┌─────────────────────────────────────────────────────────────────┐
│  检索引擎（v4.1 新增）                                           │
│  BM25 ──┐                                                       │
│  TF-IDF ─┼→ RRF 融合 → [可选] Cross-Encoder 精排 → Snippet 截取 │
│  向量  ──┘                                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 工具接口

### MCP / REST API 工具

| 工具 | 功能 |
|------|------|
| `memory_init` | 初始化会话，创建三层记忆结构 |
| `memory_log` | 记录操作（自动提取实体 + tier 分级） |
| `memory_recall` | 5 层统一检索（RRF 融合 + Cross-Encoder 精排） |
| `memory_summarize` | 触发摘要压缩（含三层统计 + 元压缩） |
| `memory_restore` | 恢复上次会话上下文 |
| `memory_profile` | 读写用户画像 |
| `memory_status` | 查询会话状态与 context 压力 |
| `memory_entities` | 查询结构化实体索引 |
| `memory_extract_entities` | 全量重提取实体 |
| `memory_knowledge_add` | 追加知识库条目 |

### manage.py 管理 CLI

```bash
python3 scripts/manage.py list              # 列出所有会话
python3 scripts/manage.py search "关键词"   # 跨会话全文搜索
python3 scripts/manage.py stats             # 全局统计（tier 分布、知识库规模）
python3 scripts/manage.py export --format json --output backup.json
python3 scripts/manage.py gc --days 90      # 垃圾回收旧会话（默认 dry-run）
python3 scripts/manage.py tier              # 补写历史数据的 tier 分级
```

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

| 能力 | Claude 原生 | mem0 | memory-lancedb-pro | ultra-memory |
|------|:-----------:|:----:|:-----------------:|:-----------:|
| 零外部依赖（核心） | ✅ | ❌ | ❌ | **✅** |
| RRF 多路融合 | ❌ | ❌ | ✅ | **✅** |
| Cross-Encoder 精排 | ❌ | ❌ | ✅（外部API） | **✅**（本地离线） |
| 冲突检测 | ❌ | ❌ | ❌ | **✅** |
| 三层记忆分级 | ❌ | ❌ | ✅ | **✅** |
| 反馈环防护 | ❌ | ❌ | ✅ | **✅** |
| 结构化实体提取 | ❌ | 部分 | LLM分类 | **✅**（regex，零API） |
| 分层压缩 O(log n) | ❌ | ❌ | ❌ | **✅** |
| 数据完全本地 | ❌（云端） | ⚠️ | ✅ | **✅** |
| 全平台支持 | 仅Claude | ⚠️ | ⚠️ | **✅** |
| 管理 CLI | ❌ | ❌ | ✅ | **✅** |

---

## 开发者

**NanJingYa** — https://github.com/nanjingya

GitHub: https://github.com/nanjingya/ultra-memory

Issues: https://github.com/nanjingya/ultra-memory/issues

---

## 许可

MIT License
