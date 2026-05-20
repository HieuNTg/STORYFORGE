"use client";

/**
 * LibraryScreen — wires nuqs `?q=&sort=` to LibraryToolbar + useStories.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQueryState } from "nuqs";
import { BookOpen } from "lucide-react";
import { LibraryToolbar, type LibrarySort } from "./LibraryToolbar";
import { LibraryGrid } from "./LibraryGrid";
import { type LibraryStory } from "./StoryCard";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import {
  useStories,
  filterAndSortStories,
  type StorySummary,
} from "@/lib/api/queries";

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

function toLibraryStory(s: StorySummary): LibraryStory {
  return {
    id: s.filename,
    title: s.title || s.filename,
    genre: s.genre || undefined,
    chapter_count: s.chapter_count,
    created_at: s.modified || undefined,
  };
}

export function LibraryScreen() {
  const router = useRouter();
  const [q, setQ] = useQueryState("q", { defaultValue: "" });
  const [sort, setSort] = useQueryState<LibrarySort>("sort", {
    defaultValue: "recent",
    parse: (v) =>
      v === "title" || v === "length" || v === "recent" ? v : "recent",
    serialize: (v) => v,
  });

  const debouncedQ = useDebounced(q, 300);

  const query = useStories({ q: debouncedQ, sort, pageSize: 20 });

  const allItems: StorySummary[] = React.useMemo(
    () => (query.data?.pages ?? []).flatMap((p) => p.items),
    [query.data]
  );

  const visible: LibraryStory[] = React.useMemo(
    () =>
      filterAndSortStories(allItems, { q: debouncedQ, sort }).map(
        toLibraryStory
      ),
    [allItems, debouncedQ, sort]
  );

  const onCardClick = React.useCallback(
    (story: LibraryStory) => {
      router.push(`/library/${encodeURIComponent(story.id)}`);
    },
    [router]
  );

  if (query.isError) {
    return (
      <ErrorState
        title="Không tải được danh sách"
        description={(query.error as Error)?.message ?? "Lỗi không xác định"}
        onRetry={() => query.refetch()}
      />
    );
  }

  return (
    <div className="space-y-4">
      <LibraryToolbar
        q={q}
        onQChange={(v) => void setQ(v)}
        sort={sort}
        onSortChange={(s) => void setSort(s)}
        count={visible.length}
      />
      <LibraryGrid
        stories={visible}
        isLoading={query.isLoading}
        hasNextPage={query.hasNextPage}
        isFetchingNextPage={query.isFetchingNextPage}
        onLoadMore={() => void query.fetchNextPage()}
        onStoryClick={onCardClick}
        emptyState={
          <EmptyState
            icon={BookOpen}
            title={debouncedQ ? "Không tìm thấy truyện" : "Chưa có truyện"}
            description={
              debouncedQ
                ? "Thử từ khoá khác hoặc xoá bộ lọc."
                : "Khởi động pipeline để tạo truyện đầu tiên của bạn."
            }
          />
        }
      />
    </div>
  );
}
