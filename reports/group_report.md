# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Nhóm 02 — Lớp 402  
**Thành viên:**
| Tên | Vai trò | GitHub |
|-----|---------|--------|
| Mai Tấn Thành | Supervisor Owner — Tech Lead | MTT |
| Đặng Tùng Anh | Worker Owner — Retrieval | dtnganh |
| Hồ Nhất Khoa | MCP Owner — Policy Tool + UI | Khoa612 |
| Phạm Lê Hoàng Nam | Worker Owner — Synthesis | PaimonZero |
| Nguyễn Đức Hoàng Phúc | Trace & Docs Owner | somene112 |

**Ngày nộp:** 14/04/2026  
**Repo:** https://github.com/xandrosworld/Nhom02-402-Day09

---

## 1. Kiến trúc nhóm đã xây dựng

Nhóm xây dựng hệ thống **Supervisor-Worker Graph** gồm 1 supervisor điều phối và 3 specialized workers:

- **Supervisor** (`graph.py`): nhận câu hỏi đầu vào, phân tích keyword, quyết định route sang `retrieval_worker`, `policy_tool_worker`, hoặc `human_review`, rồi luôn kết thúc bằng `synthesis_worker`.
- **Retrieval Worker** (`workers/retrieval.py`): Hybrid BM25 + VoyageAI dense retrieval với Reciprocal Rank Fusion. Truy vấn ChromaDB collection `rag_lab` (29 chunks, 1024-dim VoyageAI embeddings từ Day08).
- **Policy Tool Worker** (`workers/policy_tool.py`): Sử dụng Claude LLM qua MCP để phân tích exception từ 5 tài liệu nội bộ. Xử lý Flash Sale, digital product, contractor access.
- **Synthesis Worker** (`workers/synthesis.py`): Gọi Anthropic Claude Sonnet để tổng hợp câu trả lời grounded từ retrieved chunks và policy context. Output có citation `[1]`, `[2]`.

**Routing logic cốt lõi:** Keyword-based routing với `POLICY_RULES` và `RETRIEVAL_RULES` — mỗi rule gắn với `route_reason` cụ thể. Multi-hop queries (có cả policy + SLA keyword) route sang `policy_tool_worker` trước, sau đó retrieval.

**MCP tools đã tích hợp (4 tools):**
- `search_kb`: Tìm kiếm ChromaDB Knowledge Base
- `get_ticket_info`: Tra cứu thông tin ticket P1 (mock data)
- `check_access_permission`: Kiểm tra quyền truy cập theo level
- `create_ticket`: Tạo ticket mới (mock)

MCP usage rate: **52–56%** câu hỏi gọi ít nhất 1 MCP tool.

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định:** Dùng ChromaDB collection từ Day08 (`rag_lab`) thay vì rebuild index mới.

**Bối cảnh vấn đề:**

Khi migration từ Day08 sang Day09, nhóm phải quyết định có rebuild ChromaDB hay reuse index cũ. Rebuild với VoyageAI đảm bảo control, nhưng mất 15–20 phút và tốn API credit. Nhóm mắc thêm lỗi: một thành viên push nhầm chroma_db với collection 384-dim (Sentence Transformers) lên remote, đè mất collection VoyageAI 1024-dim gốc.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| Reuse `rag_lab` từ Day08 | Không cần rebuild, tiết kiệm 15 phút | Phụ thuộc vào index chất lượng Day08 |
| Rebuild index mới với Day09 data | Control hoàn toàn | Tốn thời gian, tốn API |
| Sentence Transformers (offline) | Không cần API key | 384-dim, chất lượng thấp hơn VoyageAI |

**Phương án đã chọn:** Reuse `rag_lab` + restore từ local backup khi remote bị overwrite.

**Bằng chứng từ trace/code:**

```
# Trước khi fix — collection sai:
⚠️ Collection 'day08_docs' does not exist → retrieved_chunks=[] → confidence=0.1

# Sau khi fix CHROMA_COLLECTION=rag_lab:
Route: retrieval_worker
retrieved_chunks: 3
sources: ['sla_p1_2026.txt', 'access_control_sop.txt', 'it_helpdesk_faq.txt']
confidence: 0.78
```

Commit fix: `Fix: CHROMA_COLLECTION=rag_lab (actual Day08 collection name) [MTT]`

---

## 3. Kết quả grading questions

Pipeline chạy `grading_questions.json` lúc 17:26 — **10/10 succeeded, 0 crash.**

**Tổng điểm raw ước tính:** ~82–88 / 96

