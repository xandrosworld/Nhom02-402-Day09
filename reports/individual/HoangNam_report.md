# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Hoàng Nam  
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

**Quyết định:** Viết lại hoàn toàn `SYSTEM_PROMPT` cho `synthesis.py` bằng Tiếng Anh, phân tách rõ các quy tắc thành các module nhỏ: `GROUNDING`, `ABSTAIN`, `CITATION`, `EXCEPTIONS FIRST`, `LANGUAGE MATCHING`.

**Lý do:**
Ban đầu, prompt mẫu sử dụng Tiếng Việt và các quy tắc được gom chung chung (VD: "CHỈ trả lời dựa vào context... Trích dẫn nguồn..."). Qua thực nghiệm thực tế, LLM (đặc biệt là các model nhỏ như `gpt-4o-mini`) đôi khi bỏ quên mất việc trích dẫn nguồn `[tên_file]`, hoặc khi có "POLICY EXCEPTIONS" (ngoại lệ do Policy Worker trả về như Flash Sale) thì model lại ném thông tin này xuống tít dòng cuối cùng, dẫn đến câu trả lời thiếu mạch lạc.
Việc đổi sang Tiếng Anh kết hợp với Instruction rõ ràng giúp LLM bám sát định dạng cấu trúc hơn. Tôi cũng thêm `LANGUAGE MATCHING` để model động ứng biến ngôn ngữ trả lời dựa vào ngôn ngữ câu hỏi của user (Hỏi tiếng Việt đáp Tiếng Việt).

**Trade-off đã chấp nhận:**
Prompt dài hơn một chút, tiêu tốn thêm một lượng nhỏ token khi gọi API API Claude/OpenAI, đổi lại tính ổn định của đầu ra (final_answer) tăng lên đáng kể.

**Bằng chứng từ trace/code:**
Sau khi tune prompt, file trace (`run_20260414_151652.json`) đã hiển thị câu trả lời xuất sắc cho câu hỏi về hoàn tiền Flash Sale:

```json
  "final_answer": "## ⚠️ Ngoại Lệ Chính Sách (Cần Lưu Ý Trước)\n\n> **Đơn hàng Flash Sale KHÔNG được hoàn tiền** theo Điều 3, chính sách v4 [policy/refund-v4.pdf].\n\n---\n\n## Trả Lời: Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — **KHÔNG được**.\n...",
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

_Trích Trace sau khi sửa (`run_20260414_151635.json`):_

```json
"final_answer": "## SLA Xử Lý Ticket P1\n\nDưới đây là các mốc thời gian SLA cho ticket P1:\n\n- **Phản hồi ban đầu (First Response):** 15 phút kể từ khi ticket được tạo [sla-p1-2026.pdf]...",
"confidence": 0.62,
```

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**
Tôi đã hoàn tất rất nhanh phần Documentations bao gồm `routing_decisions.md` và `system_architecture.md` (giúp nhóm có cái nhìn trực quan về luồng AgentState cũng như các Quyết định Router). Việc phân bổ và trích xuất đúng Trace Data giúp nhóm củng cố minh chứng cho báo cáo tổng kết. Ngoài ra, việc thiết lập kỹ lại `SYSTEM_PROMPT` đã cứu nguy cho cấu trúc phản hồi tổng cuối cùng, giúp user có được một format trả lời thống nhất, dễ theo dõi.
