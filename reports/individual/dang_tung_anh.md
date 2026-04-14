# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Đặng Tùng Anh  
**Vai trò trong nhóm:** Worker Owner  
**Ngày nộp:** 2026-04-14  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

Tôi phụ trách `retrieval_worker` trong hệ multi-agent của Day 09. File chính tôi chịu trách nhiệm là `workers/retrieval.py`, ngoài ra tôi cũng cập nhật worker này trong `contracts/worker_contracts.yaml`. Phần tôi làm là port lại logic retrieval từ Day 08 sang kiến trúc worker-based của Day 09. Cụ thể, tôi không chỉ giữ `retrieve_dense()` mà còn thêm `retrieve_sparse()` bằng BM25, `retrieve_hybrid()` bằng Reciprocal Rank Fusion, và sửa `run(state)` để worker hỗ trợ `dense / sparse / hybrid`, mặc định dùng `hybrid`. Công việc của tôi kết nối trực tiếp với `synthesis_worker` vì toàn bộ `retrieved_chunks`, `retrieved_sources`, và `score` của tôi sẽ được dùng để tạo câu trả lời cuối và tính confidence. Nếu retrieval chưa xong, route `retrieval_worker` gần như không tạo được grounded answer.

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/retrieval.py`
- Functions tôi implement: `_tokenize_for_bm25()`, `_bm25_scores()`, `_normalize_scores_to_unit_interval()`, `retrieve_sparse()`, `retrieve_hybrid()`, và phần điều phối trong `run()`

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Phần của tôi cung cấp evidence cho `synthesis_worker`, đồng thời ảnh hưởng gián tiếp tới `policy_tool_worker` khi worker này dùng `search_kb` để lấy context.

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**

Các commit tôi tạo và đẩy lên nhánh làm việc gồm `1def4a6` và `7bffa6e`; sau đó phần normalize hybrid score được đẩy lên `main` ở commit `3006dc2`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Tôi chọn dùng hybrid retrieval theo hướng `dense + BM25 + RRF` thay vì tiếp tục giữ dense-only như file gốc của Day 09.

**Lý do:**

Khi đọc code ban đầu, tôi thấy `workers/retrieval.py` chỉ có dense retrieval, tức là hệ thống chỉ dựa vào embedding similarity. Cách này ổn cho câu hỏi ngữ nghĩa, nhưng yếu hơn với các query chứa keyword cứng như `ERR-403-AUTH`, `IT-ACCESS`, `Level 3`, hay tên policy cụ thể. Vì vậy tôi sử dụng sparse retrieval bằng BM25 và dùng RRF để gộp 2 ranking thay vì cộng trực tiếp score. Tôi chọn RRF vì dense score và BM25 score không cùng thang đo, nếu cộng raw score sẽ rất khó kiểm soát và dễ gây lệch kết quả. Sau khi triển khai, retrieval worker có thể vừa giữ lợi thế semantic matching của dense, vừa tận dụng keyword matching của BM25.

**Trade-off đã chấp nhận:**

Trade-off chính là latency cao hơn và logic phức tạp hơn dense-only. `retrieve_hybrid()` phải gọi cả `retrieve_dense()` lẫn `retrieve_sparse()`, trong khi `retrieve_sparse()` còn đọc toàn bộ corpus để tính BM25. Tôi chấp nhận đánh đổi này vì mục tiêu lab là multi-agent reasoning có grounding tốt hơn, không phải tối ưu thời gian ở mức production.

**Bằng chứng từ trace/code:**

```python
def retrieve_hybrid(query: str, top_k: int = DEFAULT_TOP_K, dense_weight: float = 0.6, sparse_weight: float = 0.4) -> list:
    dense_results = retrieve_dense(query, top_k=max(top_k * 2, top_k))
    sparse_results = retrieve_sparse(query, top_k=max(top_k * 2, top_k))
```

```text
[retrieval_worker] mode=hybrid retrieved 3 chunks from ['it/access-control-sop.md', 'hr/leave-policy-2026.pdf']
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** Hybrid retrieval trả raw RRF score quá nhỏ, làm confidence của các câu route qua retrieval worker bị méo.

