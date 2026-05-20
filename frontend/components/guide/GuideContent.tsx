"use client";

/**
 * GuideContent — Vietnamese-language onboarding + FAQ + doc links.
 *
 * Static content only; no data fetching. All routes resolve at static-export
 * time. Designer is free to restyle but keep semantic structure (h2, ul, a).
 */

import * as React from "react";
import Link from "next/link";
import { ArrowRight, BookOpen, Settings, KeyRound, GitBranch, Download, LifeBuoy } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FaqAccordion, type FaqItem } from "./FaqAccordion";

interface StepCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  href: string;
  cta: string;
}

function StepCard({ icon: Icon, title, description, href, cta }: StepCardProps) {
  return (
    <Card size="sm" className="h-full">
      <CardHeader className="flex flex-row items-center gap-2.5">
        <div className="flex size-9 items-center justify-center rounded-md bg-muted text-foreground">
          <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
        </div>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 pb-4">
        <p className="text-sm text-muted-foreground">{description}</p>
        <Link
          href={href}
          className="inline-flex items-center gap-1 text-sm font-medium text-[var(--accent-strong)] hover:underline"
        >
          {cta}
          <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      </CardContent>
    </Card>
  );
}

const STEPS: StepCardProps[] = [
  {
    icon: KeyRound,
    title: "1. Cấu hình khoá API",
    description:
      "Thêm OpenAI, Anthropic, Google AI hoặc Z.AI. Khoá được lưu trên backend, không bao giờ hiện trong URL.",
    href: "/settings",
    cta: "Mở Cài đặt",
  },
  {
    icon: BookOpen,
    title: "2. Tạo truyện đầu tiên",
    description:
      "Chọn thể loại + phong cách, viết ý tưởng vài câu, đặt số chương rồi bấm Chạy.",
    href: "/",
    cta: "Bắt đầu",
  },
  {
    icon: GitBranch,
    title: "3. Khám phá nhánh truyện",
    description:
      "Cho phép độc giả chọn ngã rẽ trong cốt truyện qua giao diện đồ thị tương tác.",
    href: "/library",
    cta: "Mở Thư viện",
  },
  {
    icon: Download,
    title: "4. Xuất bản PDF/EPUB",
    description: "Xuất truyện sang định dạng đọc được trên Kindle, iPad hoặc in ấn.",
    href: "/export",
    cta: "Mở Xuất bản",
  },
];

const FAQ: FaqItem[] = [
  {
    id: "start",
    question: "Tôi nên bắt đầu từ đâu?",
    answer: (
      <>
        <p>
          Vào{" "}
          <Link href="/settings">Cài đặt</Link> trước, thêm ít nhất một khoá API
          (OpenAI/Anthropic/Google AI). Sau đó quay về trang chính, điền ý tưởng và
          bấm <strong>Chạy pipeline</strong>. Truyện đầu tiên thường mất 1–3 phút
          tuỳ độ dài.
        </p>
      </>
    ),
  },
  {
    id: "keys",
    question: "Khoá API có an toàn không?",
    answer: (
      <>
        <p>
          Khoá lưu trên backend FastAPI (file <code>data/config.json</code>),
          không xuất hiện trong URL hoặc localStorage. Endpoint{" "}
          <code>GET /api/config</code> chỉ trả phần đã che (mask). Bạn có thể
          xoá khoá bất cứ lúc nào ở trang Cài đặt.
        </p>
      </>
    ),
  },
  {
    id: "first-story",
    question: "Tạo truyện đầu tiên thế nào?",
    answer: (
      <>
        <ol className="list-decimal pl-5">
          <li>Vào tab <strong>Pipeline</strong> (trang chủ).</li>
          <li>Chọn thể loại (vd: tiên hiệp, hiện đại, phiêu lưu) và phong cách.</li>
          <li>Viết ý tưởng cốt truyện (2–5 câu là đủ).</li>
          <li>Đặt số chương (5–15 cho lần đầu) và số nhân vật chính.</li>
          <li>
            Bấm <strong>Chạy</strong>. Theo dõi pipeline qua thanh tiến trình bên
            phải. Khi hoàn tất, truyện xuất hiện trong{" "}
            <Link href="/library">Thư viện</Link>.
          </li>
        </ol>
      </>
    ),
  },
  {
    id: "branching",
    question: "Nhánh truyện hoạt động thế nào?",
    answer: (
      <>
        <p>
          Khi mở một truyện trong{" "}
          <Link href="/library">Thư viện</Link>, bạn có thể bật chế độ Phân
          nhánh để cho phép chọn ngã rẽ ở cuối mỗi chương. Mỗi lựa chọn tạo một
          nhánh mới, hiển thị dưới dạng đồ thị. Có thể quay lại nút cha,
          undo/redo và đặt bookmark.
        </p>
      </>
    ),
  },
  {
    id: "exports",
    question: "Xuất bản truyện ra định dạng nào?",
    answer: (
      <>
        <p>
          StoryForge hỗ trợ xuất <strong>PDF</strong> (qua fpdf2) và{" "}
          <strong>EPUB</strong> (qua ebooklib). Vào{" "}
          <Link href="/library">Thư viện</Link>, chọn truyện, rồi bấm{" "}
          <strong>Xuất bản</strong>. File sẽ tải về sau vài giây.
        </p>
      </>
    ),
  },
  {
    id: "providers",
    question: "Tôi nên chọn mô hình LLM nào?",
    answer: (
      <>
        <p>
          Mặc định khuyến nghị <code>gpt-4o-mini</code> hoặc{" "}
          <code>claude-haiku</code> cho Layer 1 (tạo truyện), kết hợp{" "}
          <code>gpt-4o</code> hoặc <code>claude-sonnet</code> cho Layer 2 (làm
          gay cấn). Z.AI là lựa chọn miễn phí có giới hạn quota — phù hợp thử
          nghiệm. Mở{" "}
          <Link href="/providers">Nhà cung cấp</Link> để cấu hình fallback chain.
        </p>
      </>
    ),
  },
  {
    id: "cost",
    question: "Theo dõi chi phí ở đâu?",
    answer: (
      <>
        <p>
          Mở <Link href="/usage">Sử dụng</Link> để xem token + USD tích luỹ theo
          phiên hiện tại của server. Số liệu reset khi backend khởi động lại.
        </p>
      </>
    ),
  },
  {
    id: "troubleshooting",
    question: "Pipeline bị kẹt hoặc lỗi thì sao?",
    answer: (
      <>
        <ul className="list-disc pl-5">
          <li>
            Kiểm tra <Link href="/providers">Nhà cung cấp</Link> — nếu mô hình
            chính bị rate-limit, hệ thống sẽ tự fallback sau vài giây.
          </li>
          <li>
            Mở tab <strong>Console</strong> trong DevTools để xem log SSE chi
            tiết.
          </li>
          <li>
            Nếu lỗi lặp lại, bấm <strong>Thử lại</strong> trên trang lỗi hoặc tải
            lại trình duyệt — TanStack Query cache sẽ tự re-fetch.
          </li>
          <li>
            Báo lỗi tại{" "}
            <a
              href="https://github.com/xnohat/storyforge/issues"
              target="_blank"
              rel="noreferrer noopener"
            >
              GitHub Issues
            </a>{" "}
            kèm log từ DevTools.
          </li>
        </ul>
      </>
    ),
  },
];

