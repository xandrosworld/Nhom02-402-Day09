# Routing Decisions Log — Lab Day 09

**Nhóm:** Nhom02-402  
**Ngày:** 14/04/2026

> **Hướng dẫn:** Ghi lại ít nhất **3 quyết định routing** thực tế từ trace của nhóm.
> Không ghi giả định — phải từ trace thật (`artifacts/traces/`).
>
> Mỗi entry phải có: task đầu vào → worker được chọn → route_reason → kết quả thực tế.

---

## Routing Decision #1

**Task đầu vào:**

> SLA xử lý ticket P1 là bao lâu?

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `default route`  
**MCP tools được gọi:** None  
**Workers called sequence:** ['retrieval_worker', 'synthesis_worker']

**Kết quả thực tế:**

- final_answer (ngắn): Đưa ra các mốc thời gian SLA (15 phút phản hồi, xử lý 4 tiếng) từ tài liệu `[support/sla-p1-2026.pdf]`.
- confidence: 0.62
- Correct routing? Yes

**Nhận xét:** _Routing đúng vì câu hỏi này đơn thuần là tìm kiếm thông tin quy trình chung từ bộ tài liệu IT Helpdesk._

---

## Routing Decision #2

**Task đầu vào:**

> Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keyword`  
**MCP tools được gọi:** `search_kb`  
**Workers called sequence:** ['policy_tool_worker', 'synthesis_worker']

**Kết quả thực tế:**

- final_answer (ngắn): Trả lời là KHÔNG ĐƯỢC vì nằm trong ngoại lệ Flash Sale (Điều 3, chính sách v4).
- confidence: 0.48
- Correct routing? Yes

**Nhận xét:** _Routing đúng vì hệ thống bắt được từ khoá "hoàn tiền/Flash Sale" và route thẳng vào tools để kiểm tra case đặc biệt._

---

## Routing Decision #3

**Task đầu vào:**

> Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp. Quy trình là gì?

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keyword | risk_high flagged`  
**MCP tools được gọi:** `search_kb`, `get_ticket_info`  
**Workers called sequence:** ['policy_tool_worker', 'synthesis_worker']

**Kết quả thực tế:**

- final_answer (ngắn): Nêu rõ các bước escalation khẩn cấp để cấp quyền Level 3 tạm thời dựa trên tài liệu `it/access-control-sop.md`. Cần On-call cấp quyền và Tech Lead duyệt.
- confidence: 0.51
- Correct routing? Yes

**Nhận xét:** _Routing đúng vì từ khóa "cấp quyền level 3" mang mức độ risk cao và được đưa vào block policy tool._

---

## Routing Decision #4 (tuỳ chọn — bonus)

**Task đầu vào:**

> Hệ thống báo mã lỗi lạ ERR-999 không có trong tài liệu.

**Worker được chọn:** `human_review`  
**Route reason:** `unknown error code (ERR-xxx) and no context`

**Nhận xét: Đây là trường hợp routing khó nhất trong lab. Tại sao?**

Trường hợp này yêu cầu hệ thống nhận diện được pattern mã lỗi (ERR-xxx) thông qua Regex hoặc LLM classifier và tự nhận thức được việc "không đủ context" để phân luồng thẳng cho người thật (Human-in-the-loop), thay vì cố gắng tìm kiếm (retrieval) một cách vô ích và giảm nguy cơ ảo giác (hallucination).

---

## Tổng kết

### Routing Distribution

| Worker             | Số câu được route | % tổng |
| ------------------ | ----------------- | ------ |
| retrieval_worker   | 1                 | 33.3%  |
| policy_tool_worker | 2                 | 66.7%  |
| human_review       | 0                 | 0.0%   |

### Routing Accuracy

> Trong số 3 câu test chính của nhóm đã chạy, bao nhiêu câu supervisor route đúng?

- Câu route đúng: 3 / 3
- Câu route sai (đã sửa bằng cách nào?): 0
- Câu trigger HITL: 0

### Lesson Learned về Routing

> Quyết định kỹ thuật quan trọng nhất nhóm đưa ra về routing logic là gì?  
> (VD: dùng keyword matching vs LLM classifier, threshold confidence cho HITL, v.v.)

1. Sử dụng keyword matching ở Supervisor cho phép routing tiết kiệm rất nhiều token và đạt độ trễ siêu thấp (chỉ tốn vài mili-giây) so với gọi LLM classifier (tốn cả giây).
2. Quyết định cắm cờ `risk_high` kết nối vào Policy Worker buộc mọi request nhạy cảm ('hoàn tiền', 'cấp quyền') phải đi qua bước check điều kiện chặt chẽ, ngăn ngừa sai phạm nghiêm trọng.

### Route Reason Quality

> Nhìn lại các `route_reason` trong trace — chúng có đủ thông tin để debug không?  
> Nếu chưa, nhóm sẽ cải tiến format route_reason thế nào?

Các `route_reason` (ví dụ: `task contains policy/access keyword`) đã giải thích được lý do điều hướng tới Block nào. Tuy nhiên để debug chuyên sâu hơn nếu bị dính trùng từ khóa, nhóm dự định lưu chính xác từ khóa nào đã trigger rule. Ví dụ: `{"reason": "matched keyword policy", "triggered_by": "hoàn tiền"}`.
