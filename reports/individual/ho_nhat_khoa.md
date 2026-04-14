# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Hồ Nhất Khoa  
**MSSV:** 2A202600412  
**Vai trò trong nhóm:** Worker Owner (Policy Tool Worker) + UI Owner  
**Ngày nộp:** 14/04/2026  

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/policy_tool.py` — implement `analyze_policy()`, `_call_llm_for_policy()`, `run()`
- File phụ: `contracts/worker_contracts.yaml` — cập nhật `actual_implementation` của `policy_tool_worker`
- File UI: `app.py` — toàn bộ Gradio Chat UI với trace panel

**Cụ thể những gì tôi implement:**

Trong `workers/policy_tool.py`, tôi xây dựng **two-pass analysis**: vòng đầu rule-based phát hiện nhanh 3 exception đã biết (Flash Sale, digital product, activated product); vòng hai gọi LLM cho edge case phức tạp hơn. Primary là Anthropic Claude, fallback OpenAI gpt-4o-mini, graceful degradation về rule-only nếu cả hai fail.

Trong `app.py`, tôi xây dựng giao diện Gradio 2 cột: chat trái, trace panel phải với 5 tabs (Routing, Chunks, Policy, MCP Tools, Pipeline Steps) để demo luồng multi-agent.

**Kết nối với phần của thành viên khác:** `policy_result` của tôi được `synthesis_worker` (MTT) đọc để build context. Trace panel đọc trực tiếp `AgentState` từ `graph.py` (Phuc).

**Bằng chứng commit:**
- `57874c7` — PR #1: policy_tool_worker LLM integration (merged main)
- `700d8d3` — PR #2: Gradio Chat UI (merged main)
- `238cde9` — Bug fix: max_tokens + JSON parsing (merged main)

---

## 2. Quyết định kỹ thuật: Two-Pass Analysis thay vì LLM-only

**Quyết định:** Thiết kế `analyze_policy()` theo kiến trúc two-pass (rule-based → LLM) thay vì chỉ dùng LLM hoặc chỉ dùng rule-based.

**Lý do:**

Tôi cân nhắc hai lựa chọn:

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| **LLM-only** | Linh hoạt, xử lý được ngôn ngữ mơ hồ | Tốn token, latency cao, LLM có thể hallucinate policy |
| **Rule-based only** | Nhanh, miễn phí, deterministic | Không bắt được edge case, cứng nhắc với ngôn ngữ tự nhiên |
| **Two-pass (chọn)** | Rule nhanh cho case đã biết, LLM cho edge case | Phức tạp hơn một chút |

Tôi chọn two-pass vì ba exception đã biết (Flash Sale, digital product, activated) xuất hiện rất thường xuyên và có thể detect bằng keyword matching — không cần LLM. LLM chỉ cần thiết khi ngôn ngữ mơ hồ hoặc có exception mới. Kiến trúc này cũng đảm bảo: nếu LLM fail, pipeline vẫn cho kết quả đúng với 3 exception core.

**Trade-off đã chấp nhận:** Mỗi câu policy phải thực hiện 2 bước, nhưng rule-based instant nên overhead không đáng kể. LLM second pass thêm ~1-2 giây latency.

**Bằng chứng từ trace (gq10 — Flash Sale):** `supervisor_route=policy_tool_worker`, `confidence=0.88`, `latency=17419ms`. Rule-based bắt ngay `flash_sale_exception` → LLM xác nhận → synthesis trả lời đúng "KHÔNG được hoàn tiền" với citation `[policy/refund-v4.pdf]`.

---

## 3. Bug tôi đã sửa: JSON truncation trong `_call_llm_for_policy()`

**Lỗi:** Câu q15 test (tương tự gq09 grading) báo lỗi khi chạy `eval_trace.py`:

```
⚠️  [policy_tool] JSON parse failed: Unterminated string starting at: line 20 column 18 (char 960)
Raw: {
  "policy_applies": true,
  "llm_exceptions": [
    {
      "type": "emergency_access_escalation",
      "rule": "On-call IT Admin có thể cấp quyền tạm thời (max 24 giờ) sau khi được Tech Lead phê d
```

**Symptom:** LLM response bị cắt đứt giữa string, JSON không parse được. Pipeline fallback về rule-based only — mất hoàn toàn LLM second pass cho câu phức tạp nhất.

**Root cause:** `max_tokens=512` trong `_call_llm_for_policy()` quá nhỏ. Với câu hỏi multi-hop (P1 + Level 2 access), LLM sinh JSON dài (nhiều exceptions, rule strings tiếng Việt) vượt 512 tokens → bị truncate giữa chừng. Ngoài ra, logic strip markdown fence cũ chỉ xử lý ` ``` ` không tag nhưng không handle ` ```json `.

**Cách sửa** (commit `238cde9`): tăng `max_tokens` từ `512` → `1024` cho cả Anthropic và OpenAI call; thay logic strip markdown fence bằng regex xử lý được cả ` ```json `:

```python
cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
cleaned = re.sub(r"\n?```$", "", cleaned).strip()
```

**Kết quả sau sửa:** Không còn warning `JSON parse failed`. LLM second pass hoạt động đúng cho câu multi-hop.

---

## 4. Tự đánh giá đóng góp

**Tôi làm tốt nhất ở:** Thiết kế graceful degradation cho `policy_tool_worker` — pipeline không bao giờ crash dù LLM fail, Anthropic fail, hay JSON parse fail. Điều này đảm bảo grading run hoàn thành 10/10 câu không có `PIPELINE_ERROR`.

**Tôi làm chưa tốt ở:** Không phát hiện sớm bug `max_tokens=512` trong `synthesis.py` — bug tương tự tồn tại ở đó và gây truncation answer cho gq02, gq09. Nếu review synthesis.py sớm hơn, các câu đó đã được Full marks.

**Nhóm phụ thuộc vào tôi ở:** `policy_result` dict trong AgentState. Nếu tôi không implement đúng cấu trúc `{policy_applies, exceptions_found, explanation}`, synthesis worker của MTT không có data để build policy context block và có thể hallucinate policy rules.

**Tôi phụ thuộc vào thành viên khác:** Cần `retrieved_chunks` được populate trước khi `policy_tool_worker` chạy (do retrieval_worker của AnhDT cung cấp). Nếu ChromaDB chưa được index đúng, LLM second pass của tôi không có context để phân tích.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ tích hợp **query transformation ("expansion")** vào retrieval path cho các câu hỏi policy.

Bằng chứng từ grading: gq01 (`confidence=0.3`) trả lời sai về kênh thông báo — hệ thống nói "không có trong tài liệu" dù gq05 lấy được đúng `Slack #incident-p1` từ cùng file `sla-p1-2026.pdf`. Nguyên nhân: query "ai nhận thông báo đầu tiên" không match tốt với chunk chứa "Slack". Nếu dùng query expansion, LLM sẽ sinh thêm query "kênh thông báo incident P1" → recall tăng → gq01 có thể đạt Full marks thay vì Partial.

---

*File: `reports/individual/Ho_Nhat_Khoa.md`*
