"use client";

/**
 * PipelineForm — RHF + zod validated form that kicks off a pipeline run.
 *
 * On submit it persists the validated payload into a parent-supplied callback.
 * The parent (Pipeline page) hands the payload to `usePostStream` to open the
 * actual SSE stream — keeping this component a pure form.
 */

import * as React from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ChevronRight, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useGenres, type CreateStoryRequest } from "@/lib/api/queries";
import { cn } from "@/lib/utils";
import {
  CHAPTER_MIN,
  CHAPTER_MAX,
  getChapterDefault,
  getChapterRange,
  clampSessionToTotal,
} from "@/lib/library/chapter-defaults";

function Label({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("text-sm font-medium text-foreground", className)}
      {...props}
    />
  );
}

const schema = z
  .object({
    idea: z.string().min(10, "Tối thiểu 10 ký tự"),
    genre: z.string().min(1, "Chọn thể loại"),
    style: z.string().min(1, "Chọn phong cách"),
    language: z.string().min(2),
    drama: z.number().min(1).max(10),
    num_chapters: z.number().int().min(CHAPTER_MIN).max(CHAPTER_MAX),
    chapters_this_session: z.number().int().min(1).max(CHAPTER_MAX),
    enable_agents: z.boolean(),
    enable_quality_gate: z.boolean(),
  })
  .refine((v) => v.chapters_this_session <= v.num_chapters, {
    message: "Số chương phiên này không thể lớn hơn tổng số chương",
    path: ["chapters_this_session"],
  });

export type PipelineFormValues = z.infer<typeof schema>;

const DRAMA_TO_LABEL: Record<number, string> = {
  1: "thấp",
  2: "thấp",
  3: "thấp",
  4: "trung bình",
  5: "trung bình",
  6: "trung bình",
  7: "cao",
  8: "cao",
  9: "cao",
  10: "cao",
};

export interface PipelineFormProps {
  /** Called with a backend-ready request when the form passes validation. */
  onSubmit: (req: CreateStoryRequest) => void;
  pending?: boolean;
}

const DEFAULTS: PipelineFormValues = {
  idea: "",
  genre: "Tiên Hiệp",
  style: "Miêu tả chi tiết",
  language: "vi",
  drama: 7,
  num_chapters: getChapterDefault("Tiên Hiệp"),
  chapters_this_session: Math.min(5, getChapterDefault("Tiên Hiệp")),
  enable_agents: true,
  enable_quality_gate: true,
};

