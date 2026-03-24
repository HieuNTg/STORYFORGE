"""Manage shareable story links with UUID-based HTML exports."""
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, Union
from models.schemas import ShareableStory, StoryDraft, EnhancedStory, Character

logger = logging.getLogger(__name__)


class ShareManager:
    """Manage shareable story links."""

    SHARES_DIR = "data/shares"
    SHARES_INDEX = "data/shares/index.json"

    def __init__(self):
        os.makedirs(self.SHARES_DIR, exist_ok=True)
        self.shares: list[dict] = self._load_index()

    def create_share(
        self,
        story: Union[StoryDraft, EnhancedStory],
        characters: list[Character] = None,
        expires_days: int = 30,
    ) -> ShareableStory:
        """Tạo HTML chia sẻ với ID duy nhất."""
        from services.html_exporter import HTMLExporter

        share_id = str(uuid.uuid4())[:12]
        html_path = os.path.join(self.SHARES_DIR, f"{share_id}.html")
        now = datetime.now()
        expires = now + timedelta(days=expires_days)

        # Export HTML
        try:
            HTMLExporter.export(story, html_path, characters=characters)
        except Exception as e:
            logger.error(f"Share HTML export failed: {e}")
            # Fallback HTML cơ bản
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(f"<html><body><h1>{story.title}</h1></body></html>")

        share = ShareableStory(
            share_id=share_id,
            story_title=story.title,
            created_at=now.isoformat(),
            html_path=html_path,
            expires_at=expires.isoformat(),
        )
        self.shares.append(share.model_dump())
        self._save_index()
        logger.info(f"Share created: {share_id} for '{story.title}'")
        return share

    def get_share(self, share_id: str) -> Optional[str]:
        """Lấy đường dẫn HTML theo share_id. Trả None nếu hết hạn hoặc không tồn tại."""
        for s in self.shares:
            if s["share_id"] == share_id:
                if s.get("expires_at"):
                    try:
                        exp = datetime.fromisoformat(s["expires_at"])
                        if datetime.now() > exp:
                            return None
                    except ValueError:
                        pass
                path = s.get("html_path", "")
                return path if os.path.exists(path) else None
        return None

    def list_shares(self) -> list[ShareableStory]:
        """Liệt kê các share còn hiệu lực."""
        now = datetime.now()
        active = []
        for s in self.shares:
            try:
                exp = datetime.fromisoformat(s.get("expires_at", ""))
                if now <= exp:
                    active.append(ShareableStory(**s))
            except (ValueError, Exception):
                active.append(ShareableStory(**s))
        return active

    def delete_share(self, share_id: str) -> bool:
        """Xóa share và file HTML liên quan."""
        for i, s in enumerate(self.shares):
            if s["share_id"] == share_id:
                path = s.get("html_path", "")
                if path and os.path.exists(path):
                    os.remove(path)
                self.shares.pop(i)
                self._save_index()
                return True
        return False

    # --- helpers ---

    def _load_index(self) -> list[dict]:
        if not os.path.exists(self.SHARES_INDEX):
            return []
        try:
            with open(self.SHARES_INDEX, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_index(self):
        with open(self.SHARES_INDEX, "w", encoding="utf-8") as f:
            json.dump(self.shares, f, ensure_ascii=False, indent=2)
