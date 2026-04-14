"""
rag_answer.py — Sprint 2 + Sprint 3: Retrieval & Grounded Answer
================================================================
Sprint 2 (60 phút): Baseline RAG
  - Dense retrieval từ ChromaDB
  - Grounded answer function với prompt ép citation
  - Trả lời được ít nhất 3 câu hỏi mẫu, output có source

Sprint 3 (60 phút): Tuning tối thiểu
  - Thêm hybrid retrieval (dense + sparse/BM25)
  - Hoặc thêm rerank (cross-encoder)
  - Hoặc thử query transformation (expansion, decomposition, HyDE)
  - Tạo bảng so sánh baseline vs variant

Definition of Done Sprint 2:
  ✓ rag_answer("SLA ticket P1?") trả về câu trả lời có citation
  ✓ rag_answer("Câu hỏi không có trong docs") trả về "Không đủ dữ liệu"

Definition of Done Sprint 3:
  ✓ Có ít nhất 1 variant (hybrid / rerank / query transform) chạy được
  ✓ Giải thích được tại sao chọn biến đó để tune
"""

import os
import re
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

load_dotenv()

# MTT: Import embedding function từ index.py (dùng cùng model VoyageAI khi index)
from index import get_embedding, CHROMA_DB_DIR

# =============================================================================
# CẤU HÌNH
# =============================================================================

TOP_K_SEARCH = 10    # Số chunk lấy từ vector store trước rerank (search rộng)
TOP_K_SELECT = 3     # Số chunk gửi vào prompt sau rerank/select (top-3 sweet spot)

# MTT: Dùng Claude Sonnet 4.6 qua Anthropic API
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")


# =============================================================================
# RETRIEVAL — DENSE (Vector Search)
# =============================================================================

def retrieve_dense(query: str, top_k: int = TOP_K_SEARCH) -> List[Dict[str, Any]]:
    """
    Dense retrieval: tìm kiếm theo embedding similarity trong ChromaDB.
    # MTT: Implement Sprint 2 — dùng VoyageAI embedding (cùng model với index.py)
    """
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    collection = client.get_collection("rag_lab")

    query_embedding = get_embedding(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text": doc,
            "metadata": meta,
            "score": round(1 - dist, 4),  # cosine distance → similarity
        })
    return chunks


# =============================================================================
# RETRIEVAL — SPARSE / BM25 (Keyword Search)
# Dùng cho Sprint 3 Variant hoặc kết hợp Hybrid
# =============================================================================

