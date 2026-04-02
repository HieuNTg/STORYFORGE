"""Tests for genre library service."""
from services.genre_library import get_genre, get_genre_by_name, list_genres, GENRE_LIBRARY


class TestGetGenre:
    def test_get_known_genre_tien_hiep(self):
        genre = get_genre("tien_hiep")
        assert genre["name"] == "Tiên Hiệp"
        assert "vocab" in genre
        assert "arc_template" in genre

    def test_get_known_genre_ngon_tinh(self):
        genre = get_genre("ngon_tinh")
        assert genre["name"] == "Ngôn Tình"
        assert genre["typical_chapters"] == 100

    def test_get_known_genre_do_thi(self):
        genre = get_genre("do_thi")
        assert genre["name"] == "Đô Thị"

    def test_get_known_genre_kiem_hiep(self):
        genre = get_genre("kiem_hiep")
        assert genre["name"] == "Kiếm Hiệp"

    def test_get_known_genre_xuyen_khong(self):
        genre = get_genre("xuyen_khong")
        assert genre["name"] == "Xuyên Không"

    def test_get_known_genre_trong_sinh(self):
        genre = get_genre("trong_sinh")
        assert genre["name"] == "Trọng Sinh"

    def test_get_known_genre_cung_dau(self):
        genre = get_genre("cung_dau")
        assert genre["name"] == "Cung Đấu"

    def test_get_known_genre_huyen_huyen(self):
        genre = get_genre("huyen_huyen")
        assert genre["name"] == "Huyền Huyễn"

    def test_get_unknown_genre_returns_tien_hiep_default(self):
        genre = get_genre("nonexistent_genre")
        assert genre["name"] == "Tiên Hiệp"

    def test_get_empty_string_returns_default(self):
        genre = get_genre("")
        assert genre["name"] == "Tiên Hiệp"

    def test_tien_hiep_vocab_not_empty(self):
        genre = get_genre("tien_hiep")
        assert len(genre["vocab"]) > 0
        assert "tu luyện" in genre["vocab"]

    def test_tien_hiep_arc_template_has_entries(self):
        genre = get_genre("tien_hiep")
        assert len(genre["arc_template"]) >= 3

    def test_tien_hiep_typical_chapters(self):
        genre = get_genre("tien_hiep")
        assert genre["typical_chapters"] == 300
        assert genre["words_per_chapter"] == 3000

    def test_ngon_tinh_typical_chapters(self):
        genre = get_genre("ngon_tinh")
        assert genre["typical_chapters"] == 100
        assert genre["words_per_chapter"] == 2000

    def test_do_thi_words_per_chapter(self):
        genre = get_genre("do_thi")
        assert genre["words_per_chapter"] == 2500


class TestGetGenreByName:
    def test_found_do_thi(self):
        genre = get_genre_by_name("Đô Thị")
        assert genre is not None
        assert genre["description"] == "Cuộc sống thành phố, kinh doanh, tình yêu"

    def test_found_tien_hiep(self):
        genre = get_genre_by_name("Tiên Hiệp")
        assert genre is not None
        assert genre["typical_chapters"] == 300

    def test_found_kiem_hiep(self):
        genre = get_genre_by_name("Kiếm Hiệp")
        assert genre is not None

    def test_case_insensitive_lowercase(self):
        genre = get_genre_by_name("tiên hiệp")
        assert genre is not None

    def test_case_insensitive_uppercase(self):
        genre = get_genre_by_name("TIÊN HIỆP")
        assert genre is not None

    def test_not_found_returns_none(self):
        result = get_genre_by_name("Unknown Genre")
        assert result is None

    def test_empty_string_returns_none(self):
        result = get_genre_by_name("")
        assert result is None

    def test_partial_name_returns_none(self):
        # "Tiên" alone should not match "Tiên Hiệp"
        result = get_genre_by_name("Tiên")
        assert result is None


class TestListGenres:
    def test_returns_all_genres(self):
        genres = list_genres()
        assert len(genres) == len(GENRE_LIBRARY)

    def test_each_entry_has_key(self):
        genres = list_genres()
        assert all("key" in g for g in genres)

    def test_each_entry_has_name(self):
        genres = list_genres()
        assert all("name" in g for g in genres)

    def test_each_entry_has_description(self):
        genres = list_genres()
        assert all("description" in g for g in genres)

    def test_keys_match_genre_library(self):
        genres = list_genres()
        keys = {g["key"] for g in genres}
        assert keys == set(GENRE_LIBRARY.keys())

    def test_tien_hiep_in_list(self):
        genres = list_genres()
        names = [g["name"] for g in genres]
        assert "Tiên Hiệp" in names


class TestGenreLibraryStructure:
    def test_all_genres_have_required_fields(self):
        required = {
            "name", "description", "vocab", "tropes",
            "arc_template", "typical_chapters", "words_per_chapter",
        }
        for key, genre in GENRE_LIBRARY.items():
            missing = required - set(genre.keys())
            assert not missing, f"Genre '{key}' missing fields: {missing}"

    def test_all_typical_chapters_positive(self):
        for key, genre in GENRE_LIBRARY.items():
            assert genre["typical_chapters"] > 0, f"Genre '{key}' has non-positive typical_chapters"

    def test_all_words_per_chapter_positive(self):
        for key, genre in GENRE_LIBRARY.items():
            assert genre["words_per_chapter"] > 0, f"Genre '{key}' has non-positive words_per_chapter"

    def test_all_vocab_lists_non_empty(self):
        for key, genre in GENRE_LIBRARY.items():
            assert len(genre["vocab"]) > 0, f"Genre '{key}' has empty vocab"

    def test_all_arc_templates_non_empty(self):
        for key, genre in GENRE_LIBRARY.items():
            assert len(genre["arc_template"]) > 0, f"Genre '{key}' has empty arc_template"