**Câu pipeline xử lý tốt nhất:**
- **gq04** (store credit %) — conf=1.00: Policy worker retrieve đúng số liệu `110%` từ `customer-refund-policy-2026.pdf`
- **gq02** (remote VPN) — conf=1.00: Retrieval worker tìm ngay điều khoản HR policy
- **gq10** (Flash Sale policy) — conf=0.97: Policy worker detect exception Flash Sale + xử lý tình huống edge case

**Câu khó nhất xử lý được:**
- **gq06** (2am P1 + Level 2 access tạm thời) — conf=0.92: Multi-hop routing đúng, trace ghi 2 workers `policy_tool_worker` + `synthesis_worker`

**Câu gq07 (abstain — "mức phạt tài chính SLA P1"):**
Pipeline trả về `confidence=0.30` và nội dung từ chối rõ ràng — thông tin phạt tài chính không có trong tài liệu nội bộ → **abstain đúng, không hallucinate → 10/10 điểm câu này.**

**Câu gq06 (multi-hop):** Trace ghi đủ 2 workers được gọi, route_reason: `"multi-hop: policy=['cấp quyền'] AND retrieval=['p1'] → risk_high=True"`.

---

## 4. So sánh Day 08 vs Day 09

Dựa vào `docs/single_vs_multi_comparison.md` và trace thực tế:

**Metric thay đổi rõ nhất:**

| Metric | Day 08 (Single) | Day 09 (Multi) | Nhận xét |
|--------|----------------|----------------|----------|
| Avg confidence | ~0.6 | **0.735** | +22% nhờ policy tool |
| Latency | ~5s | ~11–17s | Chậm hơn 2–3x do multi-step |
| Abstain rate | 0% | **6%** | Tránh hallucinate câu không có trong docs |
| Debuggability | Khó trace | **Cao** — mỗi step có log | route_reason + worker_io_log |

**Điều bất ngờ nhất:** Multi-agent chậm hơn đáng kể (~12s avg vs ~5s) nhưng abstain rate tăng từ 0% lên 6% — pipeline biết "từ chối" câu không có context thay vì bịa, điều mà single-agent Day08 không làm được.

**Trường hợp multi-agent không giúp ích:** Câu đơn giản 1-hop (VD: gq02 remote policy, gq08 leave policy) — single agent cũng trả lời đúng với latency thấp hơn. Multi-agent overhead không cần thiết cho loại câu này.

---

## 5. Phân công và đánh giá nhóm

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Mai Tấn Thành | graph.py, supervisor routing, infrastructure setup, debug ChromaDB | 1, Integration |
| Đặng Tùng Anh | workers/retrieval.py — Hybrid BM25+Dense, RRF merge | 2 |
| Hồ Nhất Khoa | workers/policy_tool.py, mcp_server.py (4 tools), app.py (Gradio UI) | 2, 3 |
| Phạm Lê Hoàng Nam | workers/synthesis.py, docs/routing_decisions.md, docs/system_architecture.md | 2, 4 |
| Nguyễn Đức Hoàng Phúc | eval_trace.py, grading run, docs/single_vs_multi_comparison.md | 4 |

**Điều nhóm làm tốt:**

Phân chia sprint rõ ràng theo worker contract — mỗi người test worker độc lập trước khi integrate. Pipeline không crash lần nào trong grading run. Supervisor routing đủ thông minh để detect multi-hop (gq06, gq09) và abstain đúng (gq07).

**Điều nhóm làm chưa tốt:**

Một thành viên push nhầm chroma_db lên remote (384-dim Sentence Transformers đè 1024-dim VoyageAI), gây gián đoạn integration ~20 phút. Cần quy trình review trước khi push binary files lên repo.

**Nếu làm lại:** Dùng branch riêng cho từng worker, merge vào main sau khi Lead review — tránh push nhầm file lớn.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì?

**Cải tiến 1:** Thay keyword routing bằng embedding similarity routing để handle câu không có exact keyword. Evidence: gq02 (remote VPN) conf=1.00 nhưng q12 (temporal "31/01") conf=0.30 — pipeline route đúng nhưng không retrieve đủ context vì thiếu keyword trigger.

**Cải tiến 2:** Implement LLM-as-Judge để đánh giá confidence thực tế thay vì dùng RRF score normalize. Evidence: trace cho thấy confidence=1.00 ở nhiều câu nhưng không phân biệt được câu trả lời "chắc chắn đúng" vs "có thể đúng".
