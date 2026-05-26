"use client";

/**
 * CreateStoryModal — 5-field manual story creation.
 *
 * Fields: title / genre (6-enum) / setting / tone (5-enum) / description.
 * Submits to the local library store; never hits the backend.
 */

import * as React from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { genStoryId } from "@/lib/library/ids";
import type { Story } from "@/types/story";
import {
  CHAPTER_MIN,
  CHAPTER_MAX,
  getChapterDefault,
  getChapterRange,
} from "@/lib/library/chapter-defaults";

const GENRES = [
  "Tiên Hiệp",
  "Huyền Huyễn",
  "Đô Thị",
  "Khoa Huyễn",
  "Lịch Sử",
  "Hiện Đại",
] as const;
const TONES = ["dark", "light", "epic", "romantic", "comedic"] as const;

const formSchema = z.object({
  title: z.string().min(1).max(120),
  genre: z.enum(GENRES),
  setting: z.string().max(500),
  tone: z.enum(TONES),
  description: z.string().max(800),
  targetChapters: z.number().int().min(CHAPTER_MIN).max(CHAPTER_MAX),
});
type FormValues = z.infer<typeof formSchema>;

export interface CreateStoryModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (story: Story) => void;
}

export function CreateStoryModal({
  open,
  onOpenChange,
  onCreate,
}: CreateStoryModalProps) {
  const t = useTranslations("library.create_manual_form");
  const tGenres = useTranslations("genres");
  const tTones = useTranslations("tones");

  const localizedSchema = React.useMemo(() => {
    return z.object({
      title: z.string().min(1, t("error_required")).max(120, t("error_max_title")),
      genre: z.enum(GENRES, { message: t("error_select_genre") }),
      setting: z.string().max(500, t("error_max_setting")),
      tone: z.enum(TONES, { message: t("error_select_tone") }),
      description: z.string().max(800, t("error_max_description")),
      targetChapters: z.number().int().min(CHAPTER_MIN).max(CHAPTER_MAX),
    });
  }, [t]);

  const {
    register,
    handleSubmit,
    control,
    reset,
    setValue,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(localizedSchema),
    defaultValues: {
      title: "",
      genre: "Tiên Hiệp",
      setting: "",
      tone: "epic",
      description: "",
      targetChapters: getChapterDefault("Tiên Hiệp"),
    },
  });

  React.useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  // Auto-rebase targetChapters when genre changes, but only if user hasn't
  // manually edited it (heuristic: value matches some known genre default).
  const watchedGenre = watch("genre");
  React.useEffect(() => {
    const knownDefaults = new Set(
      GENRES.map((g) => getChapterDefault(g)),
    );
    knownDefaults.add(getChapterDefault(""));
    setValue("targetChapters", getChapterDefault(watchedGenre), {
      shouldDirty: false,
      shouldValidate: false,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchedGenre]);

  const onSubmit = (values: FormValues) => {
    const now = new Date().toISOString();
    const story: Story = {
      id: genStoryId(),
      title: values.title.trim(),
      genre: values.genre,
      setting: values.setting.trim(),
      tone: values.tone,
      description: values.description.trim(),
      coverUrl: null,
      characters: [],
      chapters: [],
      pendingChoices: null,
      language: "vi",
      targetChapters: values.targetChapters,
      createdAt: now,
      updatedAt: now,
    };
    onCreate(story);
    onOpenChange(false);
  };

  const getGenreLabel = (genre: string) => {
    const key = genre.toLowerCase().replace(/\s+/g, "_");
    return tGenres.has(key) ? tGenres(key as any) : genre;
  };

  const getToneLabel = (tone: string) => {
    return tTones.has(tone) ? tTones(tone as any) : tone;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>
            {t("description")}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          <Field label={t("label_title")} error={errors.title?.message}>
            <Input
              {...register("title")}
              placeholder={t("placeholder_title")}
              aria-invalid={!!errors.title || undefined}
              autoFocus
            />
          </Field>

          <Field label={t("label_genre")} error={errors.genre?.message}>
            <Controller
              name="genre"
              control={control}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger aria-label={t("label_genre")} aria-invalid={!!errors.genre || undefined}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {GENRES.map((g) => (
                      <SelectItem key={g} value={g}>
                        {getGenreLabel(g)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Field>

          <Field label={t("label_tone")} error={errors.tone?.message}>
            <Controller
              name="tone"
              control={control}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger aria-label={t("label_tone")} aria-invalid={!!errors.tone || undefined}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TONES.map((toneVal) => (
                      <SelectItem key={toneVal} value={toneVal}>
                        {getToneLabel(toneVal)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Field>

          <Field label={t("label_setting")} error={errors.setting?.message}>
            <Textarea
              {...register("setting")}
              rows={2}
              placeholder={t("placeholder_setting")}
              aria-invalid={!!errors.setting || undefined}
            />
          </Field>

          <Field label={t("label_description")} error={errors.description?.message}>
            <Textarea
              {...register("description")}
              rows={3}
              placeholder={t("placeholder_description")}
              aria-invalid={!!errors.description || undefined}
            />
          </Field>

          <Field
            label={t("label_target_chapters")}
            error={errors.targetChapters?.message}
          >
            <Input
              type="number"
              min={getChapterRange(watchedGenre).min}
              max={getChapterRange(watchedGenre).max}
              {...register("targetChapters", { valueAsNumber: true })}
              aria-invalid={!!errors.targetChapters || undefined}
            />
            <span className="block pt-1 text-[11px] text-muted-foreground">
              {t("hint_target_chapters", {
                genre: getGenreLabel(watchedGenre),
                default: getChapterDefault(watchedGenre),
                min: CHAPTER_MIN,
              })}
            </span>
          </Field>

          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
              {t("cancel")}
            </DialogClose>
            <Button type="submit" disabled={isSubmitting}>
              {t("submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className={cn("text-xs font-medium", error && "text-destructive")}>
        {label}
      </span>
      {children}
      {error ? (
        <span role="alert" className="block text-xs text-destructive">
          {error}
        </span>
      ) : null}
    </label>
  );
}
