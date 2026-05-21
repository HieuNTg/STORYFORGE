# Plan: FlowKit Integration (Google Labs Proxy) for StoryForge

Tích hợp tính năng tạo hình ảnh chất lượng cao (Imagen 3) và video ngắn (Google Veo) miễn phí từ Google Labs bằng giải pháp Chrome Extension Proxy (FlowKit) chạy trực tiếp trên môi trường Local. Bản thiết kế này đã được tối ưu hóa ở mức cao nhất để đảm bảo tính đồng nhất, tốc độ sinh ảnh, sự ổn định và trải nghiệm người dùng vượt trội so với phiên bản thô sơ của `KJAudioBook-v1`.

---

## User Review Required

> [!IMPORTANT]
> **Hoạt động cục bộ (Local Only):** Giải pháp này hoạt động bằng cách mượn cookie và session của trình duyệt qua một kết nối WebSocket nội bộ (`127.0.0.1:7860`). Nó chỉ khả thi khi chạy dự án StoryForge ở máy tính cá nhân.
>
> **Rủi ro tài khoản (Account Ban Warning):** Việc gửi tự động quá nhiều request sinh ảnh hoặc video qua tài khoản Google cá nhân có nguy cơ nhỏ bị hệ thống bảo mật của Google Labs quét và khóa tài khoản tạm thời/vĩnh viễn. Chúng tôi đề xuất bạn nên sử dụng tài khoản Google phụ (clone) để thực hiện thử nghiệm này.
>
> **Cài đặt thủ công:** Bạn bắt buộc phải cài đặt thủ công thư mục Chrome Extension (`flowkit_extension`) vào trình duyệt Chrome (thông qua `chrome://extensions` -> *Developer Mode* -> *Load unpacked*).

---

## Core Optimization Features (Tính năng tối ưu nâng cao)

1. **Khóa cứng Phong cách vẽ (Style Reference Lock):**
   * Cho phép người dùng upload một bức ảnh phong cách vẽ mẫu (Style Reference) từ giao diện Settings.
   * Truyền bức ảnh mẫu này vào tham chiếu API dưới vai trò chuyên biệt `IMAGE_INPUT_TYPE_STYLE` song song với ảnh chân dung nhân vật `IMAGE_INPUT_TYPE_CHARACTER`.
2. **Sinh ảnh/video song song (Concurrent Worker Pool):**
   * WebSocket backend sẽ phân phối đồng thời nhiều yêu cầu sinh ảnh đến Extension.
   * Chrome Extension thực hiện gọi API Google Labs bất tuần tự (asynchronously), giảm thời gian tạo ảnh tổng thể của một câu chuyện từ 10 phút xuống còn 2 phút.
3. **Bộ lọc Prompt chuyên sâu (Gemini Prompt Refiner):**
   * Sử dụng Gemini API của StoryForge dịch và tối ưu hóa tóm tắt phân cảnh thành cấu trúc prompt điện ảnh chuẩn quốc tế:
     `[Góc máy] + [Bố cục/Ánh sáng] + [Chi tiết nhân vật chính xác] + [Phong cách hội họa thống nhất]`
4. **Tải và lưu trữ Local tức thì (Local Downloader):**
   * Ngay sau khi ảnh/video được tạo thành công trên Cloud của Google Labs, backend StoryForge sẽ lập tức tải tệp nhị phân về máy thông qua luồng download an toàn và lưu trữ vĩnh viễn tại thư mục `output/images/{story_slug}_{session_id}/`.
   * Tránh hoàn toàn lỗi liên kết bị hết hạn (URL của Google Labs chỉ tồn tại trong 1 giờ).
5. **Cảnh báo CAPTCHA thông minh trên tab bất kỳ (Active Page CAPTCHA Toast):**
   * Khi gặp captcha block, Extension sẽ tự động chớp đỏ badge và hiển thị một thông báo Toast nhỏ trực tiếp trên Tab trình duyệt bạn đang xem tại thời điểm đó để bạn click giải captcha ngay lập tức mà không cần canh chừng ứng dụng.

---

## Proposed Changes

### Chrome Extension Component

Chứa toàn bộ mã nguồn của Chrome Extension cải tiến.

#### [NEW] [manifest.json](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/flowkit_extension/manifest.json)
* Khai báo Extension Manifest V3, các quyền truy cập `webRequest`, `scripting`, `storage`, `alarms`, `notifications` và các domain của Google Labs.

