# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Đức Hoàng Phúc  
**Vai trò trong nhóm:** Trace & Docs Owner  
**Ngày nộp:** 14/04/2026  
**Độ dài yêu cầu:** 500–800 từ  

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

Trong lab Day 09, tôi phụ trách phần **Trace & Evaluation + Documentation**, tập trung vào việc đo lường và phân tích hiệu năng giữa **single-agent (Day 08)** và **multi-agent (Day 09)**.

**Module/file tôi chịu trách nhiệm:**
- File chính: `eval_trace.py`, `docs/single_vs_multi_comparison.md`
- Functions tôi implement: logging trace từng bước (supervisor → worker → synthesis), tính metric (confidence, abstain rate)

Tôi chịu trách nhiệm đảm bảo hệ thống multi-agent có thể **debug được thông qua trace**, bao gồm các trường như `route_reason`, `worker_output`, và `final_answer`.

**Cách công việc của tôi kết nối với phần của thành viên khác:**

- Nhận output từ **supervisor (routing logic)** và **worker**
- Phân tích lại pipeline để xác định lỗi nằm ở đâu (routing / retrieval / synthesis)
- Cung cấp số liệu cho phần comparison và báo cáo

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**

- File: `eval_trace.py`
- Output trace log khi chạy:

```text
route: retrieval_worker
route_reason: contains keyword 'SLA P1'
confidence: 0.87
```

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

Quyết định: Sử dụng trace-based evaluation thay vì chỉ dựa vào output cuối của hệ thống

Trong Day 08, hệ thống chỉ trả về câu trả lời cuối cùng, không có khả năng quan sát pipeline bên trong. Tôi quyết định bổ sung trace logging trong eval_trace.py để ghi lại từng bước xử lý của multi-agent.

Lý do:

Nếu chỉ nhìn output → không biết lỗi nằm ở đâu
Trace giúp tách pipeline thành:
supervisor (routing)
worker (retrieval/tool)
synthesis (final answer)

Điều này giúp debug nhanh hơn rất nhiều.

Trade-off đã chấp nhận:

Tăng độ phức tạp code (phải maintain thêm trace format)
Tăng latency nhẹ do logging
Nhưng đổi lại: debug time giảm mạnh

Bằng chứng từ trace/code:

query: SLA xử lý ticket P1 là bao lâu?
route: retrieval_worker
route_reason: contains 'SLA' keyword
retrieved_docs: sla-p1-2026.pdf
final_answer: 15 phút + 4 giờ
confidence: 0.87

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

Lỗi: Multi-agent trả lời sai nhưng không rõ lỗi nằm ở đâu

Symptom (pipeline làm gì sai?):

Một số câu trả lời sai nhưng:
không biết do retrieval sai hay synthesis sai
không có log để kiểm tra

Ví dụ:

Answer sai nhưng không có thông tin route hay context

Root cause:

Day 08 không có trace → toàn bộ pipeline là blackbox
eval.py chỉ check output cuối → không debug được

Cách sửa:

Thêm logging vào eval_trace.py
Ghi lại:
route (worker nào được chọn)
route_reason
intermediate output
final answer + confidence

Bằng chứng trước/sau:

Trước:

Q: SLA P1?
A: 6 giờ ❌
→ Không biết sai ở đâu

Sau:

route: retrieval_worker
route_reason: SLA keyword
retrieved: đúng doc
final_answer: 4 giờ ✅

→ Xác định được lỗi nằm ở retrieval trước đó (index cũ)

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

Tôi làm tốt nhất ở điểm nào?

Tôi làm tốt phần phân tích và đo lường hệ thống, đặc biệt là chuyển từ blackbox sang observable system. Việc thêm trace giúp toàn bộ team debug nhanh hơn và hiểu rõ pipeline.

Tôi làm chưa tốt hoặc còn yếu ở điểm nào?

Tôi chưa tối ưu phần latency measurement, hiện tại chưa có số liệu cụ thể cho Day 08 nên một số metric phải để N/A.

Nhóm phụ thuộc vào tôi ở đâu?

Nhóm phụ thuộc vào tôi ở phần:

đo metric
so sánh hệ thống
viết report

Nếu không có phần này → không có bằng chứng để chứng minh multi-agent tốt hơn.

Phần tôi phụ thuộc vào thành viên khác:

Tôi phụ thuộc vào:

supervisor logic (routing đúng)
worker implementation (retrieval chính xác)

Nếu các phần này sai → trace chỉ giúp phát hiện chứ không sửa được.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Tôi sẽ thêm latency tracking cho từng bước trong multi-agent pipeline, vì trace hiện tại chỉ có confidence.

Ví dụ: trace cho thấy routing đúng nhưng chưa biết bottleneck ở đâu. Nếu đo được latency từng bước (supervisor vs worker vs synthesis), tôi có thể tối ưu performance.

Đặc biệt, câu query dạng multi-hop có thể tốn nhiều thời gian hơn → cần số liệu để chứng minh trade-off giữa accuracy và latency.