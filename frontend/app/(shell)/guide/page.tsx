import { PageHero } from "@/components/common/PageHero";
import { GuideContent } from "@/components/guide/GuideContent";

export default function GuidePage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHero
        title="Hướng dẫn"
        subtitle="Cài đặt khoá API, tạo truyện đầu tiên và câu hỏi thường gặp"
      />
      <GuideContent />
    </div>
  );
}
