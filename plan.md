# Kế Hoạch Chuyển Đổi từ ReAct sang Plan and Execute

## Tổng Quan

Kế hoạch này mô tả chi tiết việc chuyển đổi chatbot từ kiến trúc ReAct (Reason and Act) hiện tại sang kiến trúc Plan and Execute sử dụng LangGraph. Kiến trúc mới sẽ tách biệt rõ ràng giai đoạn lập kế hoạch và thực thi, giúp chatbot xử lý các yêu cầu phức tạp một cách có cấu trúc hơn.

## Phân Tích Nghiệp Vụ

Chatbot hiện tại là một trợ lý báo giá xây dựng chuyên nghiệp cho công ty DBplus, với các luồng nghiệp vụ chính:

1. **Báo Giá Sơ Bộ:** Cung cấp khoảng giá cho yêu cầu chung.
2. **Báo Giá Chi Tiết:** Dựa trên ngân sách hoặc yêu cầu cụ thể.
3. **So Sánh Giá Thị Trường:** So sánh giá công ty với giá thị trường.
4. **Báo Giá Từ Hình Ảnh:** Phân tích hình ảnh và báo giá cho các hạng mục được nhận diện.
5. **Lưu và Tra cứu Báo giá:** Quản lý các báo giá đã tạo.

## Kế Hoạch Triển Khai

### Bước 1: Cập nhật State (state.py)

1. Mở rộng `State` để hỗ trợ kiến trúc Plan and Execute:
   - Thêm trường `plan` để lưu kế hoạch.
   - Thêm trường `current_step_index` để theo dõi bước hiện tại.
   - Thêm trường `past_steps` để lưu các bước đã thực thi và kết quả.

### Bước 2: Cập nhật Prompts (prompts.py)

1. Giữ nguyên `SYSTEM_PROMPT` hiện tại.
2. Thêm `PLAN_PROMPT` để hướng dẫn LLM tạo kế hoạch.
3. Thêm `EXECUTOR_PROMPT` để hướng dẫn LLM thực thi từng bước.
4. Thêm `RESPONSE_PROMPT` để tổng hợp kết quả thành câu trả lời cuối cùng.
5. Thêm `REPLAN_PROMPT` để xử lý khi cần lập kế hoạch lại.

### Bước 3: Xây dựng Graph mới (graph.py)

1. Định nghĩa các node:
   - `plan_node`: Tạo kế hoạch từ input.
   - `execute_step_node`: Thực thi một bước trong kế hoạch.
   - `response_node`: Tổng hợp kết quả thành câu trả lời cuối cùng.
   - `replan_node`: Tạo kế hoạch mới khi cần.

2. Định nghĩa các edge và điều kiện:
   - Từ `plan_node` đến `execute_step_node` hoặc `response_node`.
   - Từ `execute_step_node` đến `execute_step_node`, `response_node`, hoặc `replan_node`.
   - Từ `replan_node` đến `execute_step_node`.
   - Từ `response_node` đến `END`.

### Bước 4: Cập nhật Các Tích Hợp

1. Đảm bảo xử lý hình ảnh vẫn hoạt động trong kiến trúc mới.
2. Đảm bảo các tool hiện tại vẫn được tích hợp đúng cách.
3. Đảm bảo bộ nhớ và lịch sử trò chuyện được quản lý đúng.

## Chi Tiết Triển Khai

### Bước 1: Cập nhật State (state.py)

```python
# Các thay đổi cần thực hiện trong state.py
```

### Bước 2: Cập nhật Prompts (prompts.py)

```python
# Các thay đổi cần thực hiện trong prompts.py
```

### Bước 3: Xây dựng Graph mới (graph.py)

```python
# Các thay đổi cần thực hiện trong graph.py
```

## Kiểm Tra và Xác Nhận

1. Kiểm tra từng luồng nghiệp vụ để đảm bảo chúng hoạt động như mong đợi.
2. Xác nhận rằng tất cả các tính năng hiện tại vẫn được hỗ trợ.
3. Kiểm tra hiệu suất và độ chính xác của chatbot với kiến trúc mới. 