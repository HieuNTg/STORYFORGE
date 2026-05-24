import { Suspense } from "react";
import { ReaderStartScreen } from "@/components/reader/ReaderStartScreen";

export default function ReaderIndexPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-medium text-foreground">Đọc truyện</h1>
        <p className="text-sm text-muted-foreground">Chế độ đọc trang giấy</p>
      </header>
      <Suspense
        fallback={
          <div className="rounded-lg border border-border/70 bg-card p-5 text-sm text-muted-foreground">
            Đang tải kho truyện…
          </div>
        }
      >
        <ReaderStartScreen />
      </Suspense>
    </div>
  );
}
