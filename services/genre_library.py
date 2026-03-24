"""Thư viện thể loại truyện Việt Nam với từ vựng và template arc chuyên biệt."""

GENRE_LIBRARY = {
    "tien_hiep": {
        "name": "Tiên Hiệp",
        "description": "Tu tiên, luyện đan, đột phá cảnh giới",
        "vocab": [
            "tu luyện", "đột phá", "cảnh giới", "linh khí", "đan dược",
            "pháp bảo", "tông môn", "trưởng lão", "nội môn", "ngoại môn", "lôi kiếp",
        ],
        "tropes": ["weak-to-strong", "tournament arc", "sect politics", "treasure hunt", "tribulation"],
        "arc_template": [
            "Nhập môn tu luyện", "Tông môn thử thách", "Bí cảnh mạo hiểm",
            "Đại chiến", "Phi thăng",
        ],
        "typical_chapters": 300,
        "words_per_chapter": 3000,
    },
    "huyen_huyen": {
        "name": "Huyền Huyễn",
        "description": "Thế giới huyền ảo, phép thuật, dị năng",
        "vocab": ["đấu khí", "ma pháp", "huyết mạch", "gia tộc", "đại lục", "đế quốc"],
        "tropes": ["bloodline awakening", "academy arc", "kingdom building"],
        "arc_template": ["Thức tỉnh", "Học viện", "Gia tộc", "Đế quốc", "Đỉnh phong"],
        "typical_chapters": 200,
        "words_per_chapter": 3000,
    },
    "do_thi": {
        "name": "Đô Thị",
        "description": "Cuộc sống thành phố, kinh doanh, tình yêu",
        "vocab": ["công ty", "giám đốc", "hợp đồng", "đầu tư", "cổ phiếu"],
        "tropes": ["rags-to-riches", "corporate intrigue", "romantic rivalry"],
        "arc_template": ["Khởi nghiệp", "Thử thách", "Thành công", "Khủng hoảng", "Đỉnh cao"],
        "typical_chapters": 150,
        "words_per_chapter": 2500,
    },
    "kiem_hiep": {
        "name": "Kiếm Hiệp",
        "description": "Giang hồ, võ lâm, kiếm khách",
        "vocab": ["giang hồ", "võ lâm", "kiếm pháp", "nội công", "chưởng môn", "bang phái"],
        "tropes": ["revenge quest", "martial arts tournament", "hidden identity"],
        "arc_template": ["Xuất sơn", "Giang hồ", "Hận thù", "Đại hội", "Minh chủ"],
        "typical_chapters": 200,
        "words_per_chapter": 3000,
    },
    "ngon_tinh": {
        "name": "Ngôn Tình",
        "description": "Tình yêu, lãng mạn, drama",
        "vocab": ["tổng tài", "thiếu gia", "hợp đồng hôn nhân", "tam giác tình yêu"],
        "tropes": ["contract marriage", "CEO romance", "second chance"],
        "arc_template": ["Gặp gỡ", "Hiểu lầm", "Yêu thầm", "Biến cố", "Happy ending"],
        "typical_chapters": 100,
        "words_per_chapter": 2000,
    },
    "cung_dau": {
        "name": "Cung Đấu",
        "description": "Hậu cung tranh đấu, âm mưu hoàng cung",
        "vocab": ["hậu cung", "hoàng hậu", "phi tần", "thái tử", "hoàng đế", "sủng phi"],
        "tropes": ["palace intrigue", "poison plot", "heir competition"],
        "arc_template": ["Nhập cung", "Tranh sủng", "Âm mưu", "Đoạt vị", "Chấp chính"],
        "typical_chapters": 150,
        "words_per_chapter": 2500,
    },
    "xuyen_khong": {
        "name": "Xuyên Không",
        "description": "Du hành thời gian, tái sinh",
        "vocab": ["xuyên việt", "tái sinh", "kiếp trước", "hệ thống", "không gian"],
        "tropes": ["second chance", "system cheat", "butterfly effect"],
        "arc_template": ["Xuyên việt", "Thích nghi", "Thay đổi", "Bí mật lộ", "Kết thúc"],
        "typical_chapters": 200,
        "words_per_chapter": 2500,
    },
    "trong_sinh": {
        "name": "Trọng Sinh",
        "description": "Tái sinh về quá khứ với trí nhớ kiếp trước",
        "vocab": ["kiếp trước", "trọng sinh", "báo thù", "thay đổi vận mệnh"],
        "tropes": ["revenge rebirth", "fix-it", "foreknowledge advantage"],
        "arc_template": ["Trọng sinh", "Bố cục", "Báo thù", "Xây dựng", "Đỉnh phong"],
        "typical_chapters": 200,
        "words_per_chapter": 2500,
    },
}


def get_genre(genre_key: str) -> dict:
    """Lấy template thể loại theo key. Trả về tien_hiep nếu không tìm thấy."""
    return GENRE_LIBRARY.get(genre_key, GENRE_LIBRARY["tien_hiep"])


def get_genre_by_name(name: str) -> dict | None:
    """Tìm thể loại theo tên tiếng Việt."""
    for key, genre in GENRE_LIBRARY.items():
        if genre["name"].lower() == name.lower():
            return genre
    return None


def list_genres() -> list[dict]:
    """Liệt kê tất cả thể loại có sẵn."""
    return [
        {"key": k, "name": v["name"], "description": v["description"]}
        for k, v in GENRE_LIBRARY.items()
    ]
