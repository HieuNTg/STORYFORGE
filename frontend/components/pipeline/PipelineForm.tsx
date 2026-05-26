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
import { useConfig, useGenres, type CreateStoryRequest } from "@/lib/api/queries";
import { cn } from "@/lib/utils";
import {
  CHAPTER_MIN,
  CHAPTER_MAX,
  getChapterDefault,
  getChapterRange,
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

const schema = z.object({
  idea: z.string().min(10, "Tối thiểu 10 ký tự"),
  genre: z.string().min(1, "Chọn thể loại"),
  style: z.string().min(1, "Chọn phong cách"),
  language: z.string().min(2),
  drama: z.number().min(1).max(10),
  num_chapters: z.number().int().min(CHAPTER_MIN).max(CHAPTER_MAX),
  enable_agents: z.boolean(),
  enable_quality_gate: z.boolean(),
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
  enable_agents: true,
  enable_quality_gate: true,
};

export function PipelineForm({
  onSubmit,
  pending = false,
}: PipelineFormProps) {
  const { data: choices } = useGenres();
  const { data: config } = useConfig();
  // Image step runs only when a provider is configured in Settings.
  // The backend gate is `enable_media && image_provider != "none"`,
  // so we mirror that check here instead of hard-coding `false`.
  const imageProvider = config?.pipeline?.image_provider ?? "none";
  const enableMedia = imageProvider !== "none";

  const form = useForm<PipelineFormValues>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULTS,
  });

  // Genre-aware num_chapters default: when the user picks a new genre we
  // bump num_chapters to that genre's recommended value — but only if they
  // haven't manually edited the field yet. Tracking "manually edited" via
  // RHF's `isDirty` per-field would require touching every controller, so
  // we use a simpler heuristic: only auto-update while num_chapters still
  // matches a known genre default.
  const watchedGenre = form.watch("genre");
  React.useEffect(() => {
    const current = form.getValues("num_chapters");
    // If the current value matches *any* known genre default, the user
    // hasn't customised it — safe to bump to the new genre's default.
    // Otherwise leave their value alone.
    const knownDefaults = new Set([
      getChapterDefault("Tiên Hiệp"),
      getChapterDefault("Huyền Huyễn"),
      getChapterDefault("Kiếm Hiệp"),
      getChapterDefault("Hiện Đại"),
      getChapterDefault("Đô Thị"),
      getChapterDefault("Lịch Sử"),
      getChapterDefault("Khoa Huyễn"),
      getChapterDefault(""),
    ]);
    if (knownDefaults.has(current)) {
      form.setValue("num_chapters", getChapterDefault(watchedGenre), {
        shouldDirty: false,
        shouldValidate: false,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchedGenre]);

  const submit = form.handleSubmit((values) => {
    const dramaLabel = DRAMA_TO_LABEL[Math.round(values.drama)] ?? "cao";
    const req: CreateStoryRequest = {
      title: "",
      genre: values.genre,
      style: values.style,
      language: values.language,
      idea: values.idea.trim(),
      num_chapters: values.num_chapters,
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
      enable_media: enableMedia,
      lite_mode: false,
    };
    onSubmit(req);
  });

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="space-y-2">
        <Label htmlFor="idea">Ý tưởng truyện</Label>
        <Textarea
          id="idea"
          rows={4}
          placeholder="Mô tả ý tưởng câu chuyện của bạn..."
          {...form.register("idea")}
          aria-invalid={!!form.formState.errors.idea}
        />
        {form.formState.errors.idea ? (
          <p className="text-xs text-destructive">{form.formState.errors.idea.message}</p>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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

        <div className="space-y-2">
          <Label htmlFor="num_chapters">
            Tổng số chương
            <span className="ml-1 text-xs font-normal text-muted-foreground">
              (truyện sẽ kết thúc tại chương này)
            </span>
          </Label>
          <Input
            id="num_chapters"
            type="number"
            min={getChapterRange(watchedGenre).min}
            max={getChapterRange(watchedGenre).max}
            {...form.register("num_chapters", { valueAsNumber: true })}
          />
          <p className="text-xs text-muted-foreground">
            Gợi ý cho {watchedGenre}: {getChapterDefault(watchedGenre)} chương ·
            Tối thiểu {CHAPTER_MIN}
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="pipeline-drama">Mức kịch tính</Label>
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

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2.5 text-sm">
          <span>Bật agent thảo luận</span>
          <Controller
            control={form.control}
            name="enable_agents"
            render={({ field }) => (
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            )}
          />
        </label>
        <label className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2.5 text-sm">
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

      <Button type="submit" disabled={pending} className="w-full sm:w-auto">
        {pending ? "Đang tạo..." : "Khởi động pipeline"}
      </Button>
    </form>
  );
}
