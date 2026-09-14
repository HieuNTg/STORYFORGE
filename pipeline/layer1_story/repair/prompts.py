"""The one prompt that replaces up to five separate chapter regenerations.

The whole point of the repair loop lives in `## RÀNG BUỘC BẮT BUỘC`: every
constraint from every detector reaches the model in a single request. The legacy
passes each rewrote the chapter knowing only their own concern, so the payoff
rewrite could shorten a chapter below target and the length expansion could then
drop the payoff it had just inserted.
"""

REPAIR_CHAPTER = """\
{user_story_idea_header}Bạn là biên tập viên văn học. Chương dưới đây đã ĐẠT về cốt truyện nhưng còn {n_issues} lỗi cần sửa.

## LỖI CẦN SỬA (theo thứ tự ưu tiên)
{fixes}

## RÀNG BUỘC BẮT BUỘC — vi phạm bất kỳ ràng buộc nào là hỏng
{constraints}

## CHƯƠNG HIỆN TẠI
{content}

## NHIỆM VỤ
Viết lại TOÀN BỘ chương, sửa hết các lỗi trên **trong một lần**, đồng thời thoả mãn MỌI ràng buộc ở trên cùng lúc.

Giữ nguyên:
- Cốt truyện, thứ tự sự kiện, và kết chương
- Nhân vật và quan hệ giữa họ
- Tên riêng / địa danh / gimmick từ [Ý TƯỞNG GỐC] nếu có ở đầu prompt — không Việt hoá, không dịch, không thay thế

TUYỆT ĐỐI KHÔNG:
- Không thêm sự kiện mới làm lệch cốt truyện
- Không lặp lại ý đã viết bằng cách diễn đạt khác để kéo dài
- Không thêm lời dẫn/meta ("Dưới đây là...", "Phiên bản đã sửa...")
- Không sửa lỗi này bằng cách phá ràng buộc kia — nếu thấy mâu thuẫn, ưu tiên ràng buộc ở trên cùng

Chỉ trả về văn xuôi của chương đã sửa, viết hoàn toàn bằng tiếng Việt.
"""

REPAIR_SYSTEM = (
    "Bạn là biên tập viên văn học. Chỉ trả về văn xuôi của chương đã sửa, "
    "không thêm bất kỳ lời dẫn hay giải thích nào."
)
