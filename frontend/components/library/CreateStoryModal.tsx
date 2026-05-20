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
import { cn } from "@/lib/utils";
import { genStoryId } from "@/lib/library/ids";
import type { Story } from "@/types/story";

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
  title: z.string().min(1, "Bắt buộc").max(120, "Tối đa 120 ký tự"),
  genre: z.enum(GENRES, { message: "Chọn thể loại" }),
  setting: z.string().max(500, "Tối đa 500 ký tự"),
  tone: z.enum(TONES, { message: "Chọn tông giọng" }),
  description: z.string().max(800, "Tối đa 800 ký tự"),
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
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      title: "",
      genre: "Tiên Hiệp",
      setting: "",
      tone: "epic",
      description: "",
    },
  });

  React.useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

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
      createdAt: now,
      updatedAt: now,
    };
    onCreate(story);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Tạo truyện thủ công</DialogTitle>
          <DialogDescription>
            Khởi tạo khung truyện trống — bạn có thể bổ sung nhân vật và chương sau.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          <Field label="Tiêu đề" error={errors.title?.message}>
            <Input
              {...register("title")}
              placeholder="Ví dụ: Bóng Kiếm Trên Đỉnh Tuyết"
              aria-invalid={!!errors.title || undefined}
              autoFocus
            />
          </Field>

          <Field label="Thể loại" error={errors.genre?.message}>
            <Controller
              name="genre"
              control={control}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger aria-invalid={!!errors.genre || undefined}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {GENRES.map((g) => (
                      <SelectItem key={g} value={g}>
                        {g}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Field>

          <Field label="Tông giọng" error={errors.tone?.message}>
            <Controller
              name="tone"
              control={control}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger aria-invalid={!!errors.tone || undefined}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TONES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Field>

          <Field label="Bối cảnh" error={errors.setting?.message}>
            <Textarea
              {...register("setting")}
              rows={2}
              placeholder="Thời đại, địa lý, thế lực…"
              aria-invalid={!!errors.setting || undefined}
            />
          </Field>

          <Field label="Mô tả tổng quan" error={errors.description?.message}>
            <Textarea
              {...register("description")}
              rows={3}
              placeholder="Câu mở đầu, mâu thuẫn chính, không khí truyện…"
              aria-invalid={!!errors.description || undefined}
            />
          </Field>

          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
              Huỷ
            </DialogClose>
            <Button type="submit" disabled={isSubmitting}>
              Tạo truyện
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
