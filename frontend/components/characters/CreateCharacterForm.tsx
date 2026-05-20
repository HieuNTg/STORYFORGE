"use client";

/**
 * CreateCharacterForm — manual fields + "Generate" CTA that calls
 * `/api/characters/generate` and yields a ForgeCharacter.
 */
import * as React from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslations } from "next-intl";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";
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
import { forgeRoleSchema, type ForgeCharacter, type ForgeRole } from "@/types/story";
import { generateCharacter } from "@/lib/api/characters";

const GENRES = [
  "Tiên Hiệp",
  "Huyền Huyễn",
  "Đô Thị",
  "Khoa Huyễn",
  "Lịch Sử",
  "Hiện Đại",
] as const;

const formSchema = z.object({
  name: z.string().min(1).max(80),
  role: forgeRoleSchema,
  genre: z.string().min(1).max(80),
  extraContext: z.string().max(2000).optional(),
});
type FormValues = z.infer<typeof formSchema>;

export interface CreateCharacterFormProps {
  defaultGenre?: string;
  onCreated: (character: ForgeCharacter) => void;
  className?: string;
}

export function CreateCharacterForm({
  defaultGenre,
  onCreated,
  className,
}: CreateCharacterFormProps) {
  const t = useTranslations("characters");
  const tRoles = useTranslations("roles");
  const [submitting, setSubmitting] = React.useState(false);

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: "",
      role: "protagonist" as ForgeRole,
      genre: defaultGenre && GENRES.includes(defaultGenre as (typeof GENRES)[number])
        ? defaultGenre
        : "Tiên Hiệp",
      extraContext: "",
    },
  });

  const onSubmit = async (values: FormValues) => {
    setSubmitting(true);
    try {
      const character = await generateCharacter({
        name: values.name.trim(),
        role: values.role,
        genre: values.genre,
        extraContext: values.extraContext?.trim() || undefined,
      });
      onCreated(character);
      reset();
      toast.success(character.name);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(t("generation_failed"), { description: msg });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className={cn("space-y-3", className)}>
      <Field label={t("name_label")} error={errors.name?.message}>
        <Input
          {...register("name")}
          placeholder={t("name_placeholder")}
          autoFocus
          disabled={submitting}
          aria-invalid={!!errors.name || undefined}
        />
      </Field>

      <Field label={t("role_label")} error={errors.role?.message}>
        <Controller
          name="role"
          control={control}
          render={({ field }) => (
            <Select
              value={field.value}
              onValueChange={field.onChange}
              disabled={submitting}
            >
              <SelectTrigger aria-label={t("role_label")} aria-invalid={!!errors.role || undefined}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(["protagonist", "antagonist", "rival", "supporting"] as const).map(
                  (r) => (
                    <SelectItem key={r} value={r}>
                      {tRoles(r)}
                    </SelectItem>
                  ),
                )}
              </SelectContent>
            </Select>
          )}
        />
      </Field>

      <Field label={t("genre_label")} error={errors.genre?.message}>
        <Controller
          name="genre"
          control={control}
          render={({ field }) => (
            <Select
              value={field.value}
              onValueChange={field.onChange}
              disabled={submitting}
            >
              <SelectTrigger aria-label={t("genre_label")} aria-invalid={!!errors.genre || undefined}>
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

      <Field label={t("extra_label")} error={errors.extraContext?.message}>
        <Textarea
          {...register("extraContext")}
          rows={3}
          placeholder={t("extra_placeholder")}
          disabled={submitting}
          aria-invalid={!!errors.extraContext || undefined}
        />
      </Field>

      <div className="flex justify-end">
        <Button type="submit" disabled={submitting} className="gap-1.5">
          {submitting ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Sparkles className="size-4" aria-hidden />
          )}
          {submitting ? t("generating") : t("generate")}
        </Button>
      </div>
    </form>
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
