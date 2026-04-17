"""Genre-based naming convention helpers for story generation."""

CHINESE_STYLE_GENRES = {
    "tiên hiệp", "tien hiep", "tiên hiệp", "kiếm hiệp", "kiem hiep",
    "wuxia", "xianxia", "tu tiên", "tu chân", "huyền huyễn",
    "cổ đại", "co dai", "cung đấu", "cung dau", "võ hiệp",
}

WESTERN_STYLE_GENRES = {
    "fantasy western", "high fantasy", "epic fantasy", "dark fantasy",
    "sci-fi", "science fiction", "khoa học viễn tưởng",
}


def get_naming_style(genre: str) -> str:
    """Return naming style based on genre."""
    genre_lower = genre.lower().strip()
    for kw in CHINESE_STYLE_GENRES:
        if kw in genre_lower:
            return "chinese"
    for kw in WESTERN_STYLE_GENRES:
        if kw in genre_lower:
            return "western"
    return "vietnamese"


def get_naming_instruction(genre: str) -> str:
    """Return naming instruction to inject into prompts."""
    style = get_naming_style(genre)
    if style == "chinese":
        return """
QUY TẮC ĐẶT TÊN (Phong cách Trung Quốc cổ):
- Tên nhân vật: họ + tên theo phong cách Trung Quốc (vd: Lý Mạc Sầu, Trương Vô Kỵ, Tiêu Viêm)
- Tên tông môn/bang phái: [Tên] + phái/môn/cung/các (vd: Thiên Sơn phái, Vô Cực môn, Hàn Băng cung)
- Tên địa danh: phong cách cổ trang (vd: Lạc Dương thành, Thiên Nhai hải các, Vạn Kiếm Sơn)
- Tên công pháp/bí kíp: [Tính chất] + công/quyết/kiếm (vd: Hàn Băng Thần Công, Thiên Long Bát Bộ quyết)
"""
    elif style == "western":
        return """
QUY TẮC ĐẶT TÊN (Phong cách Fantasy phương Tây):
- Tên nhân vật: tên Western (vd: Arthur, Elara, Theron, Morgana)
- Tên vương quốc/thành phố: phong cách Western (vd: Kingdom of Eldoria, Silverhaven, Ironforge)
- Tên guild/tổ chức: [The] + [Tính chất] + [Danh từ] (vd: The Silver Hand, Order of the Phoenix)
"""
    else:
        return """
QUY TẮC ĐẶT TÊN (Phong cách Việt Nam hiện đại):
- Tên nhân vật: họ + tên Việt Nam (vd: Nguyễn Minh Anh, Trần Hải Long, Lê Thu Hà)
- Tên địa danh: địa danh Việt Nam hoặc tên Việt (vd: Hà Nội, Sài Gòn, quán cà phê Sương Mai)
- Tên công ty/tổ chức: phong cách hiện đại (vd: Tập đoàn Thành Công, Công ty Hoa Sen)
"""
