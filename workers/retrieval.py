"""
workers/retrieval.py — Retrieval Worker
Sprint 2: Implement retrieval từ ChromaDB, trả về chunks + sources.

Input (từ AgentState):
    - task: câu hỏi cần retrieve
    - (optional) retrieved_chunks nếu đã có từ trước

Output (vào AgentState):
    - retrieved_chunks: list of {"text", "source", "score", "metadata"}
    - retrieved_sources: list of source filenames
    - worker_io_log: log input/output của worker này

Gọi độc lập để test:
    python workers/retrieval.py
"""

import math
import os
import re
import sys
from collections import Counter
from dotenv import load_dotenv
load_dotenv()

# ─────────────────────────────────────────────
# Worker Contract (xem contracts/worker_contracts.yaml)
# Input:  {"task": str, "top_k": int = 3}
# Output: {"retrieved_chunks": list, "retrieved_sources": list, "error": dict | None}
# ─────────────────────────────────────────────

WORKER_NAME = "retrieval_worker"
DEFAULT_TOP_K = 3
DEFAULT_RETRIEVAL_MODE = "hybrid"


def _get_embedding_fn():
    """
    Trả về embedding function dùng VoyageAI (kế thừa từ Day 08).
    """
    # Option A: VoyageAI (kế thừa từ Day 08 — primary)
    try:
        import voyageai
        voyage_client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
        model_name = os.getenv("VOYAGE_EMBEDDING_MODEL", "voyage-multilingual-2")
        def embed(text: str) -> list:
            result = voyage_client.embed([text], model=model_name)
            return result.embeddings[0]
        return embed
    except Exception:
        pass

    # Option B: Sentence Transformers (offline fallback)
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        def embed(text: str) -> list:
            return model.encode([text])[0].tolist()
        return embed
    except ImportError:
        pass

    # Fallback: random embeddings cho test (KHÔNG dùng production)
    import random
    def embed(text: str) -> list:
        return [random.random() for _ in range(1024)]  # VoyageAI dim=1024
    print("⚠️  WARNING: Using random embeddings (test only).")
    return embed


def _get_collection():
    """
    Kết nối ChromaDB collection — dùng lại index từ Day 08.
    """
    import chromadb
    db_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
    collection_name = os.getenv("CHROMA_COLLECTION", "day08_docs")
    client = chromadb.PersistentClient(path=db_path)
    try:
        collection = client.get_collection(collection_name)
        return collection
    except Exception:
        print(f"⚠️  Collection '{collection_name}' chưa có. Kiểm tra chroma_db/ đã copy từ Day 08 chưa.")
        raise


