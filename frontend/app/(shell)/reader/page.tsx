import { ReaderStartScreen } from "@/components/reader/ReaderStartScreen";

export default function ReaderIndexPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-medium text-foreground">Đọc truyện</h1>
        <p className="text-sm text-muted-foreground">Chế độ đọc trang giấy</p>
      </header>
      <ReaderStartScreen />
    </div>
  );
}
