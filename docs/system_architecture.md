# System Architecture — Lab Day 09

**Nhóm:** Nhóm 02 — Lớp 402  
**Ngày:** 14/04/2026  
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

**Pattern đã chọn:** Supervisor-Worker Graph  
**Lý do chọn pattern này (thay vì single agent):**

Hệ thống Day09 áp dụng Supervisor-Worker để phân tách trách nhiệm rõ ràng. Supervisor chỉ làm 1 việc: phân tích câu hỏi và quyết định route. Từng worker chuyên biệt xử lý đúng domain của mình (retrieval, policy, synthesis). Điều này giúp:
- **Debug độc lập:** mỗi worker có thể test mà không cần chạy cả graph
- **Trace rõ ràng:** mỗi bước có log `route_reason`, `worker_io_log`
- **Mở rộng dễ:** thêm worker mới chỉ cần wire vào graph, không sửa logic cũ

---

## 2. Sơ đồ Pipeline

```text
User Request (câu hỏi tiếng Việt)
         │
         ▼
┌─────────────────────────────────────────┐
│              SUPERVISOR                 │
│   • Phân tích keyword trong task        │
│   • Quyết định route + route_reason     │
│   • Đánh dấu risk_high nếu khẩn cấp    │
│   • needs_tool = True nếu cần MCP       │
└──────────────────┬──────────────────────┘
                   │ route_decision()
         ┌─────────┼──────────────┐
         │         │              │
         ▼         ▼              ▼
  retrieval    policy_tool    human_review
   _worker      _worker        (HITL)
         │         │              │
         │    ┌────┤ MCP calls    │
         │    │ search_kb        │
         │    │ get_ticket_info  │
         │    │ check_access_... │
         │    └────┘              │
         └─────────┬──────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │ SYNTHESIS WORKER│
         │ Claude Sonnet   │
         │ + citations [1] │
         └────────┬────────┘
                  │
                  ▼
           Final Answer
    {answer, sources, confidence,
     route_reason, workers_called,
     mcp_tools_used, hitl_triggered}
```

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Phân tích câu hỏi, quyết định route tới đúng worker |
| **Input** | `task` (str) — câu hỏi đầu vào |
| **Output** | `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` |
| **Routing logic** | Keyword-based: `POLICY_RULES` (hoàn tiền, flash sale, cấp quyền...) vs `RETRIEVAL_RULES` (sla, p1, remote, bao lâu...). Multi-hop khi có cả 2 loại keyword. |
| **HITL condition** | Pattern `ERR-xxx` không khớp SLA/procedure keyword → `human_review` |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Tìm top-k chunks liên quan từ ChromaDB bằng Hybrid retrieval |
| **Embedding model** | VoyageAI `voyage-multilingual-2` (1024-dim) |
| **Retrieval mode** | Hybrid: Dense (VoyageAI) + Sparse (BM25) merged bằng RRF (dense_weight=0.6, sparse_weight=0.4) |
| **Top-k** | 3 (mặc định, configurable qua env `RETRIEVAL_TOP_K`) |
| **Score normalization** | RRF scores được normalize về [0.5, 1.0] trước khi trả ra để confidence calculation chính xác |
| **Stateless?** | Yes — không giữ state giữa các request |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Phân tích exception/edge case trong policy. Gọi MCP tools để lấy context. |
| **MCP tools gọi** | `search_kb` (tìm policy docs), `get_ticket_info` (lấy ticket details) |
| **Exception cases xử lý** | Flash Sale (không hoàn tiền), digital product/license key, contractor access, store credit |
| **LLM** | Claude Sonnet 4.6 — structured JSON output với `policy_applies`, `llm_exceptions`, `recommendation` |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **LLM model** | Claude Sonnet 4.6 (Primary) — Anthropic API |
| **Temperature** | 0 — tăng tính chính xác, giảm hallucination |
| **Grounding strategy** | System prompt yêu cầu chỉ dùng context được cung cấp, không dùng prior knowledge |
| **Abstain condition** | `retrieved_chunks=[]` hoặc answer chứa "Không đủ thông tin" → confidence=0.1–0.3 |
| **Citation** | Output có `[1]`, `[2]` linking về retrieved sources |

