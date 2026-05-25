"use client";

import * as React from "react";
import type { ReactNode } from "react";
import { Copy, Eye, EyeOff, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export interface ApiKeysFormProps {
  form: ReactNode;
  isSaving?: boolean;
  onSave: () => void;
  canReset?: boolean;
  onReset?: () => void;
  className?: string;
}

/**
 * Presentational shell for the API keys settings tab.
 * Includes a security banner explaining that keys are server-side only.
 */
import { useTranslations } from "next-intl";

export function ApiKeysForm({
  form,
  isSaving = false,
  onSave,
  canReset = false,
  onReset,
  className,
}: ApiKeysFormProps) {
  const t = useTranslations("settings_panel");

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <div
        role="note"
        className="flex items-start gap-2.5 rounded-lg border-l-2 border-accent bg-muted px-3 py-2.5 text-sm text-muted-foreground"
      >
        <Shield className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
        <p className="leading-relaxed">
          {t("form.api.banner")}
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-4 py-2">{form}</CardContent>
      </Card>

      <div className="sticky bottom-0 z-10 -mx-4 flex items-center justify-end gap-2 border-t bg-background/95 px-4 py-3 supports-backdrop-filter:backdrop-blur sm:mx-0 sm:rounded-lg sm:border sm:px-3 sm:py-2">
        {canReset ? (
          <Button
            type="button"
            variant="outline"
            onClick={onReset}
            disabled={isSaving}
          >
            {t("form.reset")}
          </Button>
        ) : null}
        <Button type="button" onClick={onSave} disabled={isSaving}>
          {isSaving ? t("form.saving") : t("form.save")}
        </Button>
      </div>
    </div>
  );
}

export interface MaskedInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  name?: string;
  placeholder?: string;
  error?: string;
  /** Optional callback fired after a successful copy. Caller can show a toast. */
  onCopied?: () => void;
  className?: string;
  /** Auto-generated id; provide for label/error association control. */
  id?: string;
}

/**
 * Password-style API key input with explicit show/hide and copy-to-clipboard.
 * Copy never happens automatically — only on user click.
 */
export function MaskedInput({
  label,
  value,
  onChange,
  name,
  placeholder,
  error,
  onCopied,
  className,
  id,
}: MaskedInputProps) {
  const generatedId = React.useId();
  const inputId = id ?? generatedId;
  const errorId = `${inputId}-error`;
  const [revealed, setRevealed] = React.useState(false);
  const t = useTranslations("settings_panel");

  const handleCopy = React.useCallback(async () => {
    if (!value) return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      }
      onCopied?.();
    } catch {
      // swallow — caller may surface its own feedback via onCopied negative path
    }
  }, [value, onCopied]);

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label
        htmlFor={inputId}
        className="text-sm font-medium text-foreground"
      >
        {label}
      </label>
      <div className="flex items-stretch gap-1.5">
        <Input
          id={inputId}
          name={name}
          type={revealed ? "text" : "password"}
          // Defense against autofill / password-manager save prompts (F11/F8).
          // The value lives in `value` only — never echoed into title/aria/data-*.
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          data-1p-ignore=""
          data-lpignore="true"
          data-form-type="other"
          value={value}
          placeholder={placeholder}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => onChange(event.target.value)}
          className="flex-1 font-mono"
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label={revealed ? t("form.api.hide_key") : t("form.api.show_key")}
          aria-pressed={revealed}
          onClick={() => setRevealed((v) => !v)}
        >
          {revealed ? <EyeOff /> : <Eye />}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label={t("form.api.copy_key")}
          disabled={!value}
          onClick={handleCopy}
        >
          <Copy />
        </Button>
      </div>
      {error ? (
        <p id={errorId} className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
