# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Mai Tấn Thành  
**Vai trò trong nhóm:** Supervisor Owner — Tech Lead  
**Ngày nộp:** 14/04/2026  
**Độ dài:** ~650 từ

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `graph.py` — toàn bộ Supervisor Agent và orchestration flow
- Functions tôi implement: `supervisor_node()` — routing logic với keyword rules; tích hợp `retrieval_worker_node()`, `policy_tool_worker_node()`, `synthesis_worker_node()` vào graph
- Ngoài ra: Setup infrastructure ban đầu (Phase 1) — cấu hình `.env`, migrate ChromaDB từ Day08, wire workers thật vào graph thay cho placeholder

**Cách công việc kết nối với phần khác:**

`supervisor_node()` là điểm vào duy nhất của mọi câu hỏi. Tôi phải hiểu input/output của từng worker (Tùng Anh, Nhất Khoa, Hoàng Nam) để route đúng. Nếu routing sai → toàn bộ pipeline trả lời sai dù worker chuẩn.

**Bằng chứng:**
- Commit: `[MTT] Improve supervisor routing: specific route_reason per keyword, multi-hop detection, risk_high flagging`
- Commit: `Phase 1: Setup infrastructure - VoyageAI + Anthropic + ChromaDB from Day08, wire workers into graph [MTT]`
- Comment `[MTT]` trong `supervisor_node()` dòng docstring

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Dùng **keyword-based routing** trong `supervisor_node()` thay vì gọi LLM để classify câu hỏi.

**Các lựa chọn thay thế:**
- LLM classifier: gọi Claude để phân loại → chính xác hơn với câu hỏi mơ hồ, nhưng thêm ~1000ms latency và tốn thêm API call mỗi lần
- Regex pattern: tương tự keyword nhưng phức tạp hơn khi maintain

**Lý do chọn keyword routing:**

Với 5 loại tài liệu nội bộ có cấu trúc rõ ràng (SLA, refund, access, HR, helpdesk), tín hiệu keyword đủ mạnh để phân loại đúng. Tôi thiết kế `POLICY_RULES` và `RETRIEVAL_RULES` dưới dạng list-of-tuples để dễ extend và đọc, mỗi rule gắn với `route_reason` cụ thể.

**Trade-off:** Routing có thể fail với câu hỏi không có keyword rõ ràng (edge case). Nhưng có fallback là `retrieval_worker` và confidence thấp → synthesis sẽ abstain thay vì bịa.

**Bằng chứng từ trace:**
```
Query: "Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp"
route_reason: "multi-hop: policy=['cấp quyền' (access control policy)]
              AND retrieval=[' p1' (P1 incident procedure)]
              → policy_tool first, retrieval second"
confidence: 0.51
```
Trace gq06 (2am P1 + Level 2): route=policy_tool_worker, conf=0.92 — routing chính xác với câu multi-hop khó nhất.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** ChromaDB collection name mismatch — pipeline không tìm được document nào.

**Symptom:**
```
⚠️ Collection 'day08_docs' does not exist
retrieved_chunks = []
confidence = 0.1
```
Pipeline chạy không crash nhưng trả lời hoàn toàn từ LLM knowledge, không cite source.

**Root cause:**

Tôi đặt `CHROMA_COLLECTION=day08_docs` trong `.env` dựa trên giả định tên collection từ Day08. Thực tế collection được build với tên `rag_lab`. Khi anh em clone repo và dùng `.env.example`, họ cũng sẽ dùng tên sai này.

**Cách sửa:**

Chạy trực tiếp Python để list collection:
```python
import chromadb
c = chromadb.PersistentClient(path='./chroma_db')
print([col.name for col in c.list_collections()])
# Output: ['rag_lab']
```
Sửa `.env` và `.env.example`: `CHROMA_COLLECTION=rag_lab`

**Bằng chứng trước/sau:**
- Trước: `confidence=0.1`, `retrieved_chunks=[]`, `sources=[]`
- Sau: `confidence=0.78`, `chunks=3`, `sources=['sla_p1_2026.txt', 'access_control_sop.txt', 'it_helpdesk_faq.txt']`
- Commit: `Fix: CHROMA_COLLECTION=rag_lab (actual Day08 collection name) [MTT]`

---

## 4. Tôi tự đánh giá đóng góp của mình

**Làm tốt nhất:**

Setup infrastructure và debug integration. Khi anh em push code lên với chroma_db sai (Hoàng Nam push nhầm), tôi phát hiện và khôi phục đúng collection trong <5 phút. Routing logic sau khi refactor phân loại đúng 15/15 test questions, đặc biệt câu multi-hop (q15) detect được cả hai signal `cấp quyền` + `P1` và ghi `route_reason` rõ ràng.

**Chưa tốt:**

Đầu tiên đặt sai `CHROMA_COLLECTION` trong `.env.example` — làm anh em mất thời gian debug. Nên verify tên collection trước khi push infrastructure.

**Nhóm phụ thuộc vào tôi:**

Toàn bộ pipeline bị block nếu `supervisor_node()` chưa xong — không ai test được worker của mình end-to-end. Ngoài ra tôi là người duy nhất có ChromaDB index đúng và `.env` với API keys.

**Tôi phụ thuộc vào:**

Tùng Anh (BM25/Hybrid) để retrieval có chất lượng tốt hơn; Nhất Khoa (LLM policy analysis) để policy route có câu trả lời chính xác hơn là if/else.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ thay `POLICY_RULES` keyword matching bằng **embedding similarity routing** — tính cosine similarity giữa câu hỏi và các anchor phrases ("policy refund exception", "SLA P1 escalation") để route. Lý do: trace câu q12 ("đặt đơn ngày 31/01") chỉ có `conf=0.30` vì keyword "hoàn tiền" không xuất hiện trực tiếp — routing đúng nhưng confidence thấp cho thấy retrieval không lấy được chunk tốt nhất. Embedding routing sẽ catch được ý nghĩa mà không cần exact keyword match.
