#!/usr/bin/env node
/**
 * ultra-memory MCP Server
 * 将 ultra-memory 封装为标准 MCP 工具，供 Claude Code / OpenClaw 调用
 *
 * 提供 9 个工具：
 *   memory_init     — 初始化会话
 *   memory_status   — 查询当前会话状态
 *   memory_log      — 记录操作（自动提取实体）
 *   memory_recall   — 四层统一检索（ops/summary/semantic/entity）
 *   memory_summarize — 触发摘要压缩（含元压缩）
 *   memory_restore  — 恢复上次会话
 *   memory_profile  — 读写用户画像
 *   memory_entities — 查询结构化实体索引（新增）
 *   memory_extract_entities — 全量重提取实体（新增）
 */

const { execSync, execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");
const readline = require("readline");

const SCRIPTS_DIR = path.join(__dirname);
const ULTRA_MEMORY_HOME =
  process.env.ULTRA_MEMORY_HOME || path.join(os.homedir(), ".ultra-memory");

function runScript(script, args = []) {
  const scriptPath = path.join(SCRIPTS_DIR, script);
  try {
    const result = execFileSync(
      "python3",
      [scriptPath, ...args],
      { encoding: "utf-8", timeout: 15000 }
    );
    return { success: true, output: result.trim() };
  } catch (e) {
    return { success: false, output: e.stdout || e.message };
  }
}

// MCP 工具定义（共 7 个）
const TOOLS = [
  {
    name: "memory_init",
    description: "初始化 ultra-memory 会话。Claude Code 首次启动或新会话开始时调用，创建三层记忆结构并注入历史上下文",
    inputSchema: {
      type: "object",
      properties: {
        project: { type: "string", description: "项目名称", default: "default" },
        resume: { type: "boolean", description: "尝试恢复最近会话", default: false }
      },
      required: []
    }
  },
  {
    name: "memory_status",
    description: "查询当前会话状态：操作数、最后里程碑、context 压力级别（low/medium/high/critical）",
    inputSchema: {
      type: "object",
      properties: {
        session_id: { type: "string", description: "会话 ID" }
      },
      required: ["session_id"]
    }
  },
  {
    name: "memory_log",
    description: "记录一条操作到当前会话的操作日志 (Layer 1)",
    inputSchema: {
      type: "object",
      properties: {
        session_id: { type: "string", description: "当前会话 ID" },
        op_type: {
          type: "string",
          enum: ["tool_call", "file_write", "file_read", "bash_exec",
                 "reasoning", "user_instruction", "decision", "error", "milestone"],
          description: "操作类型"
        },
        summary: { type: "string", description: "操作摘要（50字内）" },
        detail: { type: "object", description: "详细信息（可选）" },
        tags: { type: "array", items: { type: "string" }, description: "标签列表" }
      },
      required: ["session_id", "op_type", "summary"]
    }
  },
  {
    name: "memory_recall",
    description: "从三层记忆中检索与查询相关的操作历史",
    inputSchema: {
      type: "object",
      properties: {
        session_id: { type: "string", description: "当前会话 ID" },
        query: { type: "string", description: "检索关键词（中英文均可）" },
        top_k: { type: "number", description: "返回结果数量，默认 5", default: 5 }
      },
      required: ["session_id", "query"]
    }
  },
  {
    name: "memory_summarize",
    description: "触发当前会话的摘要压缩（将 ops 日志压缩为 summary.md）",
    inputSchema: {
      type: "object",
      properties: {
        session_id: { type: "string", description: "当前会话 ID" },
        force: { type: "boolean", description: "强制压缩，即使条数不足", default: false }
      },
      required: ["session_id"]
    }
  },
  {
    name: "memory_restore",
    description: "恢复指定项目的上次会话上下文，用于跨天继续任务",
    inputSchema: {
      type: "object",
      properties: {
        project: { type: "string", description: "项目名称", default: "default" },
        verbose: { type: "boolean", description: "显示详细操作记录", default: false }
      },
      required: []
    }
  },
  {
    name: "memory_profile",
    description: "读写用户画像（技术栈、偏好、项目列表）",
    inputSchema: {
      type: "object",
      properties: {
        action: { type: "string", enum: ["read", "update"], description: "操作类型" },
        updates: {
          type: "object",
          description: "要更新的字段（action=update 时必填）"
        }
      },
      required: ["action"]
    }
  },
  {
    name: "memory_entities",
    description: "查询结构化实体索引（函数/文件/依赖/决策/错误），精确回答「用过哪些函数」「装了哪些包」「做了哪些决策」等结构化问题",
    inputSchema: {
      type: "object",
      properties: {
        entity_type: {
          type: "string",
          enum: ["function", "file", "dependency", "decision", "error", "class", "all"],
          description: "实体类型过滤（all=不过滤）",
          default: "all"
        },
        query: { type: "string", description: "搜索关键词（可选，空则返回全部该类型）", default: "" },
        top_k: { type: "number", description: "返回数量", default: 10 }
      },
      required: []
    }
  },
  {
    name: "memory_extract_entities",
    description: "对指定会话的 ops.jsonl 全量重新提取结构化实体（修复或初次建立实体索引时使用）",
    inputSchema: {
      type: "object",
      properties: {
        session_id: { type: "string", description: "会话 ID" }
      },
      required: ["session_id"]
    }
  }
];

// 工具执行逻辑
function executeTool(name, input) {
  switch (name) {
    case "memory_init": {
      const args = ["--project", input.project || "default"];
      if (input.resume) args.push("--resume");
      return runScript("init.py", args);
    }
    case "memory_status": {
      // 读取 meta.json 并调用 check_context_pressure
      const sessionId = input.session_id;
      const metaPath = path.join(ULTRA_MEMORY_HOME, "sessions", sessionId, "meta.json");
      let meta = {};
      try {
        meta = JSON.parse(fs.readFileSync(metaPath, "utf-8"));
      } catch {
        return { success: false, output: `会话不存在: ${sessionId}` };
      }
      // 调用 init.py --check-pressure 获取压力级别
      const pressureResult = runScript("init.py", ["--check-pressure", sessionId]);
      const statusLines = [
        `会话 ID: ${sessionId}`,
        `项目: ${meta.project || "default"}`,
        `操作数: ${meta.op_count || 0}`,
        `最后里程碑: ${meta.last_milestone || "（无）"}`,
        `上次压缩: ${meta.last_summary_at || "（未压缩）"}`,
        pressureResult.output,
      ];
      return { success: true, output: statusLines.join("\n") };
    }
    case "memory_log": {
      const args = [
        "--session", input.session_id,
        "--type", input.op_type,
        "--summary", input.summary,
        "--detail", JSON.stringify(input.detail || {}),
        "--tags", (input.tags || []).join(",")
      ];
      return runScript("log_op.py", args);
    }
    case "memory_recall": {
      const args = [
        "--session", input.session_id,
        "--query", input.query,
        "--top-k", String(input.top_k || 5)
      ];
      return runScript("recall.py", args);
    }
    case "memory_summarize": {
      const args = ["--session", input.session_id];
      if (input.force) args.push("--force");
      return runScript("summarize.py", args);
    }
    case "memory_restore": {
      const args = ["--project", input.project || "default"];
      if (input.verbose) args.push("--verbose");
      return runScript("restore.py", args);
    }
    case "memory_profile": {
      const profilePath = path.join(ULTRA_MEMORY_HOME, "semantic", "user_profile.json");
      if (input.action === "read") {
        try {
          const content = fs.readFileSync(profilePath, "utf-8");
          return { success: true, output: content };
        } catch {
          return { success: true, output: "{}" };
        }
      } else if (input.action === "update") {
        let profile = {};
        try { profile = JSON.parse(fs.readFileSync(profilePath, "utf-8")); } catch {}
        Object.assign(profile, input.updates || {});
        profile.last_updated = new Date().toISOString().slice(0, 10);
        fs.mkdirSync(path.dirname(profilePath), { recursive: true });
        fs.writeFileSync(profilePath, JSON.stringify(profile, null, 2));
        return { success: true, output: "用户画像已更新" };
      }
      return { success: false, output: "未知操作" };
    }
    case "memory_entities": {
      // 直接读取 entities.jsonl，按类型过滤后返回
      const entitiesPath = path.join(ULTRA_MEMORY_HOME, "semantic", "entities.jsonl");
      const targetType = (input.entity_type || "all").toLowerCase();
      const query = (input.query || "").toLowerCase();
      const topK = input.top_k || 10;
      try {
        const lines = fs.readFileSync(entitiesPath, "utf-8").split("\n").filter(Boolean);
        const entities = lines.map(l => { try { return JSON.parse(l); } catch { return null; } })
                              .filter(Boolean);
        let filtered = entities;
        if (targetType !== "all") {
          filtered = filtered.filter(e => e.entity_type === targetType);
        }
        if (query) {
          filtered = filtered.filter(e =>
            (e.name || "").toLowerCase().includes(query) ||
            (e.context || "").toLowerCase().includes(query)
          );
        }
        // 去重（同类型同名保留最新）
        const seen = new Set();
        const deduped = [];
        for (const e of filtered.reverse()) {
          const key = `${e.entity_type}:${e.name}`;
          if (!seen.has(key)) { seen.add(key); deduped.push(e); }
        }
        const result = deduped.slice(0, topK);
        const lines_out = result.map(e => {
          let line = `[${e.entity_type}] ${e.name}`;
          if (e.rationale) line += ` 依据: ${e.rationale}`;
          if (e.manager) line += ` [${e.manager}]`;
          if (e.context) line += `\n  来源: ${e.context}`;
          return line;
        });
        const output = lines_out.length > 0
          ? `找到 ${lines_out.length} 个实体：\n\n${lines_out.join("\n")}`
          : "未找到匹配实体";
        return { success: true, output };
      } catch (e) {
        return { success: true, output: "实体索引尚未建立，请先运行 memory_log 记录操作" };
      }
    }
    case "memory_extract_entities": {
      return runScript("extract_entities.py", ["--session", input.session_id, "--all"]);
    }
    default:
      return { success: false, output: `未知工具: ${name}` };
  }
}

// MCP stdio 协议处理
const rl = readline.createInterface({ input: process.stdin });

rl.on("line", (line) => {
  let request;
  try {
    request = JSON.parse(line);
  } catch {
    return;
  }

  const { id, method, params } = request;

  let response;
  if (method === "initialize") {
    response = {
      id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "ultra-memory", version: "3.0.0" }
      }
    };
  } else if (method === "tools/list") {
    response = { id, result: { tools: TOOLS } };
  } else if (method === "tools/call") {
    const { name, arguments: args } = params;
    const result = executeTool(name, args || {});
    response = {
      id,
      result: {
        content: [{ type: "text", text: result.output }],
        isError: !result.success
      }
    };
  } else {
    response = { id, error: { code: -32601, message: "Method not found" } };
  }

  process.stdout.write(JSON.stringify(response) + "\n");
});

process.stderr.write("[ultra-memory] MCP Server 已启动 (stdio 模式)\n");