export function PipelineForm({
  onSubmit,
  pending = false,
}: PipelineFormProps) {
  const { data: choices } = useGenres();
  // Comics are no longer auto-generated when the pipeline finishes — they are
  // produced on demand, per story, from the Library (POST /api/images/*).
  // The backend now ignores `enable_media`; we send `false` so the pipeline
  // never implies comics are created on finish.

  const form = useForm<PipelineFormValues>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULTS,
  });

  // Genre-aware num_chapters default: when the user picks a new genre we bump
  // num_chapters to that genre's recommended value — but only until the user
  // has manually edited the field. The old value-equality heuristic mistook a
  // user value that happened to equal a genre default for "untouched" and
  // silently overwrote it. We now track an explicit "touched" flag set by the
  // input's own onChange (programmatic setValue never fires it), so a user's
  // deliberate count is never clobbered by a later genre switch.
  const numChaptersTouched = React.useRef(false);
  const watchedGenre = form.watch("genre");
  React.useEffect(() => {
    if (numChaptersTouched.current) return; // user customised — leave it alone
    form.setValue("num_chapters", getChapterDefault(watchedGenre), {
      shouldDirty: false,
      shouldValidate: false,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchedGenre]);

  // Live-clamp "chương phiên này" so it can never exceed the story total. When
  // the user lowers num_chapters below the per-session count, follow it down
  // (mirrors ContinueStoryScreen's maxBatch clamp) instead of only surfacing a
  // validation error on submit.
  const watchedNumChapters = form.watch("num_chapters");
  React.useEffect(() => {
    const session = form.getValues("chapters_this_session");
    const clamped = clampSessionToTotal(session, watchedNumChapters);
    if (clamped !== session) {
      form.setValue("chapters_this_session", clamped, { shouldValidate: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchedNumChapters]);

  const submit = form.handleSubmit((values) => {
    const dramaLabel = DRAMA_TO_LABEL[Math.round(values.drama)] ?? "cao";
    const req: CreateStoryRequest = {
      title: "",
      genre: values.genre,
      style: values.style,
      language: values.language,
      idea: values.idea.trim(),
      num_chapters: values.chapters_this_session,
      target_total_chapters: values.num_chapters,
      num_characters: 5,
      word_count: 2000,
      num_sim_rounds: 3,
      drama_level: dramaLabel,
      enable_agents: values.enable_agents,
      enable_quality_gate: values.enable_quality_gate,
      enable_l1_consistency: false,
      enable_emotional_memory: true,
      enable_proactive_constraints: true,
      enable_thread_enforcement: true,
      enable_emotional_bridge: true,
      enable_scene_beat_writing: true,
      enable_l1_causal_graph: true,
      enable_self_review: true,
      enable_agent_debate: values.enable_agents,
      l2_drama_threshold: 0.5,
      l2_drama_target: 0.65,
      quality_gate_threshold: 2.5,
      enable_smart_revision: true,
      smart_revision_threshold: 3.5,
      shots_per_chapter: 8,
      enable_scoring: values.enable_quality_gate,
      enable_media: false,
      lite_mode: false,
    };
    onSubmit(req);
  });

  return (
    <form onSubmit={submit} className="space-y-7">
      <div className="space-y-2">
        <Label htmlFor="idea" className="text-base font-semibold">
          Ý tưởng truyện
        </Label>
        <Textarea
          id="idea"
          rows={5}
          placeholder="Mô tả ý tưởng câu chuyện của bạn..."
          className="min-h-[140px]"
          {...form.register("idea")}
          aria-invalid={!!form.formState.errors.idea}
        />
        {form.formState.errors.idea ? (
          <p className="text-xs text-destructive">{form.formState.errors.idea.message}</p>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="space-y-2">
          <Label>Thể loại</Label>
          <Controller
            control={form.control}
            name="genre"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger aria-label="Thể loại">
                  <SelectValue placeholder="Chọn thể loại" />
                </SelectTrigger>
                <SelectContent>
                  {(choices?.genres ?? []).map((g) => (
                    <SelectItem key={g} value={g}>
                      {g}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>

        <div className="space-y-2">
          <Label>Phong cách</Label>
          <Controller
            control={form.control}
            name="style"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger aria-label="Phong cách">
                  <SelectValue placeholder="Phong cách" />
                </SelectTrigger>
                <SelectContent>
                  {(choices?.styles ?? []).map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>

        <div className="space-y-2">
          <Label>Ngôn ngữ</Label>
          <Controller
            control={form.control}
            name="language"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger aria-label="Ngôn ngữ">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(choices?.languages ?? [
                    { code: "vi", label: "Tiếng Việt" },
                    { code: "en", label: "English" },
                  ]).map((l) => (
                    <SelectItem key={l.code} value={l.code}>
                      {l.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>
      </div>

      <div className="space-y-4 rounded-lg border border-border/40 bg-muted/20 p-4">
        <div className="space-y-2">
          <Label className="text-sm font-medium">Phạm vi chương</Label>
          <div className="flex items-center gap-3">
            <Input
              id="chapters_this_session"
              type="number"
              min={1}
              max={form.watch("num_chapters") || CHAPTER_MAX}
              className="w-24 text-center"
              {...form.register("chapters_this_session", { valueAsNumber: true })}
              aria-invalid={!!form.formState.errors.chapters_this_session}
              aria-label="Số chương phiên này"
            />
            <span className="text-2xl font-light text-muted-foreground" aria-hidden>
              /
            </span>
            <Input
              id="num_chapters"
              type="number"
              min={getChapterRange(watchedGenre).min}
              max={getChapterRange(watchedGenre).max}
              className="w-24 text-center"
              {...form.register("num_chapters", {
                valueAsNumber: true,
                // Mark the field user-touched so a later genre switch never
                // overwrites a count the user deliberately set. Programmatic
                // setValue() does NOT fire this onChange.
                onChange: () => {
                  numChaptersTouched.current = true;
                },
              })}
              aria-label="Tổng số chương"
            />
            <span className="text-xs text-muted-foreground">chương</span>
          </div>
          {form.formState.errors.chapters_this_session ? (
            <p className="text-xs text-destructive">
              {form.formState.errors.chapters_this_session.message}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              Viết {form.watch("chapters_this_session")} chương đầu trong tổng {form.watch("num_chapters")} ·
              Gợi ý cho {watchedGenre}: {getChapterDefault(watchedGenre)} chương
            </p>
          )}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="pipeline-drama" className="text-sm font-medium">
              Mức kịch tính
            </Label>
            <span className="text-xs text-muted-foreground">
              {form.watch("drama")} / 10
            </span>
          </div>
          <Controller
            control={form.control}
            name="drama"
            render={({ field }) => (
              <Slider
                id="pipeline-drama"
                value={[field.value]}
                min={1}
                max={10}
                step={1}
                aria-label="Mức kịch tính (1-10)"
                onValueChange={(v) =>
                  field.onChange(Array.isArray(v) ? v[0] : v)
                }
              />
            )}
          />
        </div>
      </div>

      <details className="group rounded-md border border-border/30 px-3 py-2">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground">
          <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" aria-hidden />
          Tùy chọn nâng cao
        </summary>
        <div className="space-y-2 pt-3">
          <label className="flex items-center justify-between gap-3 rounded-md border border-border/60 bg-card px-3 py-2 text-sm">
            <span>Bật agent thảo luận</span>
            <Controller
              control={form.control}
              name="enable_agents"
              render={({ field }) => (
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              )}
            />
          </label>
          <label className="flex items-center justify-between gap-3 rounded-md border border-border/60 bg-card px-3 py-2 text-sm">
            <span>Quality gate</span>
            <Controller
              control={form.control}
              name="enable_quality_gate"
              render={({ field }) => (
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              )}
            />
          </label>
        </div>
      </details>

      <Button
        type="submit"
        disabled={pending}
        size="lg"
        className="h-12 w-full gap-2 text-base font-semibold shadow-lg shadow-primary/20"
      >
        <Sparkles className="size-4" aria-hidden />
        {pending ? "Đang tạo..." : "Khởi động pipeline"}
      </Button>
    </form>
  );
}
