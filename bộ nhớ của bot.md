# BỘ NHỚ CỦA BOT - NHẬT KÝ VÀ QUY TẮC LÀM VIỆC

## I. QUY TẮC HOẠT ĐỘNG
1. **Ghi chép hàng ngày:** Tất cả các cuộc trao đổi và tiến độ công việc trong ngày phải được ghi chú lại vào file "Bộ nhớ của bot" này.
2. **Ghi nhớ lỗi:** Mọi lỗi xảy ra trong quá trình làm việc và trò chuyện nếu được yêu cầu note lại thì phải ghi nhớ tuyệt đối, không lặp lại lỗi hay để người dùng phải nhắc lại lần 2.
3. **Đọc lại bộ nhớ trước mỗi phiên làm việc:** Trước mỗi cuộc trò chuyện/phiên làm việc mới, bot bắt buộc phải đọc lại toàn bộ lịch sử trò chuyện và các ghi chú trong file nhật ký này để đảm bảo không có bất kỳ sai sót nào.

## II. NHẬT KÝ LÀM VIỆC & TIẾN ĐỘ

### Ngày 15/07/2026
- **Khởi tạo dự án:** Bắt đầu dự án xây dựng Bot Trade Future trên Binance theo chiến lược lướt sóng (scalping).
- **Thiết lập quy tắc:** Đã ghi nhận và cam kết tuân thủ 3 quy tắc làm việc cốt lõi do người dùng đề ra.
- **Xác định yêu cầu kỹ thuật (Cập nhật 15/07/2026):** 
  - Ngôn ngữ: Python.
  - Cốt lõi: Tích hợp thuật toán thông minh/AI để tự động phân tích nến và các chỉ số kỹ thuật.
  - Đầu ra: Tự động tính toán điểm vào lệnh (Entry), Chốt lời (TP) và Cắt lỗ (SL) tối ưu có cơ sở thống kê.
  - Tương tác: Gửi tín hiệu (Signal) về Telegram để người dùng tham khảo quyết định, không tự động đặt lệnh để đảm bảo an toàn.
  - **Quyết định thuật toán:** Sử dụng mô hình Thuật toán kết hợp đa chỉ báo. Dùng thư viện `pandas` để tính toán EMA (9, 21, 50), RSI, ATR và các đường Kháng cự/Hỗ trợ để làm cơ sở ra quyết định Entry/TP/SL.
  - **Dữ liệu:** Bắt buộc đồng bộ sóng và thông số nến y chang 100% với sàn Binance Futures bằng cách gọi API trực tiếp từ Binance.
- **Chốt cấu hình giao dịch (Cập nhật 15/07/2026):**
  - Cặp giao dịch: SOLUSDT (Tập trung đánh Solana).
  - Tần suất quét: Quét dữ liệu định kỳ (mỗi 5 phút, tương ứng nến 5m).
  - Môi trường triển khai: Đẩy code lên GitHub và host chạy 24/7 trên Render.
- **Tiến độ hiện tại (Cập nhật 15/07/2026):**
  - Đã code xong toàn bộ logic bộ não (analyzer.py) và cấu hình Telegram.
  - Người dùng đang tiến hành **vào lệnh thử nghiệm thực tế (live test)** dựa trên tín hiệu đầu tiên của bot để đánh giá mức độ chính xác của thuật toán (Entry, TP, SL).
- **Bước tiếp theo:** Chờ phản hồi kết quả lệnh test từ người dùng. Nếu cần thiết sẽ tinh chỉnh lại các thông số EMA, RSI hoặc hệ số nhân ATR. Hỗ trợ người dùng hoàn tất quá trình đưa bot lên Render.

## III. GHI CHÚ LỖI CẦN TRÁNH
1. **Lỗi `{"code":-2008,"msg":"Invalid Api-Key ID."}` trên Binance:** Khi người dùng chưa cấu hình API Key thật (chỉ dùng chuỗi mẫu `dien_api_key_...`), không được truyền thông số `apiKey` và `secret` vào hàm khởi tạo `ccxt.binance()`. Việc truyền API Key ảo sẽ khiến Binance báo lỗi ngay cả khi lấy dữ liệu nến public. Chỉ lấy nến public bằng chế độ không xác thực (không có key) cho đến khi có API thật.
