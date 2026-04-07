#!/usr/bin/env python3
"""
ultra-memory: 知识库写入脚本
将重要信息追加写入 semantic/knowledge_base.jsonl，供未来相似任务检索。
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ULTRA_MEMORY_HOME = Path(os.environ.get("ULTRA_MEMORY_HOME", Path.home() / ".ultra-memory"))


def log_knowledge(
    title: str,
    content: str,
    project: str = "default",
    tags: list = None,
):
    """追加一条知识库条目"""
    semantic_dir = ULTRA_MEMORY_HOME / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    kb_file = semantic_dir / "knowledge_base.jsonl"

    entry = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "project": project,
        "title": title[:100],
        "content": content[:200],
        "tags": tags or [],
    }

    with open(kb_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"[ultra-memory] 知识库已写入: {title}")
    return entry


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="追加知识库条目")
    parser.add_argument("--title", required=True, help="知识标题（100字内）")
    parser.add_argument("--content", required=True, help="知识内容（200字内）")
    parser.add_argument("--project", default="default", help="关联项目名")
    parser.add_argument("--tags", default="", help="逗号分隔的标签")
    args = parser.parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    log_knowledge(args.title, args.content, args.project, tags)
