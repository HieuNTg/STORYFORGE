"use client";

/**
 * /gallery — public-shares gallery.
 *
 * Data: `GET /api/share/gallery` via `useGallery`. Backend doesn't yet expose
 * genre or length on share items, so the nuqs filters operate over whatever
 * fields are present and silently match-all when missing.
 */

import * as React from "react";
import { Images } from "lucide-react";
import { useQueryState } from "nuqs";

import { PageHero } from "@/components/common/PageHero";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { GalleryGrid } from "@/components/gallery/GalleryGrid";
import { GalleryFilters } from "@/components/gallery/GalleryFilters";
import {
  useGallery,
  filterGalleryItems,
  type GalleryItem,
} from "@/lib/api/gallery";

export default function GalleryPage() {
  const [genre, setGenre] = useQueryState("genre", { defaultValue: "" });
  const [length, setLength] = useQueryState("length", { defaultValue: "" });

  const query = useGallery({ pageSize: 24 });

  const allItems: GalleryItem[] = React.useMemo(
    () => (query.data?.pages ?? []).flatMap((p) => p.items),
    [query.data],
  );

  const visible = React.useMemo(
    () => filterGalleryItems(allItems, { genre, length }),
    [allItems, genre, length],
  );

  const genreOptions = React.useMemo(() => {
    const set = new Set<string>();
    for (const it of allItems) if (it.genre) set.add(it.genre);
    return Array.from(set).sort();
  }, [allItems]);

  const openShare = React.useCallback((item: GalleryItem) => {
    if (typeof window === "undefined") return;
    window.open(`/api/share/${item.share_id}`, "_blank", "noopener");
  }, []);

  if (query.isError) {
    return (
      <div className="flex flex-col gap-6">
        <PageHero title="Bộ sưu tập" subtitle="Truyện được chia sẻ công khai" />
        <ErrorState
          title="Không tải được bộ sưu tập"
          description={(query.error as Error)?.message ?? "Lỗi không xác định"}
          onRetry={() => query.refetch()}
        />
      </div>
    );
  }

  const total = query.data?.pages[0]?.total ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        title="Bộ sưu tập"
        subtitle="Truyện được chia sẻ công khai từ cộng đồng"
      />

      <GalleryFilters
        genre={genre}
        length={length}
        onGenreChange={(v) => void setGenre(v || null)}
        onLengthChange={(v) => void setLength(v || null)}
        genreOptions={genreOptions}
        totalLabel={total > 0 ? `${visible.length} / ${total} truyện` : undefined}
      />

      <GalleryGrid
        items={visible}
        isLoading={query.isLoading}
        hasNextPage={query.hasNextPage}
        isFetchingNextPage={query.isFetchingNextPage}
        onLoadMore={() => void query.fetchNextPage()}
        onOpen={openShare}
        emptyState={
          genre || length ? (
            // Filter active — different micro-copy, no default CTA needed.
            <EmptyState
              icon={Images}
              title="Không có truyện khớp bộ lọc"
              description="Thử xoá bộ lọc hoặc chọn thể loại khác."
            />
          ) : (
            // Phase 4 variant — illustration + Vietnamese copy + CTA preset.
            <EmptyState variant="gallery-empty" />
          )
        }
      />
    </div>
  );
}
