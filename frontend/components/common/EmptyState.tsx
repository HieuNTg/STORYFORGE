import * as React from "react";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// 12 illustration components — one per route. Each is a small composed
// lucide-line-icon scene; consumed via the `variant` prop below.
import PipelineEmpty from "./empty-illustrations/pipeline-empty";
import LibraryEmpty from "./empty-illustrations/library-empty";
import LibraryReaderEmpty from "./empty-illustrations/library-reader-empty";
import BranchingEmpty from "./empty-illustrations/branching-empty";
import AnalyticsEmpty from "./empty-illustrations/analytics-empty";
import SettingsEmpty from "./empty-illustrations/settings-empty";
import ProvidersEmpty from "./empty-illustrations/providers-empty";
import ExportEmpty from "./empty-illustrations/export-empty";
import AccountEmpty from "./empty-illustrations/account-empty";
import GalleryEmpty from "./empty-illustrations/gallery-empty";
import UsageEmpty from "./empty-illustrations/usage-empty";
import GuideEmpty from "./empty-illustrations/guide-empty";

/**
 * EmptyState — Phase 4 primitive used across every route's empty surface.
 *
 * Three usage modes:
 *   1. `variant` — preferred. Wires illustration + Vietnamese copy + default
 *      CTA from the 12-route catalog below. Each variant maps 1:1 to a route.
 *   2. `illustration` — pass any ReactNode (typically a `*Empty` from
 *      `@/components/common/empty-illustrations`). Overrides `variant`'s art.
 *   3. Legacy `icon` — single LucideIcon inside a circular muted backdrop.
 *      Kept for backward compat with screens authored pre-Phase 4.
 *
 * `action` accepts either:
 *   - A `{ label, href? | onClick? }` object that renders a default Button /
 *     Button-as-Link, or
 *   - A custom ReactNode for arbitrary CTA composition.
 *
 * If `variant` is given, its default title/description/action populate any
 * fields not overridden by props. Vietnamese copy throughout.
 */
export interface EmptyStateAction {
  label: string;
  href?: string;
  onClick?: () => void;
}

export type EmptyStateVariant =
  | "pipeline-empty"
  | "library-empty"
  | "reader-empty"
  | "branching-empty"
  | "analytics-empty"
  | "settings-empty"
  | "providers-empty"
  | "export-empty"
  | "account-empty"
  | "gallery-empty"
  | "usage-empty"
  | "guide-empty";

interface VariantPreset {
  illustration: React.ComponentType;
  title: string;
  description?: string;
  action?: EmptyStateAction;
}

/**
 * 12 variants — one per route. Each variant ships a default illustration +
 * 1 short Vietnamese sentence + a single CTA. Order matches the Phase 4 brief.
 */
const VARIANTS: Record<EmptyStateVariant, VariantPreset> = {
  "pipeline-empty": {
    illustration: PipelineEmpty,
    title: "Bạn chưa có câu chuyện nào.",
    description: "Điền ý tưởng và bấm Chạy để tạo truyện đầu tiên.",
    action: { label: "Tạo truyện mới", href: "/" },
  },
  "library-empty": {
    illustration: LibraryEmpty,
    title: "Thư viện đang trống.",
    description: "Tạo truyện xong, mọi tác phẩm sẽ tập trung tại đây.",
    action: { label: "Tạo truyện đầu tiên", href: "/" },
  },
  "reader-empty": {
    illustration: LibraryReaderEmpty,
    title: "Chưa có chương để đọc.",
    description: "Chọn một truyện trong Thư viện hoặc tạo mới để bắt đầu.",
    action: { label: "Mở Thư viện", href: "/library" },
  },
  "branching-empty": {
    illustration: BranchingEmpty,
    title: "Chưa có nhánh nào được mở.",
    description: "Mở một truyện để rẽ nhánh ở cuối mỗi chương.",
    action: { label: "Mở Thư viện", href: "/library" },
  },
  "analytics-empty": {
    illustration: AnalyticsEmpty,
    title: "Chưa có số liệu để phân tích.",
    description: "Chạy pipeline để thu thập dữ liệu chương và độ phức tạp.",
    action: { label: "Mở Pipeline", href: "/" },
  },
  "settings-empty": {
    illustration: SettingsEmpty,
    title: "Bạn đang dùng cấu hình mặc định.",
    description: "Tinh chỉnh model, độ dài hoặc số chương khi cần.",
    action: { label: "Tinh chỉnh ngay", href: "/settings" },
  },
  "providers-empty": {
    illustration: ProvidersEmpty,
    title: "Chưa kết nối nhà cung cấp LLM.",
    description: "Thêm khoá OpenAI, Anthropic, Google AI hoặc Z.AI để bắt đầu.",
    action: { label: "Thêm khoá API", href: "/providers" },
  },
  "export-empty": {
    illustration: ExportEmpty,
    title: "Chưa có file xuất nào.",
    description: "Chọn một truyện rồi xuất sang PDF hoặc EPUB.",
    action: { label: "Mở Thư viện", href: "/library" },
  },
  "account-empty": {
    illustration: AccountEmpty,
    title: "Chưa có thông tin tài khoản.",
    description: "Cập nhật hồ sơ để cá nhân hoá trải nghiệm.",
    action: { label: "Cập nhật hồ sơ", href: "/account" },
  },
  "gallery-empty": {
    illustration: GalleryEmpty,
    title: "Bộ sưu tập đang trống.",
    description: "Truyện công khai từ cộng đồng sẽ xuất hiện tại đây.",
    action: { label: "Tạo truyện của bạn", href: "/" },
  },
  "usage-empty": {
    illustration: UsageEmpty,
    title: "Chưa có lệnh gọi LLM nào.",
    description: "Số liệu token và chi phí sẽ hiện khi pipeline chạy.",
    action: { label: "Chạy pipeline", href: "/" },
  },
  "guide-empty": {
    illustration: GuideEmpty,
    title: "Không tìm thấy hướng dẫn phù hợp.",
    description: "Thử từ khoá khác hoặc xem mục Câu hỏi thường gặp.",
    action: { label: "Xem FAQ", href: "/guide" },
  },
};