**Symptom (pipeline làm gì sai?):**

Khi nhóm chạy `python eval_trace.py`, nhiều câu route vào `retrieval_worker` ra `conf=0.10` gần như hàng loạt. Nhìn bề ngoài thì giống như retrieval rất yếu, dù thực tế worker vẫn retrieve được đúng nguồn như `support/sla-p1-2026.pdf` hoặc `it/access-control-sop.md`.

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**

Root cause nằm ở `worker logic` và integration giữa retrieval với synthesis. Thuật toán RRF vốn sinh ra score rất nhỏ, chỉ quanh `0.01`. Tuy nhiên các phần sau của pipeline lại đọc `chunk["score"]` theo hướng giống relevance/confidence. Kết quả là retrieval score bị hiểu sai thang đo, khiến confidence cuối bị kéo xuống thấp giả.

**Cách sửa:**

Tôi giữ nguyên RRF để xếp hạng, nhưng chuẩn hóa score đầu ra của hybrid retrieval để hệ thống đọc dễ hơn. Ban đầu tôi map về khoảng `0.5–1.0`, sau đó tiếp tục chỉnh về `[0, 1]` thật sự để bớt optimistic. Ngoài ra tôi bỏ fallback random embedding để tránh trường hợp worker trả kết quả giả nhưng vẫn có format hợp lệ.

**Bằng chứng trước/sau:**
> Dán trace/log/output trước khi sửa và sau khi sửa.

Trước khi sửa, log nhóm ghi nhiều câu retrieval route có `conf=0.10`. Sau khi normalize lại hybrid score và cập nhật logic liên quan, cùng pipeline cho ra các giá trị như `conf=0.95` hoặc `conf=1.00`, đồng thời trong trace các chunk score chuyển từ raw RRF rất nhỏ sang các giá trị dễ diễn giải hơn như `0.59`, `0.55`, `0.51`.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**

Tôi làm tốt nhất ở phần đọc đúng vấn đề kỹ thuật đằng sau symptom. Nếu chỉ nhìn log `conf=0.10`, rất dễ kết luận retrieval tệ, nhưng tôi đi lại từ code của `retrieval.py`, đối chiếu với `synthesis.py`, rồi xác định vấn đề chính là mismatch về thang đo score chứ không chỉ là “retrieve sai”.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Tôi vẫn còn thiên về sửa trong phạm vi worker của mình hơn là đồng bộ toàn pipeline ngay từ đầu. Ví dụ sau khi retrieval worker dùng hybrid, `mcp_server.search_kb()` của hệ vẫn có lúc dùng dense-only, làm chiến lược retrieval giữa các route chưa hoàn toàn thống nhất.

**Nhóm phụ thuộc vào tôi ở đâu?** _(Phần nào của hệ thống bị block nếu tôi chưa xong?)_

Nhóm phụ thuộc vào tôi ở toàn bộ nhánh `retrieval_worker`. Nếu tôi chưa hoàn thành thì các câu hỏi route theo tài liệu nội bộ sẽ chỉ chạy dense-only hoặc trả score khó dùng cho synthesis.

**Phần tôi phụ thuộc vào thành viên khác:** _(Tôi cần gì từ ai để tiếp tục được?)_

Tôi phụ thuộc vào phần `synthesis_worker` và `policy_tool_worker`, vì confidence cuối và quality answer không chỉ do retrieval quyết định. Tôi cũng phụ thuộc vào dữ liệu ChromaDB đã được chuẩn bị đúng collection để test worker thực tế.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Nếu có thêm 2 giờ, tôi sẽ chỉnh tiếp phần calibration của confidence trong `workers/synthesis.py`. Lý do là trace mới cho thấy retrieval score đã bớt méo, nhưng `confidence` cuối vẫn có xu hướng quá cao ở nhiều câu route qua retrieval worker, ví dụ một số câu lên `1.00` dù chunk score chỉ ở mức trung bình. Tôi muốn ràng buộc judge score với strength của evidence để confidence phản ánh retrieval trung thực hơn.

---