#### [NEW] [background.js](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/flowkit_extension/background.js)
* Quản lý kết nối WebSocket đến `ws://127.0.0.1:7860/ws/flowkit`.
* Cho phép thực thi API bất đồng bộ song song nhiều request.
* Chớp đỏ badge, phát âm thanh cảnh báo nhẹ và tiêm mã hiển thị Toast thông báo CAPTCHA lên tab đang hoạt động (`activeTab`).
* Duy trì keep-alive tự động ping Google Labs mỗi 10 phút.

#### [NEW] [content.js](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/flowkit_extension/content.js)
* Script nhúng vào trang Google Labs để tương tác reCAPTCHA v3.
* Chứa hàm vẽ giao diện Toast thông báo khi có yêu cầu giải captcha từ các tab ngoài.

#### [NEW] [injected.js](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/flowkit_extension/injected.js)
* Hook trực tiếp vào hàm Google reCAPTCHA gốc trên trang web để xuất token tự động.

#### [NEW] [popup.html](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/flowkit_extension/popup.html) & [popup.js](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/flowkit_extension/popup.js)
* Giao diện nhỏ hiển thị trạng thái kết nối, token, và log tiến trình chạy song song.

---

### Backend API Component

Cung cấp cổng giao tiếp WebSocket và HTTP Callback cho Chrome Extension.

#### [NEW] [flowkit.py](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/api/flowkit.py)
* Router mới cho FastAPI.
* Định nghĩa endpoint WebSocket `/ws/flowkit` để duy trì kết nối với Extension.
* Định nghĩa endpoint POST `/api/ext/callback` để nhận kết quả nhị phân (ảnh/video) trả về từ Extension.
* Gồm loop chạy nền `poll_jobs_loop()` để liên tục kiểm tra tiến trình tạo video không đồng bộ (Google Veo).

#### [MODIFY] [app.py](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/app.py)
* Đăng ký router `flowkit` vào ứng dụng chính của StoryForge.
* Khởi động loop chạy nền `poll_jobs_loop` trong sự kiện khởi chạy (lifespan) của FastAPI.

---

### Backend Service Component

Xử lý logic nghiệp vụ, gọi API và định dạng đầu ra.

#### [NEW] [flow_service.py](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/services/media/flow_service.py)
* Tạo lớp `FlowService` đóng vai trò quản lý hàng đợi công việc (SQLite3 `jobs.db`).
* Tự động tải ảnh/video từ URL GCS Google về thư mục lưu trữ cục bộ theo từng truyện (`output/images/{story_slug}_{session_id}/`).
* Tích hợp bộ tạo prompt chuyên sâu sử dụng Gemini để làm mịn các mô tả cảnh.

#### [MODIFY] [image_generator.py](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/services/media/image_generator.py)
* Hỗ trợ chỉ định thư mục lưu trữ động (`output_dir`) khi khởi tạo `ImageGenerator`.
* Đăng ký thêm `"flowkit"` vào mảng `PROVIDERS`.
* Viết hàm `_generate_flowkit(self, prompt, filename, reference_paths=None)` để giao tiếp với `flow_service`.
* Tách biệt các tham chiếu ảnh mẫu thành `IMAGE_INPUT_TYPE_CHARACTER` và `IMAGE_INPUT_TYPE_STYLE` tương ứng.

#### [MODIFY] [image_provider.py](file:///c:/Users/Admin/OneDrive/Desktop/STORYFORGE/services/media/image_provider.py)
* Chỉnh sửa hàm `is_configured` để trả về `True` nếu WebSocket của FlowKit đang kết nối hoạt động.

---

## Verification Plan

### Automated Tests
* Viết test mock WebSocket trong thư mục `tests/test_flowkit.py` để mô phỏng phản hồi từ Extension và đảm bảo hệ thống chuyển đổi trạng thái chính xác.
* Chạy test bằng lệnh:
  ```bash
  pytest tests/test_flowkit.py -v
  ```

### Manual Verification
1. Chạy app StoryForge local: `python app.py`.
2. Load thư mục `flowkit_extension` vào Chrome.
3. Mở trang `https://labs.google/fx/tools/flow` trên trình duyệt.
4. Kiểm tra popup của extension báo kết nối màu xanh (Connected).
5. Vào Settings của StoryForge Web UI, đổi Image Provider thành `flowkit`.
6. Thực hiện tạo truyện mới và kiểm tra hình ảnh/video được tạo và lưu trong thư mục `output/images/{story_slug}_{session_id}/` (lưu riêng theo từng truyện, tránh lộn xộn).
