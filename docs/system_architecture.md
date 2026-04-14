# System Architecture — Lab Day 09

**Nhóm:** ___________  
**Ngày:** ___________  
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

> Mô tả ngắn hệ thống của nhóm: chọn pattern gì, gồm những thành phần nào.

**Pattern đã chọn:** Supervisor-Worker  
**Lý do chọn pattern này (thay vì single agent):**
Phân tách trách nhiệm (Separation of Concerns). Supervisor đảm nhận routing, các worker xử lý domain riêng (retrieval, policy, synthesis). Giúp dễ debug, kiểm thử từng phần độc lập và dễ mở rộng các tính năng mới mà không làm phình to prompt của Single Agent.

---

## 2. Sơ đồ Pipeline

> Vẽ sơ đồ pipeline dưới dạng text, Mermaid diagram, hoặc ASCII art.
> Yêu cầu tối thiểu: thể hiện rõ luồng từ input → supervisor → workers → output.

**Ví dụ (ASCII art):**
```
User Request
     │
     ▼
┌──────────────┐
│  Supervisor  │  ← route_reason, risk_high, needs_tool
└──────┬───────┘
       │
   [route_decision]
       │
  ┌────┴────────────────────┐
  │                         │
  ▼                         ▼
Retrieval Worker     Policy Tool Worker
  (evidence)           (policy check + MCP)
  │                         │
  └─────────┬───────────────┘
            │
            ▼
      Synthesis Worker
        (answer + cite)
            │
            ▼
         Output
```

**Sơ đồ thực tế của nhóm:**

```text
User Request
     │
     ▼
┌──────────────┐
│  Supervisor  │  ← Phân tích từ khóa, risk_high
└──────┬───────┘
       │
   [route_decision]
       │
  ┌────┼────────────────────┐
  │    │                    │
  ▼    ▼                    ▼
Retrieval Worker     Policy Tool Worker      Human Review
  (evidence)        (policy check + MCP)      (manual)
  │    │                    │
  └────┴────────┬───────────┘
                │
                ▼
          Synthesis Worker
            (answer + cite)
                │
                ▼
             Output
```

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | ___________________ |
| **Input** | ___________________ |
| **Output** | supervisor_route, route_reason, risk_high, needs_tool |
| **Routing logic** | ___________________ |
| **HITL condition** | ___________________ |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | ___________________ |
| **Embedding model** | ___________________ |
| **Top-k** | ___________________ |
| **Stateless?** | Yes / No |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | ___________________ |
| **MCP tools gọi** | ___________________ |
| **Exception cases xử lý** | ___________________ |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **LLM model** | claude-sonnet-4-6 (Primary) / gpt-4o-mini (Fallback) |
| **Temperature** | 0 (tăng tính chính xác, tránh hallucination) |
| **Grounding strategy** | CHỈ sử dụng tài liệu TÀI LIỆU THAM KHẢO và POLICY EXCEPTIONS được cung cấp |
| **Abstain condition** | Nếu context rỗng hoặc không có đủ thông tin, từ chối trả lời với strict message |

### MCP Server (`mcp_server.py`)

| Tool | Input | Output |
|------|-------|--------|
| search_kb | query, top_k | chunks, sources |
| get_ticket_info | ticket_id | ticket details |
| check_access_permission | access_level, requester_role | can_grant, approvers |
| ___________________ | ___________________ | ___________________ |

---

## 4. Shared State Schema

> Liệt kê các fields trong AgentState và ý nghĩa của từng field.

| Field | Type | Mô tả | Ai đọc/ghi |
|-------|------|-------|-----------|
| task | str | Câu hỏi đầu vào | supervisor đọc |
| supervisor_route | str | Worker được chọn | supervisor ghi |
| route_reason | str | Lý do route | supervisor ghi |
| retrieved_chunks | list | Evidence từ retrieval | retrieval ghi, synthesis đọc |
| policy_result | dict | Kết quả kiểm tra policy | policy_tool ghi, synthesis đọc |
| mcp_tools_used | list | Tool calls đã thực hiện | policy_tool ghi |
| final_answer | str | Câu trả lời cuối | synthesis ghi |
| confidence | float | Mức tin cậy | synthesis ghi |
| history | list | Lịch sử các bước xử lý | Tất cả node ghi |
| workers_called | list | Các worker đã gọi | Các worker ghi |
| sources | list | Nguồn tài liệu được dùng | synthesis ghi |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------|
| Debug khi sai | Khó — không rõ lỗi ở đâu | Dễ hơn — test từng worker độc lập |
| Thêm capability mới | Phải sửa toàn prompt | Thêm worker/MCP tool riêng |
| Routing visibility | Không có | Có route_reason trong trace |
| ___________________ | ___________________ | ___________________ |

**Nhóm điền thêm quan sát từ thực tế lab:**
Kiến trúc Supervisor-Worker xử lý các luồng công việc rõ ràng hơn, tuy nhiên thời gian phản hồi (latency) cao hơn một chút do yêu cầu đi qua qua nhiều agents. Nó giúp hệ thống giảm rủi ro bị ảo giác (hallucination) đáng kể trong các case đặc biệt như Flash Sale.

---

## 6. Giới hạn và điểm cần cải tiến

> Nhóm mô tả những điểm hạn chế của kiến trúc hiện tại.

1. Độ trễ (latency) khi chạy qua nhiều model có phần tăng so với pipeline Single Agent.
2. Cần cơ chế chấm rate của confidence mạnh hơn thay cho các rule if/else cơ bản hiện tại.
3. Nếu supervisor fail phân loại ở bước đầu, toàn bộ luồng phía sau sẽ tính sai kết quả.
