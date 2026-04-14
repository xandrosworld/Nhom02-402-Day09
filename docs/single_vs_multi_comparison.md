# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** 2 - E402 
**Ngày:** 14/04/2026

> **Hướng dẫn:** So sánh Day 08 (single-agent RAG) với Day 09 (supervisor-worker).
> Phải có **số liệu thực tế** từ trace — không ghi ước đoán.

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | 0.38 | 0.87 | +0.49 | Trace có confidence từng câu |
| Avg latency (ms) | ~7000–9000 | ~14000–18000 | +7000 | Multi-agent nhiều bước |
| Abstain rate (%) | ~20% | ~10% | -10% | Có câu trả “không đủ thông tin” |
| Multi-hop accuracy | ~60% | ~90% | +30% | Policy + cross-doc tốt hơn |
| Routing visibility | ✗ Không có | ✓ Có route_reason | N/A | Debug dễ hơn |
| Debug time (estimate) | ~20 phút | ~5–7 phút | -13 phút | Có trace rõ ràng |
| Stability (truncate rate) | ~0% | ~40% | -40% | Multi-agent bị truncate |

> **Lưu ý:** Day 08 không có đầy đủ trace chi tiết → một số metric là ước lượng từ behavior.

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | Cao (~90%) | Cao (~90–100%) |
| Latency | Thấp | Cao hơn |
| Observation | Trả lời đúng, nhanh | Trả lời đúng nhưng overkill |

**Kết luận:**  
Multi-agent **không cải thiện đáng kể** cho câu hỏi đơn giản, nhưng làm tăng latency do pipeline phức tạp hơn.

---

### 2.2 Câu hỏi multi-hop (cross-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | ~60% | ~90% |
| Routing visible? | ✗ | ✓ |
| Observation | Dễ miss logic hoặc exception | Xử lý tốt policy + exception |

**Kết luận:**  
Multi-agent **cải thiện rõ rệt** cho multi-hop nhờ:
- tách policy tool
- reasoning có structure
- supervisor routing đúng worker

---

### 2.3 Câu hỏi cần abstain

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | ~0% | ~10% |
| Hallucination cases | Có | Gần như không |
| Observation | Có xu hướng bịa | Biết nói “không đủ thông tin” |

**Kết luận:**  
Multi-agent **giảm hallucination đáng kể**, đây là improvement quan trọng cho production.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow
Khi answer sai → phải đọc toàn bộ RAG pipeline code → tìm lỗi ở retrieval hoặc prompt
Không có trace → không biết sai ở đâu
Thời gian ước tính: ~20 phút

### Day 09 — Debug workflow
Khi answer sai → đọc trace → xem supervisor_route + route_reason
→ Nếu route sai → sửa supervisor
→ Nếu retrieval sai → test retrieval_worker
→ Nếu synthesis sai → test synthesis_worker
Thời gian ước tính: ~5–7 phút


**Câu cụ thể nhóm đã debug:**

- Câu multi-hop (gq09) bị trả lời thiếu phần (2)
- Trace cho thấy synthesis_worker bị truncate do context dài
- Fix bằng cách giảm context → xác định đúng root cause

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa prompt | Thêm worker + route |
| Thêm 1 domain mới | Phải chỉnh toàn hệ thống | Thêm worker riêng |
| Thay đổi retrieval strategy | Sửa pipeline | Sửa retrieval_worker |
| A/B test một phần | Khó | Dễ |

**Nhận xét:**

Multi-agent **linh hoạt và modular hơn nhiều**, phù hợp mở rộng hệ thống lớn.

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 calls | Day 09 calls |
|---------|-------------|-------------|
| Simple query | 1 | 2–3 |
| Complex query | 1 | 3–5 |
| MCP tool call | N/A | 1–2 |

**Nhận xét về cost-benefit:**

- Cost ↑ (nhiều LLM calls hơn)
- Latency ↑ (~2x)
- Nhưng:
  - Accuracy ↑
  - Reasoning ↑
  - Hallucination ↓

👉 Trade-off **đáng giá cho use-case phức tạp**

---

## 6. Kết luận

> **Multi-agent tốt hơn single agent ở điểm nào?**

1. Xử lý tốt **multi-hop và policy reasoning**
2. Giảm **hallucination**, có khả năng **abstain đúng**
3. Debug dễ hơn nhờ **trace và routing visibility**

---

> **Multi-agent kém hơn hoặc không khác biệt ở điểm nào?**

1. Latency cao hơn, cost cao hơn
2. Không cải thiện nhiều với câu hỏi đơn giản
3. Có issue về **token overflow → truncate output**

---

> **Khi nào KHÔNG nên dùng multi-agent?**

- Hệ thống đơn giản (FAQ, lookup)
- Không cần reasoning phức tạp
- Yêu cầu latency thấp

---

> **Nếu tiếp tục phát triển hệ thống này, nhóm sẽ thêm gì?**

- Token control (tránh truncate output)
- Reranking để giảm context
- Retry mechanism khi output bị cắt
- Monitoring + logging tốt hơn