const LINKS: Array<{ label: string; href: string; description: string }> = [
  {
    label: "GitHub repository",
    href: "https://github.com/xnohat/storyforge",
    description: "Mã nguồn, issue tracker, changelog.",
  },
  {
    label: "Tài liệu API (FastAPI)",
    href: "/docs",
    description: "Swagger UI cho mọi endpoint backend.",
  },
  {
    label: "CLAUDE.md (kiến trúc)",
    href: "https://github.com/xnohat/storyforge/blob/master/CLAUDE.md",
    description: "Giải thích pipeline 2-layer chi tiết.",
  },
];

export function GuideContent() {
  return (
    // Phase 4 typography discipline: section headings use the H2 scale
    // (text-xl). FAQ answers inherit `prose-guide` via FaqAccordion, so the
    // line-length cap (~70ch) and body rhythm apply automatically inside
    // each accordion panel.
    <div className="flex flex-col gap-10">
      <section aria-labelledby="getting-started" className="flex flex-col gap-4">
        <h2 id="getting-started" className="text-xl font-semibold tracking-tight">
          Bắt đầu nhanh
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s) => (
            <StepCard key={s.title} {...s} />
          ))}
        </div>
      </section>

      <section aria-labelledby="faq" className="flex flex-col gap-4">
        <h2 id="faq" className="text-xl font-semibold tracking-tight">
          Câu hỏi thường gặp
        </h2>
        <FaqAccordion items={FAQ} />
      </section>

      <section aria-labelledby="resources" className="flex flex-col gap-4">
        <h2 id="resources" className="text-xl font-semibold tracking-tight">
          Tài nguyên
        </h2>
        <Card>
          <CardContent className="flex flex-col gap-3 pb-4">
            <ul className="flex flex-col gap-2">
              {LINKS.map((l) => (
                <li key={l.href} className="flex items-start gap-3">
                  <LifeBuoy className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <div className="flex flex-col">
                    <a
                      href={l.href}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-sm font-medium text-foreground hover:underline"
                    >
                      {l.label}
                    </a>
                    <span className="text-xs text-muted-foreground">
                      {l.description}
                    </span>
                  </div>
                </li>
              ))}
              <li className="flex items-start gap-3">
                <Settings className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <div className="flex flex-col">
                  <Link
                    href="/settings"
                    className="text-sm font-medium text-foreground hover:underline"
                  >
                    Mở Cài đặt
                  </Link>
                  <span className="text-xs text-muted-foreground">
                    Cấu hình khoá API, model, flag pipeline.
                  </span>
                </div>
              </li>
            </ul>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