### MCP Server (`mcp_server.py`)

| Tool | Input | Output |
|------|-------|--------|
| `search_kb` | query (str), top_k (int) | chunks (list), sources (list), total_found (int) |
| `get_ticket_info` | ticket_id (str) | ticket details: priority, status, assignee, SLA deadline, escalated |
| `check_access_permission` | access_level (str), requester_role (str) | can_grant (bool), approvers (list), conditions (list) |
| `create_ticket` | priority, title, description | ticket_id, created_at, assigned_to |

---

## 4. Shared State Schema

| Field | Type | Mô tả | Ai đọc/ghi |
|-------|------|-------|-----------|
| `task` | str | Câu hỏi đầu vào | supervisor đọc |
| `supervisor_route` | str | Worker được chọn | supervisor ghi |
| `route_reason` | str | Lý do route cụ thể + keyword trigger | supervisor ghi |
| `risk_high` | bool | True nếu có keyword khẩn cấp | supervisor ghi |
| `needs_tool` | bool | True nếu cần MCP | supervisor ghi |
| `retrieved_chunks` | list[dict] | Evidence: {text, source, score, metadata} | retrieval ghi, synthesis đọc |
| `retrieved_sources` | list[str] | Tên file nguồn | retrieval ghi |
| `policy_result` | dict | {policy_applies, exceptions_found, recommendation} | policy_tool ghi, synthesis đọc |
| `mcp_tools_used` | list[dict] | {tool, input, output, timestamp} | policy_tool ghi |
| `final_answer` | str | Câu trả lời cuối có citation | synthesis ghi |
| `confidence` | float | 0.1–1.0 dựa vào chunk scores | synthesis ghi |
| `hitl_triggered` | bool | True nếu human review được kích hoạt | human_review ghi |
| `workers_called` | list[str] | Thứ tự các worker đã chạy | Mỗi worker append |
| `history` | list[str] | Log từng bước xử lý | Tất cả node append |
| `worker_io_logs` | list[dict] | Chi tiết input/output của từng worker | Mỗi worker ghi |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------|
| Debug khi sai | Khó — không rõ lỗi ở bước nào | Rõ ràng — xem `route_reason` + `worker_io_log` |
| Thêm capability mới | Phải sửa toàn prompt | Thêm worker hoặc MCP tool, không ảnh hưởng logic cũ |
| Routing visibility | Không có | route_reason log chi tiết trong mọi trace |
| Xử lý multi-hop | Không native | Supervisor detect, call policy_tool + retrieval tuần tự |
| Abstain / HITL | Không có | human_review node cho ERR-xxx và câu không đủ context |
| Avg confidence | ~0.6 (tất cả câu) | **0.735** (phân biệt câu chắc vs không chắc) |
| Latency | ~5s | ~12s (cost của multi-step) |

**Quan sát thực tế từ lab:**

Supervisor-Worker giúp câu gq07 ("mức phạt tài chính SLA P1" — không có trong docs) được abstain đúng (`conf=0.30`) thay vì hallucinate. Single Agent Day08 không có cơ chế này. Đây là khác biệt rõ nhất giữa 2 kiến trúc, được chứng minh trực tiếp từ grading trace.

---

## 6. Giới hạn và điểm cần cải tiến

1. **Latency cao:** ~12s avg do multi-step API calls. Cải tiến: cache retrieval results cho câu hỏi tương tự.
2. **Routing phụ thuộc exact keyword:** Câu hỏi paraphrase ("bao lâu" vs "mấy tiếng") có thể miss trigger. Cải tiến: embedding similarity routing thay keyword matching.
3. **Confidence chưa phân biệt tốt:** Nhiều câu đơn giản cũng ra confidence=1.00, không phân biệt được câu "chắc chắn đúng 100%" vs "đúng với evidence có sẵn". Cải tiến: LLM-as-Judge evaluation.
4. **Single point of failure:** Nếu Anthropic API down, cả pipeline fail. Cần fallback provider tốt hơn.