def _tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize bằng regex để giữ keyword kiểu IT-ACCESS ổn định hơn split()."""
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())


def _bm25_scores(tokenized_corpus: list[list[str]], tokenized_query: list[str]) -> list[float]:
    """
    Tính BM25 scores.
    Ưu tiên dùng rank_bm25 nếu có; nếu không có thì fallback sang bản BM25 tối giản.
    """
    try:
        from rank_bm25 import BM25Okapi

        bm25 = BM25Okapi(tokenized_corpus)
        return [float(score) for score in bm25.get_scores(tokenized_query)]
    except ImportError:
        if not tokenized_corpus:
            return []

        document_count = len(tokenized_corpus)
        avg_doc_len = sum(len(doc) for doc in tokenized_corpus) / document_count
        doc_freq = Counter()
        for doc in tokenized_corpus:
            doc_freq.update(set(doc))

        k1 = 1.5
        b = 0.75
        scores = []
        for doc in tokenized_corpus:
            term_freq = Counter(doc)
            doc_len = len(doc) or 1
            score = 0.0
            for token in tokenized_query:
                if token not in term_freq:
                    continue
                df = doc_freq.get(token, 0)
                idf = math.log(((document_count - df + 0.5) / (df + 0.5)) + 1.0)
                numerator = term_freq[token] * (k1 + 1.0)
                denominator = term_freq[token] + k1 * (1.0 - b + b * (doc_len / avg_doc_len))
                score += idf * (numerator / denominator)
            scores.append(float(score))
        return scores


def retrieve_dense(query: str, top_k: int = DEFAULT_TOP_K) -> list:
    """
    Dense retrieval: embed query → query ChromaDB → trả về top_k chunks.

    TODO Sprint 2: Implement phần này.
    - Dùng _get_embedding_fn() để embed query
    - Query collection với n_results=top_k
    - Format result thành list of dict

    Returns:
        list of {"text": str, "source": str, "score": float, "metadata": dict}
    """
    # TODO: Implement dense retrieval
    embed = _get_embedding_fn()
    query_embedding = embed(query)

    try:
        collection = _get_collection()
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "distances", "metadatas"]
        )

        chunks = []
        for i, (doc, dist, meta) in enumerate(zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0]
        )):
            chunks.append({
                "text": doc,
                "source": meta.get("source", "unknown"),
                "score": round(1 - dist, 4),  # cosine similarity
                "metadata": meta,
            })
        return chunks

    except Exception as e:
        print(f"⚠️  ChromaDB query failed: {e}")
        # Fallback: return empty (abstain)
        return []


def retrieve_sparse(query: str, top_k: int = DEFAULT_TOP_K) -> list:
    """
    Sparse retrieval bằng BM25 trên toàn bộ corpus.
    Trả cùng format chunk như dense để dễ merge và đúng contract worker.
    """
    try:
        collection = _get_collection()
        all_chunks = collection.get(include=["documents", "metadatas"])
        documents = all_chunks.get("documents", [])
        metadatas = all_chunks.get("metadatas", [])

        if not documents:
            return []

        tokenized_corpus = [_tokenize_for_bm25(doc) for doc in documents]
        tokenized_query = _tokenize_for_bm25(query)
        scores = _bm25_scores(tokenized_corpus, tokenized_query)
        ranked_indices = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)[:top_k]

        chunks = []
        for idx in ranked_indices:
            metadata = metadatas[idx] or {}
            chunks.append({
                "text": documents[idx],
                "source": metadata.get("source", "unknown"),
                "score": round(float(scores[idx]), 4),
                "metadata": metadata,
            })
        return chunks
    except Exception as e:
        print(f"⚠️  Sparse retrieval failed: {e}")
        return []


def retrieve_hybrid(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    dense_weight: float = 0.6,
    sparse_weight: float = 0.4,
) -> list:
    """
    Hybrid retrieval: merge dense + sparse bằng Reciprocal Rank Fusion (RRF).
    Không cộng trực tiếp raw score vì hai thang đo khác nhau.
    """
    dense_results = retrieve_dense(query, top_k=max(top_k * 2, top_k))
    sparse_results = retrieve_sparse(query, top_k=max(top_k * 2, top_k))

    rrf_scores = {}
    merged_chunks = {}
    rrf_k = 60

    for rank, chunk in enumerate(dense_results, start=1):
        chunk_id = chunk["text"]
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + dense_weight * (1.0 / (rrf_k + rank))
        merged_chunks[chunk_id] = chunk

    for rank, chunk in enumerate(sparse_results, start=1):
        chunk_id = chunk["text"]
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + sparse_weight * (1.0 / (rrf_k + rank))
        if chunk_id not in merged_chunks:
            merged_chunks[chunk_id] = chunk

    ranked_chunks = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    return [
        {
            "text": chunk_id,
            "source": merged_chunks[chunk_id]["source"],
            "score": round(float(score), 6),
            "metadata": merged_chunks[chunk_id]["metadata"],
        }
        for chunk_id, score in ranked_chunks
    ]


def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.

    Args:
        state: AgentState dict

    Returns:
        Updated AgentState với retrieved_chunks và retrieved_sources
    """
    task = state.get("task", "")
    top_k = state.get("retrieval_top_k", DEFAULT_TOP_K)
    retrieval_mode = state.get("retrieval_mode", DEFAULT_RETRIEVAL_MODE)

    state.setdefault("workers_called", [])
    state.setdefault("history", [])

    state["workers_called"].append(WORKER_NAME)

    # Log worker IO (theo contract)
    worker_io = {
        "worker": WORKER_NAME,
        "input": {"task": task, "top_k": top_k, "retrieval_mode": retrieval_mode},
        "output": None,
        "error": None,
    }

    try:
        if retrieval_mode == "dense":
            chunks = retrieve_dense(task, top_k=top_k)
        elif retrieval_mode == "sparse":
            chunks = retrieve_sparse(task, top_k=top_k)
        else:
            chunks = retrieve_hybrid(task, top_k=top_k)

        sources = list({c["source"] for c in chunks})

        state["retrieved_chunks"] = chunks
        state["retrieved_sources"] = sources

        worker_io["output"] = {
            "chunks_count": len(chunks),
            "sources": sources,
            "retrieval_mode": retrieval_mode,
        }
        state["history"].append(
            f"[{WORKER_NAME}] mode={retrieval_mode} retrieved {len(chunks)} chunks from {sources}"
        )

    except Exception as e:
        worker_io["error"] = {"code": "RETRIEVAL_FAILED", "reason": str(e)}
        state["retrieved_chunks"] = []
        state["retrieved_sources"] = []
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    # Ghi worker IO vào state để trace
    state.setdefault("worker_io_logs", []).append(worker_io)

    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Retrieval Worker - Standalone Test")
    print("=" * 50)

    test_queries = [
        "SLA ticket P1 la bao lau?",
        "Dieu kien duoc hoan tien la gi?",
        "Ai phe duyet cap quyen Level 3?",
    ]

    for query in test_queries:
        print(f"\n> Query: {query}")
        result = run({"task": query})
        chunks = result.get("retrieved_chunks", [])
        print(f"  Retrieved: {len(chunks)} chunks")
        for c in chunks[:2]:
            print(f"    [{c['score']:.3f}] {c['source']}: {c['text'][:80]}...")
        print(f"  Sources: {result.get('retrieved_sources', [])}")

    print("\n[OK] retrieval_worker test done.")