def retrieve_sparse(query: str, top_k: int = TOP_K_SEARCH) -> List[Dict[str, Any]]:
    """
    Sparse retrieval: tìm kiếm theo keyword (BM25).
    # DTA: Implement Sprint 3 — BM25 keyword search
    """
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    collection = client.get_collection("rag_lab")

    # Load all chunks to build BM25 index
    all_chunks = collection.get(include=["documents", "metadatas"])
    documents = all_chunks["documents"]
    metadatas = all_chunks["metadatas"]

    if not documents:
        return []

    # Tokenizer: loại bỏ các ký tự đặc biệt, dấu ngoặc để bắt từ khóa chính xác hơn
    def simple_tokenize(text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    # Tokenize corpus và query
    tokenized_corpus = [simple_tokenize(doc) for doc in documents]
    bm25 = BM25Okapi(tokenized_corpus)

    tokenized_query = simple_tokenize(query)
    scores = bm25.get_scores(tokenized_query)

    # Get top_k results
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    results = []
    for i in top_indices:
        results.append({
            "text": documents[i],
            "metadata": metadatas[i],
            "score": round(float(scores[i]), 4)
        })
    return results


# =============================================================================
# RETRIEVAL — HYBRID (Dense + Sparse với Reciprocal Rank Fusion)
# =============================================================================

def retrieve_hybrid(
    query: str,
    top_k: int = TOP_K_SEARCH,
    dense_weight: float = 0.6,
    sparse_weight: float = 0.4,
) -> List[Dict[str, Any]]:
    """
    Hybrid retrieval: kết hợp dense và sparse bằng Reciprocal Rank Fusion (RRF).
    # DTA: Implement Sprint 3 — RRF merging
    """
    dense_results = retrieve_dense(query, top_k=top_k * 2)  # Lấy rộng để merge
    sparse_results = retrieve_sparse(query, top_k=top_k * 2)

    # Reciprocal Rank Fusion (RRF)
    # RRF_score(doc) = sum( weight / (k + rank) )
    rrf_scores = {}  # { doc_text: score }
    doc_map = {}     # { doc_text: metadata }
    K = 60           # RRF constant

    # Process Dense
    for rank, res in enumerate(dense_results, 1):
        txt = res["text"]
        rrf_scores[txt] = rrf_scores.get(txt, 0) + dense_weight * (1.0 / (K + rank))
        doc_map[txt] = res["metadata"]

    # Process Sparse
    for rank, res in enumerate(sparse_results, 1):
        txt = res["text"]
        rrf_scores[txt] = rrf_scores.get(txt, 0) + sparse_weight * (1.0 / (K + rank))
        if txt not in doc_map:
            doc_map[txt] = res["metadata"]

    # Sort by RRF score
    sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    results = []
    for txt, score in sorted_docs:
        results.append({
            "text": txt,
            "metadata": doc_map[txt],
            "score": round(score, 6)
        })

    return results


# =============================================================================
# RERANK (Sprint 3 alternative)
# Cross-encoder để chấm lại relevance sau search rộng
# =============================================================================

def rerank(
    query: str,
    candidates: List[Dict[str, Any]],
    top_k: int = TOP_K_SELECT,
) -> List[Dict[str, Any]]:
    """
    Rerank các candidate chunks bằng cross-encoder.

    Cross-encoder: chấm lại "chunk nào thực sự trả lời câu hỏi này?"
    MMR (Maximal Marginal Relevance): giữ relevance nhưng giảm trùng lặp

    Funnel logic (từ slide):
      Search rộng (top-20) → Rerank (top-6) → Select (top-3)
    """

    try:
        import voyageai
        import os
        client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
        
        docs = [chunk["text"] for chunk in candidates]
        model_name = os.getenv("VOYAGE_RERANK_MODEL", "rerank-2")
        
        rerank_result = client.rerank(query=query, documents=docs, model=model_name, top_k=top_k)
        
        ranked_chunks = []
        for r in rerank_result.results:
            chunk = candidates[r.index].copy()
            chunk["score"] = round(r.relevance_score, 4)
            ranked_chunks.append(chunk)
            
        return ranked_chunks
    except Exception as e:
        print(f"[Rerank lỗi] {e}. Đang trả về kết quả không rerank.")
        return candidates[:top_k]


# =============================================================================
# QUERY TRANSFORMATION (Sprint 3 alternative)
# =============================================================================

def transform_query(query: str, strategy: str = "expansion") -> List[str]:
    """
    Biến đổi query để tăng recall.

    Strategies:
      - "expansion": Thêm từ đồng nghĩa, alias, tên cũ
      - "decomposition": Tách query phức tạp thành 2-3 sub-queries
      - "hyde": Sinh câu trả lời giả (hypothetical document) để embed thay query
    """

    if strategy == "expansion":
        prompt = f"""Given the query: '{query}'
Generate 2-3 alternative phrasings or related terms in Vietnamese.
Do not include any numbering, prefix, or explanation. Output each as a separate line."""
        response = call_llm(prompt)
        alternatives = [line.strip().lstrip('-').strip() for line in response.split('\n') if line.strip()]
        return [query] + alternatives
    elif strategy == "decomposition":
        prompt = f"""Break down this complex query into 2-3 simpler sub-queries in Vietnamese: '{query}'
Do not include any numbering, prefix, or explanation. Output each sub-query on a separate line."""
        response = call_llm(prompt)
        sub_queries = [line.strip().lstrip('-').strip() for line in response.split('\n') if line.strip()]
        return sub_queries
    elif strategy == "hyde":
        prompt = f"""Write a hypothetical document paragraph in Vietnamese that would directly answer this query: '{query}'
Do not include any explanation. Just provide the direct paragraph."""
        response = call_llm(prompt)
        return [response.strip()]
    return [query]


# =============================================================================
# GENERATION — GROUNDED ANSWER FUNCTION
# =============================================================================

def build_context_block(chunks: List[Dict[str, Any]]) -> str:
    """
    Đóng gói danh sách chunks thành context block để đưa vào prompt.

    Format: structured snippets với source, section, score (từ slide).
    Mỗi chunk có số thứ tự [1], [2], ... để model dễ trích dẫn.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source = meta.get("source", "unknown")
        section = meta.get("section", "")
        score = chunk.get("score", 0)
        text = chunk.get("text", "")

        # TODO: Tùy chỉnh format nếu muốn (thêm effective_date, department, ...)
        header = f"[{i}] {source}"
        if section:
            header += f" | {section}"
        if score > 0:
            header += f" | score={score:.2f}"

        context_parts.append(f"{header}\n{text}")

    return "\n\n".join(context_parts)


def build_grounded_prompt(query: str, context_block: str) -> str:
    """
    Xây dựng grounded prompt theo 4 quy tắc từ slide:
    1. Evidence-only: Chỉ trả lời từ retrieved context
    2. Abstain: Thiếu context thì nói không đủ dữ liệu
    3. Citation: Gắn source/section khi có thể
    4. Short, clear, stable: Output ngắn, rõ, nhất quán
    """
    prompt = f"""Bạn là một Chuyên viên CS & IT Helpdesk (trợ lý nội bộ) cực kỳ chuyên nghiệp và tận tâm.
    Dưới đây là các chứng cứ (context) được hệ thống trích xuất từ tài liệu policy, quy trình và SLA của nội bộ công ty.

    YÊU CẦU BẮT BUỘC:
    1. EVIDENCE-ONLY: Chỉ trả lời dựa rập khuôn theo nội dung chứng cứ bên dưới.
    2. ABSTAIN: Nếu context thiếu thông tin hoặc không liên quan, hãy thẳng thắn từ chối: "Xin lỗi, hiện tại tôi không có đủ dữ liệu từ tài liệu hệ thống để trả lời câu hỏi này." và TUYỆT ĐỐI KHÔNG chế tạo thêm số liệu/quy trình.
    3. CITATION: Bắt buộc đính kèm trích dẫn nguồn ở định dạng [1], [2] khi dẫn chứng điều khoản, SLA hay thông tin kỹ thuật nào.
    4. FORMAT: Trình bày súc tích. Hãy sử dụng bullet points cho các điều kiện, bước xử lý, quyền truy cập hoặc các mã lỗi.
    5. TONE: Giữ giọng văn thân thiện, hỗ trợ bằng Tiếng Việt.

    Question: {query}

    Context:
    {context_block}

    Answer:"""
    return prompt


def call_llm(prompt: str) -> str:
    """
    Gọi Claude Sonnet 4.6 qua Anthropic API để sinh câu trả lời.
    # MTT: Implement Sprint 2 — temperature=0 để output ổn định cho eval
    """
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=512,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def rag_answer(
    query: str,
    retrieval_mode: str = "dense",
    top_k_search: int = TOP_K_SEARCH,
    top_k_select: int = TOP_K_SELECT,
    use_rerank: bool = False,
    use_transform: bool = False,
    transform_strategy: str = "expansion",
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Pipeline RAG hoàn chỉnh: (transform) → query → retrieve → (rerank) → generate.
    """
    config = {
        "retrieval_mode": retrieval_mode,
        "top_k_search": top_k_search,
        "top_k_select": top_k_select,
        "use_rerank": use_rerank,
        "use_transform": use_transform,
        "transform_strategy": transform_strategy if use_transform else None,
    }

    # --- Bước 0: Transform Query (optional) ---
    search_queries = [query]
    if use_transform:
        search_queries = transform_query(query, strategy=transform_strategy)
        if verbose:
            print(f"[RAG] Transformed queries: {search_queries}")

    # --- Bước 1: Retrieve ---
    all_candidates = []
    for q in search_queries:
        if retrieval_mode == "dense":
            all_candidates.extend(retrieve_dense(q, top_k=top_k_search))
        elif retrieval_mode == "sparse":
            all_candidates.extend(retrieve_sparse(q, top_k=top_k_search))
        elif retrieval_mode == "hybrid":
            all_candidates.extend(retrieve_hybrid(q, top_k=top_k_search))
        else:
            raise ValueError(f"retrieval_mode không hợp lệ: {retrieval_mode}")

    # Deduplicate candidates by text
    seen_texts = set()
    candidates = []
    for c in all_candidates:
        if c["text"] not in seen_texts:
            candidates.append(c)
            seen_texts.add(c["text"])

    if verbose:
        print(f"\n[RAG] Query: {query}")
        print(f"[RAG] Retrieved {len(candidates)} candidates (mode={retrieval_mode})")
        for i, c in enumerate(candidates[:3]):
            print(f"  [{i+1}] score={c.get('score', 0):.3f} | {c['metadata'].get('source', '?')}")

    # --- Bước 2: Rerank (optional) ---
    if use_rerank:
        candidates = rerank(query, candidates, top_k=top_k_select)
    else:
        candidates = candidates[:top_k_select]

    if verbose:
        print(f"[RAG] After select: {len(candidates)} chunks")

    # --- Bước 3: Build context và prompt ---
    context_block = build_context_block(candidates)
    prompt = build_grounded_prompt(query, context_block)

    if verbose:
        print(f"\n[RAG] Prompt:\n{prompt[:500]}...\n")

    # --- Bước 4: Generate ---
    answer = call_llm(prompt)

    # --- Bước 5: Extract sources ---
    sources = list({
        c["metadata"].get("source", "unknown")
        for c in candidates
    })

    return {
        "query": query,
        "answer": answer,
        "sources": sources,
        "chunks_used": candidates,
        "config": config,
    }


# =============================================================================
# SPRINT 3: SO SÁNH BASELINE VS VARIANT
# =============================================================================

def compare_retrieval_strategies(query: str) -> None:
    """
    So sánh các retrieval strategies với cùng một query.

    TODO Sprint 3:
    Chạy hàm này để thấy sự khác biệt giữa dense, sparse, hybrid.
    Dùng để justify tại sao chọn variant đó cho Sprint 3.

    A/B Rule (từ slide): Chỉ đổi MỘT biến mỗi lần.
    """
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print('='*60)

    strategies = ["dense", "hybrid"]  # Thêm "sparse" sau khi implement

    for strategy in strategies:
        print(f"\n--- Strategy: {strategy} ---")
        try:
            result = rag_answer(query, retrieval_mode=strategy, verbose=False)
            print(f"Answer: {result['answer']}")
            print(f"Sources: {result['sources']}")
        except NotImplementedError as e:
            print(f"Chưa implement: {e}")
        except Exception as e:
            print(f"Lỗi: {e}")


# =============================================================================
# MAIN — Demo và Test
# =============================================================================

if __name__ == "__main__":
    # =========================================================================
    # CẤU HÌNH CHẠY THỬ (DTA - Tùng Anh)
    # Lựa chọn 1 trong 5 chế độ:
    # 1. "dense": Chỉ dùng Vector Search (Baseline)
    # 2. "sparse": Chỉ dùng BM25 Keyword Search
    # 3. "hybrid": Kết hợp Dense + Sparse (RRF)
    # 4. "hybrid_rerank": Hybrid + VoyageAI Reranker (Top Accuracy)
    # 5. "hybrid_transform": Hybrid + Query Expansion (Top Recall)
    # =========================================================================
    MODE = "hybrid_transform"
    # =========================================================================

    print("=" * 60)
    print(f"RAG Answer Pipeline - Mode: {MODE.upper()}")
    print("=" * 60)

    # Cấu hình tham số dựa trên MODE
    config_params = {
        "retrieval_mode": "hybrid",
        "use_rerank": False,
        "use_transform": False,
    }

    if MODE == "dense":
        config_params["retrieval_mode"] = "dense"
    elif MODE == "sparse":
        config_params["retrieval_mode"] = "sparse"
    elif MODE == "hybrid":
        config_params["retrieval_mode"] = "hybrid"
    elif MODE == "hybrid_rerank":
        config_params["retrieval_mode"] = "hybrid"
        config_params["use_rerank"] = True
    elif MODE == "hybrid_transform":
        config_params["retrieval_mode"] = "hybrid"
        config_params["use_transform"] = True
        config_params["transform_strategy"] = "expansion"

    # Test queries từ data/test_questions.json
    test_queries = [
        "SLA xử lý ticket P1 là bao lâu?",
        "Dự án IT-ACCESS là gì?",
        "ERR-403-AUTH là lỗi gì?",
    ]

    print(f"\n--- Chạy thử với Mode: {MODE} ---")
    for query in test_queries:
        print(f"\nQuery: {query}")
        try:
            result = rag_answer(query, **config_params, verbose=True)
            print(f"Answer: {result['answer']}")
            print(f"Sources: {result['sources']}")
        except NotImplementedError:
            print(f"Chưa implement mode {MODE}.")
        except Exception as e:
            print(f"Lỗi: {e}")

    # Nếu muốn so sánh các strategies, hãy gọi hàm dưới đây:
    print("\n--- So sánh strategies ---")
    compare_retrieval_strategies("IT-ACCESS")

    print("\n\nViệc cần làm Sprint 2:")
    print("  1. Implement retrieve_dense() — query ChromaDB")
    print("  2. Implement call_llm() — gọi OpenAI hoặc Gemini")
    print("  3. Chạy rag_answer() với 3+ test queries")
    print("  4. Verify: output có citation không? Câu không có docs → abstain không?")

    print("\nViệc cần làm Sprint 3:")
    print("  1. Chọn 1 trong 3 variants: hybrid, rerank, hoặc query transformation")
    print("  2. Implement variant đó")
    print("  3. Chạy compare_retrieval_strategies() để thấy sự khác biệt")
    print("  4. Ghi lý do chọn biến đó vào docs/tuning-log.md")
