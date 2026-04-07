#!/usr/bin/env python3
"""
ultra-memory: 记忆检索脚本
支持从三层记忆中检索相关内容
优化：同义词/别名映射 + 时间衰减权重 + 上下文窗口（前后各1条）
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

ULTRA_MEMORY_HOME = Path(os.environ.get("ULTRA_MEMORY_HOME", Path.home() / ".ultra-memory"))

# 同义词/别名映射表：中文描述 ↔ 英文函数名/技术词
# 检索时会将查询词扩展为同义词集合，提升跨语言检索精度
SYNONYM_MAP = {
    # 数据处理
    "数据清洗": ["clean", "clean_df", "preprocess", "cleaner", "清洗", "data_clean"],
    "clean_df": ["数据清洗", "清洗", "preprocess", "数据处理", "clean"],
    "preprocess": ["预处理", "数据清洗", "clean_df", "数据处理"],
    "数据处理": ["clean_df", "preprocess", "transform", "处理数据"],
    # 测试
    "测试": ["test", "unittest", "pytest", "spec", "assert"],
    "test": ["测试", "单元测试", "pytest", "unittest"],
    "单元测试": ["test", "unittest", "pytest"],
    # 安装/依赖
    "安装": ["install", "pip install", "npm install", "setup", "依赖"],
    "install": ["安装", "依赖", "setup"],
    "依赖": ["install", "dependency", "requirements", "安装"],
    # 部署
    "部署": ["deploy", "docker", "release", "发布"],
    "deploy": ["部署", "发布", "release"],
    # 错误
    "报错": ["error", "exception", "traceback", "failed", "错误"],
    "error": ["报错", "错误", "exception", "traceback"],
    "错误": ["error", "exception", "报错", "traceback"],
    # 配置
    "配置": ["config", "settings", "setup", ".env"],
    "config": ["配置", "设置", "settings"],
    # 接口
    "接口": ["api", "endpoint", "route", "url"],
    "api": ["接口", "endpoint", "请求", "route"],
    # 函数/方法
    "函数": ["def", "function", "method", "func"],
    "function": ["函数", "方法", "def"],
    # 完成
    "完成": ["done", "finished", "milestone", "✅"],
    "done": ["完成", "finished", "milestone"],
}

# 时间衰减半衰期（秒）：越新的操作权重越高
TIME_HALF_LIFE_SECONDS = 3600 * 24  # 24小时为半衰期


def expand_query(query: str) -> set[str]:
    """将查询词扩展为同义词集合"""
    tokens = tokenize(query)
    expanded = set(tokens)
    for token in list(tokens):
        for key, synonyms in SYNONYM_MAP.items():
            if token == key.lower() or token in [s.lower() for s in synonyms]:
                expanded.add(key.lower())
                expanded.update(s.lower() for s in synonyms)
    return expanded


def tokenize(text: str) -> set[str]:
    """简单中英文分词（无需外部依赖）"""
    # 英文：按空格和标点切分
    words = re.findall(r'[a-zA-Z0-9_\-\.]+', text.lower())
    # 中文：unigram + bigram（bigram 提升短语匹配）
    chinese = re.findall(r'[\u4e00-\u9fff]', text)
    bigrams = [chinese[i] + chinese[i+1] for i in range(len(chinese)-1)]
    return set(words + bigrams + chinese)


def time_weight(ts_str: str) -> float:
    """
    计算时间衰减权重（指数衰减）。
    越新的操作权重越接近 1.0，24小时前的操作权重约 0.5。
    """
    try:
        ts = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_seconds = (now - ts).total_seconds()
        # 指数衰减：weight = 0.5^(age / half_life)
        import math
        weight = math.pow(0.5, age_seconds / TIME_HALF_LIFE_SECONDS)
        # 最低保底权重 0.1，避免旧记忆完全消失
        return max(0.1, weight)
    except Exception:
        return 0.5


def score_relevance(query_tokens: set, text: str, ts_str: str = "") -> float:
    """
    关键词重叠相关性评分 × 时间权重。
    加入同义词扩展后的 token 参与匹配。
    """
    text_tokens = tokenize(text)
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens)
    base_score = overlap / max(len(query_tokens), 1)
    tw = time_weight(ts_str) if ts_str else 1.0
    return base_score * (0.7 + 0.3 * tw)  # 时间权重占 30%


def load_all_ops(session_dir: Path) -> list[dict]:
    """加载全部操作（含已压缩，用于提取上下文窗口）"""
    ops_file = session_dir / "ops.jsonl"
    if not ops_file.exists():
        return []
    ops = []
    with open(ops_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ops.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return ops


def get_context_window(all_ops: list[dict], target_seq: int, window: int = 1) -> dict:
    """
    返回目标 seq 前后各 window 条操作作为上下文。
    """
    seq_map = {op["seq"]: op for op in all_ops}
    before = []
    after = []
    for i in range(1, window + 1):
        if (target_seq - i) in seq_map:
            before.insert(0, seq_map[target_seq - i])
        if (target_seq + i) in seq_map:
            after.append(seq_map[target_seq + i])
    return {"before": before, "after": after}


def search_ops(session_dir: Path, query_tokens: set, top_k: int) -> list[dict]:
    """在操作日志中搜索，附带时间权重和上下文窗口"""
    all_ops = load_all_ops(session_dir)
    if not all_ops:
        return []

    results = []
    for op in all_ops:
        text = op.get("summary", "") + " " + json.dumps(op.get("detail", {}), ensure_ascii=False)
        score = score_relevance(query_tokens, text, op.get("ts", ""))
        if score > 0:
            ctx = get_context_window(all_ops, op["seq"], window=1)
            results.append({
                "score": score,
                "source": "ops",
                "data": op,
                "context": ctx,
            })

    results.sort(key=lambda x: (-x["score"], -x["data"]["seq"]))
    return results[:top_k]


def search_summary(session_dir: Path, query_tokens: set) -> list[dict]:
    """在摘要文件中搜索"""
    summary_file = session_dir / "summary.md"
    if not summary_file.exists():
        return []
    with open(summary_file, encoding="utf-8") as f:
        content = f.read()
    paragraphs = [p.strip() for p in content.split("\n") if p.strip() and not p.startswith("#")]
    results = []
    for para in paragraphs:
        score = score_relevance(query_tokens, para)
        if score > 0.1:
            results.append({"score": score, "source": "summary", "text": para})
    results.sort(key=lambda x: -x["score"])
    return results[:3]


def search_entities(query_tokens: set, top_k: int) -> list[dict]:
    """
    第4层：实体索引搜索（结构化精确检索）。
    适合回答：
      - "我们用过哪些函数？" → entity_type=function
      - "动过哪些文件？"     → entity_type=file
      - "装了哪些依赖？"     → entity_type=dependency
      - "做了哪些决策？"     → entity_type=decision
    相比 bigram 关键词，对结构化查询的精度提升显著。
    """
    entities_file = ULTRA_MEMORY_HOME / "semantic" / "entities.jsonl"
    if not entities_file.exists():
        return []

    # 实体类型别名：查询词到实体类型的映射
    TYPE_ALIASES = {
        "函数": "function", "function": "function", "方法": "function", "func": "function",
        "文件": "file", "file": "file", "路径": "file",
        "依赖": "dependency", "dependency": "dependency", "包": "dependency",
        "决策": "decision", "decision": "decision", "选择": "decision",
        "错误": "error", "error": "error", "报错": "error", "异常": "error",
        "类": "class", "class": "class",
    }

    # 检测查询是否包含实体类型词（精确类型过滤）
    target_type = None
    for token in query_tokens:
        if token in TYPE_ALIASES:
            target_type = TYPE_ALIASES[token]
            break

    results = []
    seen_names: set[str] = set()  # 去重：同名实体只保留最新一条

    all_entities = []
    with open(entities_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                all_entities.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # 按 ts 倒序（最新优先）
    all_entities.sort(key=lambda e: e.get("ts", ""), reverse=True)

    for ent in all_entities:
        # 类型过滤
        if target_type and ent.get("entity_type") != target_type:
            continue

        name = ent.get("name", "")
        context = ent.get("context", "")
        ent_text = name + " " + context

        score = score_relevance(query_tokens, ent_text, ent.get("ts", ""))

        # 实体名精确匹配给予额外加分
        name_tokens = tokenize(name)
        exact_match = bool(query_tokens & name_tokens)
        if exact_match:
            score = max(score, 0.5)  # 保底 0.5 分

        # 如果是类型查询（"所有函数" "所有文件"），返回全部该类型实体
        if target_type and not seen_names:
            score = max(score, 0.3)

        if score > 0.1:
            dedup_key = f"{ent.get('entity_type')}:{name}"
            if dedup_key not in seen_names:
                seen_names.add(dedup_key)
                results.append({
                    "score": score,
                    "source": "entity",
                    "data": ent,
                })

    results.sort(key=lambda x: -x["score"])
    return results[:top_k]


def search_semantic(query_tokens: set, top_k: int) -> list[dict]:
    """在 Layer 3 语义层搜索（轻量模式：关键词匹配 + 同义词扩展）"""
    semantic_dir = ULTRA_MEMORY_HOME / "semantic"
    kb_file = semantic_dir / "knowledge_base.jsonl"
    index_file = semantic_dir / "session_index.json"

    results = []

    if kb_file.exists():
        with open(kb_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # 过滤已失效条目
                if entry.get("superseded"):
                    continue
                text = entry.get("content", "") + " " + entry.get("title", "")
                ts = entry.get("ts", "")
                score = score_relevance(query_tokens, text, ts)
                if score > 0.1:
                    results.append({"score": score, "source": "knowledge_base", "data": entry})

    if index_file.exists():
        with open(index_file, encoding="utf-8") as f:
            index = json.load(f)
        for s in index.get("sessions", []):
            text = s.get("project", "") + " " + (s.get("last_milestone") or "")
            ts = s.get("started_at", "")
            score = score_relevance(query_tokens, text, ts)
            if score > 0.1:
                results.append({"score": score, "source": "history", "data": s})

    results.sort(key=lambda x: -x["score"])
    return results[:top_k]


def search_profile(query_tokens: set, home: Path) -> list[dict]:
    """从 user_profile.json 检索相关字段，跳过 superseded 字段"""
    profile_file = home / "semantic" / "user_profile.json"
    if not profile_file.exists():
        return []

    try:
        with open(profile_file, encoding="utf-8") as f:
            profile = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

    results = []
    for key, value in profile.items():
        # 跳过 superseded 标记的字段
        if key.endswith("_superseded"):
            continue
        text = f"{key} {value}"
        score = score_relevance(query_tokens, str(text))
        if score > 0.1:
            results.append({
                "score": score,
                "source": "profile",
                "data": {"field": key, "value": value},
            })

    results.sort(key=lambda x: -x["score"])
    return results[:3]


# ── TF-IDF 向量语义搜索层（第四层召回的增强）───────────────────────────

def is_sklearn_available() -> bool:
    try:
        import sklearn; return True
    except ImportError:
        return False


def is_sentencetransformers_available() -> bool:
    try:
        from sentence_transformers import SentenceTransformer; return True
    except ImportError:
        return False


_TFidfCache: dict[str, dict] = {}  # session_id → {vocab, idfs, doc_vectors, doc_texts}


def _get_tfidf_cache_path(session_dir: Path) -> Path:
    return session_dir / "tfidf_cache.json"


def _text_from_op(op: dict) -> str:
    """提取 op 中可索引的文本"""
    parts = [
        op.get("summary", ""),
        op.get("type", ""),
        " ".join(op.get("tags", [])),
    ]
    detail = op.get("detail", {})
    if isinstance(detail, dict):
        for v in detail.values():
            if isinstance(v, str):
                parts.append(v)
    return " ".join(parts)


def _build_tfidf_index(ops: list[dict]) -> dict:
    """
    用 sklearn TfidfVectorizer 构建内存索引。
    返回 {vocab: [...], idfs: [...], doc_vectors: [[...], ...], doc_texts: [...]}
    完全零外部 API 依赖。
    """
    import math
    from collections import Counter

    texts = [_text_from_op(op) for op in ops]
    # 简单 tokenize：英文保留 word，中文逐字
    def tokens(text: str) -> list[str]:
        import re
        en = re.findall(r'[a-zA-Z0-9_]+', text.lower())
        zh = list(text)
        return en + zh

    tokenized = [tokens(t) for t in texts]
    # 构建词表
    vocab_set: set[str] = set()
    for tk in tokenized:
        vocab_set.update(tk)
    vocab = sorted(vocab_set)
    word2idx = {w: i for i, w in enumerate(vocab)}
    n = len(vocab)

    # TF: 词频
    N = len(texts)
    df = Counter()
    for tk in tokenized:
        df.update(set(tk))

    idfs = []
    for w in vocab:
        df_w = df[w]
        idf = math.log((N + 1) / (df_w + 1)) + 1  # 平滑
        idfs.append(idf)

    # 文档向量 = TF × IDF
    doc_vectors = []
    for tk in tokenized:
        tf = Counter(tk)
        vec = [0.0] * n
        for w, f in tf.items():
            if w in word2idx:
                idx = word2idx[w]
                vec[idx] = f * idfs[idx]
        # L2 归一化
        norm = math.sqrt(sum(v ** 2 for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        doc_vectors.append(vec)

    return {
        "vocab": vocab,
        "idfs": idfs,
        "doc_vectors": doc_vectors,
        "doc_texts": texts,
        "n_docs": N,
    }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _search_tfidf(session_dir: Path, all_ops: list[dict],
                  query: str, top_k: int) -> list[dict]:
    """纯 sklearn TF-IDF 语义搜索（零依赖，fallback 方案）"""
    import re

    cache_path = _get_tfidf_cache_path(session_dir)

    # 加载或构建缓存
    if cache_path.exists():
        try:
            import json as _json
            with open(cache_path, encoding="utf-8") as f:
                cache = _json.load(f)
            doc_vectors = cache["doc_vectors"]
            doc_texts   = cache["doc_texts"]
            vocab       = cache["vocab"]
            idfs        = cache["idfs"]
            cached_seq  = cache.get("last_seq", -1)
        except Exception:
            cache = None
            doc_vectors = None
    else:
        cache = None

    # 如果缓存过期（seq 变了）或不存在，重新构建
    current_seq = max((op.get("seq", 0) for op in all_ops), default=0)
    if doc_vectors is None or cache is None or cache.get("last_seq", -1) != current_seq:
        cache = _build_tfidf_index(all_ops)
        doc_vectors = cache["doc_vectors"]
        doc_texts   = cache["doc_texts"]
        vocab       = cache["vocab"]
        idfs        = cache["idfs"]
        cache["last_seq"] = current_seq
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except Exception:
            pass  # 写入失败不影响搜索

    # 把 query 也转成 TF-IDF 向量
    def tokens(text: str) -> list[str]:
        en = re.findall(r'[a-zA-Z0-9_]+', text.lower())
        zh = list(text)
        return en + zh

    q_tokens = tokens(query)
    tf_q = Counter(q_tokens)
    word2idx = {w: i for i, w in enumerate(vocab)}
    vec_q = [0.0] * len(vocab)
    for w, f in tf_q.items():
        if w in word2idx:
            idx = word2idx[w]
            vec_q[idx] = f * idfs[idx]

    # L2 归一化
    import math
    norm = math.sqrt(sum(v * v for v in vec_q))
    if norm > 0:
        vec_q = [v / norm for v in vec_q]

    # 余弦相似度
    scored = []
    for i, dv in enumerate(doc_vectors):
        score = _cosine_similarity(vec_q, dv)
        if score > 0.05:  # 阈值过滤噪音
            scored.append((score, i))
    scored.sort(key=lambda x: -x[0])

    results = []
    # all_ops 和 doc_vectors/doc_texts 按同一顺序排列，直接用索引对应
    for score, i in scored[:top_k]:
        results.append({"score": score, "source": "tfidf", "data": all_ops[i]})

    return results


def _search_sentencetransformers(
    session_dir: Path, all_ops: list[dict],
    query: str, top_k: int
) -> list[dict]:
    """
    sentence-transformers 向量语义搜索（更高质量，需 pip install sentence-transformers）。
    使用 all-MiniLM-L6-v2（22MB，本地运行，无需 API）。
    """
    import json as _json

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return []

    cache_path = session_dir / "embed_cache.json"

    # 加载或构建 embedding 缓存
    if cache_path.exists():
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = _json.load(f)
            cached_seq = cache.get("last_seq", -1)
            current_seq = max((op.get("seq", 0) for op in all_ops), default=0)
            if cached_seq != current_seq:
                cache = None
        except Exception:
            cache = None
    else:
        cache = None

    texts = [_text_from_op(op) for op in all_ops]

    if cache is None:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(texts, show_progress_bar=False).tolist()
        current_seq = max((op.get("seq", 0) for op in all_ops), default=0)
        cache = {"embeddings": embeddings, "last_seq": current_seq}
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                _json.dump(cache, f)
        except Exception:
            pass

    # 将查询向量化
    model = SentenceTransformer("all-MiniLM-L6-v2")
    query_emb = model.encode([query], show_progress_bar=False)[0].tolist()

    embeddings = cache["embeddings"]
    import math
    scored = []
    for i, emb in enumerate(embeddings):
        dot = sum(a * b for a, b in zip(query_emb, emb))
        na = math.sqrt(sum(a * a for a in query_emb))
        nb = math.sqrt(sum(a * a for a in emb))
        score = dot / (na * nb) if na > 0 and nb > 0 else 0
        if score > 0.3:
            scored.append((score, i))
    scored.sort(key=lambda x: -x[0])

    results = []
    for score, i in scored[:top_k]:
        results.append({"score": score, "source": "embedding", "data": all_ops[i]})
    return results


def search_tfidf(session_dir: Path, all_ops: list[dict],
                 query: str, top_k: int) -> list[dict]:
    """
    语义搜索入口：优先 sentence-transformers，退回 sklearn TF-IDF。
    如果都不可用，返回空列表（不阻塞主流程）。
    """
    if is_sentencetransformers_available():
        return _search_sentencetransformers(session_dir, all_ops, query, top_k)
    elif is_sklearn_available():
        return _search_tfidf(session_dir, all_ops, query, top_k)
    return []


# ── 结果格式化 ──────────────────────────────────────────────────────────

def format_result(result: dict, show_context: bool = True) -> str:
    source = result["source"]
    lines = []

    if source == "ops":
        op = result["data"]
        ts = op["ts"][:16].replace("T", " ")
        lines.append(f"[ops #{op['seq']} · {ts}] {op['summary']}")
        # 显示上下文窗口
        if show_context and result.get("context"):
            ctx = result["context"]
            for before_op in ctx.get("before", []):
                lines.append(f"  ↑ [#{before_op['seq']}] {before_op['summary'][:60]}")
            for after_op in ctx.get("after", []):
                lines.append(f"  ↓ [#{after_op['seq']}] {after_op['summary'][:60]}")
    elif source == "summary":
        lines.append(f"[摘要] {result['text']}")
    elif source == "knowledge_base":
        d = result["data"]
        lines.append(f"[知识库 · {d.get('title', '?')}] {d.get('content', '')[:100]}")
    elif source == "history":
        d = result["data"]
        ts = d.get("started_at", "")[:10]
        lines.append(f"[历史会话 · {ts} · {d.get('project', '')}] {d.get('last_milestone', '无里程碑记录')}")
    elif source == "entity":
        d = result["data"]
        et = d.get("entity_type", "?")
        name = d.get("name", "?")
        ctx = d.get("context", "")
        ts = d.get("ts", "")[:16].replace("T", " ")
        extra = ""
        if et == "dependency":
            extra = f" [via {d.get('manager', '?')}]"
        elif et == "decision":
            rationale = d.get("rationale", "")
            extra = f" 依据: {rationale}" if rationale else ""
        elif et == "error":
            extra = f" ← {d.get('message', '')}"
        lines.append(f"[实体/{et} · {ts}] {name}{extra}")
        if ctx:
            lines.append(f"  来源: {ctx}")

    elif source in ("tfidf", "embedding"):
        d = result["data"]
        ts = d.get("ts", "")[:16].replace("T", " ")
        label = "TF-IDF" if source == "tfidf" else "向量"
        lines.append(f"[语义/{label} #{d.get('seq', '?')} · {ts}] {d.get('summary', '?')[:80]}")
        detail = d.get("detail", {})
        if isinstance(detail, dict):
            for k, v in list(detail.items())[:2]:
                lines.append(f"  [{k}] {str(v)[:60]}")

    elif source == "profile":
        d = result["data"]
        lines.append(f"[用户画像] {d['field']}: {d['value']}")

    return "\n".join(lines) if lines else str(result)


def recall(session_id: str, query: str, top_k: int = 5):
    # 扩展查询词（加入同义词）
    query_tokens = expand_query(query)

    session_dir = ULTRA_MEMORY_HOME / "sessions" / session_id
    found = []

    # Layer 1: 操作日志（含时间权重 + 上下文窗口）
    ops_results = search_ops(session_dir, query_tokens, top_k)
    found.extend(ops_results)

    # Layer 2: 摘要
    summary_results = search_summary(session_dir, query_tokens)
    found.extend(summary_results)

    # Layer 3: 语义层（跨会话）
    semantic_results = search_semantic(query_tokens, top_k)
    found.extend(semantic_results)

    # 画像检索（从 user_profile.json 搜索相关字段）
    profile_results = search_profile(query_tokens, ULTRA_MEMORY_HOME)
    found.extend(profile_results)

    # Layer 4: 实体索引（结构化精确检索）
    entity_results = search_entities(query_tokens, top_k)
    found.extend(entity_results)

    # Layer 5: 向量语义搜索（TF-IDF 或 sentence-transformers）
    ops_for_tfidf = load_all_ops(session_dir)
    if ops_for_tfidf:
        tfidf_results = search_tfidf(session_dir, ops_for_tfidf, query, top_k)
        found.extend(tfidf_results)

    # 去重 + 排序
    found.sort(key=lambda x: -x["score"])
    found = found[:top_k]

    if not found:
        print(f"[RECALL] 未找到与「{query}」相关的记忆")
        return

    print(f"\n[RECALL] 找到 {len(found)} 条相关记录（查询: {query}）：\n")
    for i, r in enumerate(found, 1):
        print(f"{i}. {format_result(r, show_context=True)}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="检索记忆")
    parser.add_argument("--session", required=True, help="会话 ID")
    parser.add_argument("--query", required=True, help="检索关键词")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    recall(args.session, args.query, args.top_k)
