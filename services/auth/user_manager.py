"""Simple user management with JSON file storage."""
import bcrypt
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional
from models.schemas import UserProfile

logger = logging.getLogger(__name__)


class UserManager:
    """User auth, story library, usage tracking — JSON file storage."""

    def __init__(self, storage_path: str = "data/users"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

    def register(self, username: str, password: str) -> UserProfile:
        """Đăng ký user mới. Raise ValueError nếu username đã tồn tại."""
        # Kiểm tra trùng tên
        for fname in os.listdir(self.storage_path):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(self.storage_path, fname), "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("username") == username:
                        raise ValueError(f"Username '{username}' already exists")
                except (json.JSONDecodeError, KeyError):
                    continue

        user_id = str(uuid.uuid4())[:8]
        profile = UserProfile(
            user_id=user_id,
            username=username,
            password_hash=self._hash_password(password),
            created_at=datetime.now().isoformat(),
        )
        self._save_profile(profile)
        # Tạo thư mục truyện riêng
        os.makedirs(os.path.join(self.storage_path, user_id, "stories"), exist_ok=True)
        logger.info(f"User registered: {username} ({user_id})")
        return profile

    def login(self, username: str, password: str) -> Optional[UserProfile]:
        """Xác thực user. Trả None nếu sai."""
        for fname in os.listdir(self.storage_path):
            if fname.endswith(".json"):
                try:
                    path = os.path.join(self.storage_path, fname)
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("username") == username:
                        if self._verify_password(password, data.get("password_hash", "")):
                            return UserProfile(**data)
                except (json.JSONDecodeError, OSError, KeyError, TypeError) as e:
                    logger.debug(f"Login scan error for {fname}: {e}")
                    continue
        return None

    def save_story(self, user_id: str, story_data: dict, title: str) -> str:
        """Lưu truyện vào thư viện user. Trả về story_id."""
        story_id = str(uuid.uuid4())[:8]
        stories_dir = os.path.join(self.storage_path, user_id, "stories")
        os.makedirs(stories_dir, exist_ok=True)
        story_path = os.path.join(stories_dir, f"{story_id}.json")
        meta = {
            "story_id": story_id,
            "title": title,
            "saved_at": datetime.now().isoformat(),
            "data": story_data,
        }
        with open(story_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        # Cập nhật profile
        profile = self._load_profile(user_id)
        if profile:
            profile.story_ids.append(story_id)
            self._save_profile(profile)
        return story_id

    def list_stories(self, user_id: str) -> list[dict]:
        """Liệt kê truyện đã lưu (id, title, ngày)."""
        stories_dir = os.path.join(self.storage_path, user_id, "stories")
        if not os.path.isdir(stories_dir):
            return []
        result = []
        for fname in sorted(os.listdir(stories_dir)):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(stories_dir, fname), "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    result.append({
                        "story_id": meta["story_id"],
                        "title": meta["title"],
                        "saved_at": meta.get("saved_at", ""),
                    })
                except (json.JSONDecodeError, OSError, KeyError) as e:
                    logger.debug(f"Story list error: {e}")
                    continue
        return result

    def delete_story(self, user_id: str, story_id: str) -> bool:
        """Xóa truyện khỏi thư viện."""
        path = os.path.join(self.storage_path, user_id, "stories", f"{story_id}.json")
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def track_usage(self, user_id: str):
        """Tăng bộ đếm sử dụng."""
        profile = self._load_profile(user_id)
        if profile:
            profile.usage_count += 1
            self._save_profile(profile)

    # --- helpers ---

    def _hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verify_password(self, password: str, hash_str: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hash_str.encode('utf-8'))
        except (ValueError, TypeError) as e:
            logger.debug(f"Password verify failed: {e}")
            return False

    def _save_profile(self, profile: UserProfile):
        path = os.path.join(self.storage_path, f"{profile.user_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)

    def _load_profile(self, user_id: str) -> Optional[UserProfile]:
        path = os.path.join(self.storage_path, f"{user_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return UserProfile(**json.load(f))
        except (json.JSONDecodeError, OSError, KeyError, TypeError) as e:
            logger.debug(f"Profile load error: {e}")
            return None
