# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Phạm Lê Hoàng Nam
**MSHV:** 2A202600416
**Vai trò trong nhóm:** Worker Owner (Synthesis) / Trace & Docs Owner  
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

Trong Lab 09 lần này, khối lượng công việc của tôi tập trung vào việc tinh chỉnh (fine-tune) `synthesis_worker` và hoàn thiện các tài liệu thiết kế hệ thống quan trọng của nhóm.

**Module/file tôi chịu trách nhiệm:**

- File chính: `workers/synthesis.py`, `docs/routing_decisions.md`, `docs/system_architecture.md`, `contracts/worker_contracts.yaml`.
- Functions tôi implement: Tôi tập trung cấu hình lại `SYSTEM_PROMPT` bên trong `synthesis.py` để LLM tuân thủ nghiêm ngặt các quy tắc Grounding và Citation.

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Tôi đóng vai trò cấu thành chốt chặn cuối cùng trong graph. Các worker khác (Retrieval do Đặng Tùng Anh phụ trách, Policy do Hồ Nhất Khoa phụ trách) sẽ đổ context (evidence & exceptions) về cho Synthesis Worker. Output của các bạn chính là Input của tôi, và nhiệm vụ của tôi là đảm bảo LLM không bị ảo giác (hallucinate) từ các context đó, đồng thời format câu trả lời sao cho chuẩn xác, có đánh dấu nguồn trước khi trả về cho user.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định 1:** Viết lại hoàn toàn `SYSTEM_PROMPT` cho `synthesis.py` bằng Tiếng Anh, phân tách rõ các quy tắc thành các module nhỏ: `GROUNDING`, `ABSTAIN`, `CITATION`, `EXCEPTIONS FIRST`, `LANGUAGE MATCHING`.  
**Lý do:** Ban đầu, prompt mẫu sử dụng Tiếng Việt và các quy tắc chung chung khiến LLM dễ bị ảo giác (hallucinate) hoặc quên trích dẫn nguồn. Việc đổi sang Tiếng Anh với Instruction dạng module rõ ràng giúp LLM bám sát cấu trúc hơn. `LANGUAGE MATCHING` giúp model xuất ra ngôn ngữ đích xác dựa theo ngữ cảnh hỏi.

**Quyết định 2:** Áp dụng **LLM-as-Judge** trong module đánh giá mức độ tin cậy `_estimate_confidence()`.  
**Lý do:** Phương pháp cũ tính toán confidence dựa vào tính trung bình cộng similarity score (Heuristic) trừ đi exception penalty là một giải pháp khá máy móc và có độ nhiễu cao, vì nội dung văn bản mới là quyết định cuối. Việc dùng chính LLM đóng vai trò làm thẩm định viên (Evaluator) chấm điểm chéo câu trả lời dựa trên context/chunks giảm thiểu tỷ lệ confidence rating sai lệch.

**Trade-off đã chấp nhận:**
Chuyển đổi sang LLM-as-Judge làm tăng số lượng API request và thời gian chạy graph thêm khoảng ~1.5 giây cho mỗi query, tiêu tốn thêm token so với Heuristic. Đổi lại tính chính xác và khả năng đánh giá (calibration) của hệ thống phản ánh đúng thực tế ngữ nghĩa.

**Bằng chứng từ trace/code:**
Sau khi tune prompt và judge, file trace (`run_20260414_154758.json`) đã tính toán confidence bằng LLM chuẩn xác (đạt 0.88) và hiển thị câu trả lời xuất sắc:

```json
  "final_answer": "## ⚠️ Ngoại Lệ Chính Sách (Áp Dụng Ngay)\n\n> **Đơn hàng Flash Sale KHÔNG được hoàn tiền** — theo Điều...\n...",
  "confidence": 0.88
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** LLM liên tục trả về `[SYNTHESIS ERROR] Không thể gọi LLM. Kiểm tra API key trong .env.` cho toàn bộ các query. Đồng thời xảy ra lỗi `ModuleNotFoundError: No module named 'dotenv'` khi chạy codebase.

**Symptom (pipeline làm gì sai?):**
Bất cứ câu hỏi nào đưa qua hệ thống (kể cả SLA P1 hay Flash Sale) đều nhận được output lỗi. Luồng supervisor phân loại đúng, luồng worker cũng tìm ra chunk, tuy nhiên Synthesis Worker bị crash ở bước gọi OpenAI/Anthropic SDK.

**Root cause:**

- Môi trường ảo (`venv`) bị thiếu các thư viện quan trọng: `python-dotenv` để load biến môi trường, `anthropic` và `openai` để khởi tạo HTTP Client giao tiếp với mô hình ngôn ngữ.
- File `.env` chứa API keys bị bỏ trống.

**Cách sửa:**

- Tôi đã trực tiếp cài đặt các module thiếu vào môi trường hiện tại (`pip install anthropic openai python-dotenv`), đồng thời bổ sung hẳn chúng vào `requirements.txt` để các thành viên khác kéo code về không bị lỗi tương tự.
- Gắn OpenAI/Anthropic API Key vào `.env`.

**Bằng chứng trước/sau:**
_Trích Trace trước khi sửa (`run_20260414_145807.json`):_

```json
"final_answer": "[SYNTHESIS ERROR] Không thể gọi LLM. Kiểm tra API key trong .env....",
"confidence": 0.1,
```

_Trích Trace sau khi sửa (`run_20260414_154744.json`):_

```json
"final_answer": "## SLA xử lý ticket P1\n\nDưới đây là các chỉ số SLA cho ticket P1:\n\n- **Phản hồi ban đầu (First Respo...",
"confidence": 1.0,
```

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**
Tôi đã hoàn tất rất nhanh phần Documentations bao gồm `routing_decisions.md` và `system_architecture.md` (giúp nhóm có cái nhìn trực quan về luồng AgentState cũng như các Quyết định Router). Việc phân bổ và trích xuất đúng Trace Data giúp nhóm củng cố minh chứng cho báo cáo tổng kết. Ngoài ra, việc thiết lập kỹ lại `SYSTEM_PROMPT` đã cứu nguy cho cấu trúc phản hồi tổng cuối cùng, giúp user có được một format trả lời thống nhất, dễ theo dõi.