export interface EmptyStateProps {
  /** Phase 4 preferred form — picks illustration + copy + CTA from the catalog. */
  variant?: EmptyStateVariant;
  /** Override `variant`'s illustration with custom art. */
  illustration?: React.ReactNode;
  /** Legacy single-icon form. Ignored when `variant` or `illustration` is provided. */
  icon?: LucideIcon;
  /** Overrides variant title when present. */
  title?: string;
  /** Overrides variant description when present. */
  description?: string;
  /** Overrides variant action when present. Pass `null` to suppress. */
  action?: EmptyStateAction | React.ReactNode | null;
  className?: string;
}

import { useTranslations } from "next-intl";

function isActionObject(a: unknown): a is EmptyStateAction {
  return (
    !!a &&
    typeof a === "object" &&
    "label" in (a as Record<string, unknown>) &&
    typeof (a as Record<string, unknown>).label === "string"
  );
}

export function EmptyState({
  variant,
  illustration,
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  const t = useTranslations("empty_state");
  const preset = variant ? VARIANTS[variant] : undefined;

  const resolvedTitle = title ?? (variant ? t(`${variant}.title`) : preset?.title) ?? "";
  const resolvedDescription = description ?? (variant ? t(`${variant}.description`) : preset?.description);

  let presetAction = preset?.action;
  if (variant && presetAction) {
    presetAction = {
      ...presetAction,
      label: t(`${variant}.action_label`),
    };
  }

  // `action === null` is the explicit "suppress" sentinel.
  const resolvedAction: EmptyStateProps["action"] =
    action === null ? null : (action ?? presetAction);

  let illustrationNode: React.ReactNode = illustration;
  if (!illustrationNode && preset) {
    const Illo = preset.illustration;
    illustrationNode = <Illo />;
  }

  let actionNode: React.ReactNode = null;
  if (resolvedAction && isActionObject(resolvedAction)) {
    if (resolvedAction.href) {
      actionNode = (
        <Link
          href={resolvedAction.href}
          className={cn(buttonVariants({ variant: "default" }))}
        >
          {resolvedAction.label}
        </Link>
      );
    } else {
      actionNode = (
        <Button type="button" onClick={resolvedAction.onClick}>
          {resolvedAction.label}
        </Button>
      );
    }
  } else if (resolvedAction) {
    actionNode = resolvedAction as React.ReactNode;
  }

  return (
    <div
      className={cn(
        // Generous line-height + comfortable vertical rhythm for Vietnamese diacritics.
        // `motion-fade-in` is bounded (one-shot); safe to use everywhere.
        "motion-fade-in flex flex-col items-center justify-center gap-4 px-6 py-12 text-center leading-relaxed",
        className,
      )}
    >
      {illustrationNode ? (
        // Illustration owns its own a11y role/label.
        <div className="mb-1">{illustrationNode}</div>
      ) : Icon ? (
        <div
          aria-hidden
          className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground"
        >
          <Icon className="size-6" strokeWidth={1.5} />
        </div>
      ) : null}

      <div className="flex flex-col gap-1.5">
        <h3 className="text-[18px] font-medium leading-snug text-foreground">
          {resolvedTitle}
        </h3>
        {resolvedDescription ? (
          <p className="mx-auto max-w-prose text-sm leading-relaxed text-muted-foreground">
            {resolvedDescription}
          </p>
        ) : null}
      </div>

      {actionNode ? <div className="mt-1">{actionNode}</div> : null}
    </div>
  );
}
