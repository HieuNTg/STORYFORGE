# Shim: re-exports from new location for backward compatibility
from services.pipeline.self_review import SelfReviewer, get_genre_threshold

__all__ = ["SelfReviewer", "get_genre_threshold"]
