"use client";

/**
 * SettingsWizardController — first-run setup flow.
 *
 * Opens automatically when:
 *   1. GET /api/config returns an empty `api_key_masked` (no key configured), AND
 *   2. The user has not explicitly dismissed it (settings-store.wizardDismissed).
 *
 * 3 steps: pick provider → paste API key → confirm.
 *
 * SECURITY: the key the user types lives in this component's React state
 * only — never URL, never persist, never console. It is sent to PUT
 * /api/config on "Hoàn tất" and the local state is cleared afterwards.
 */

import * as React from "react";
import { toast } from "sonner";

import { SettingsWizard, type SettingsWizardStep } from "@/components/settings/SettingsWizard";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useUpdateConfig } from "@/lib/api/queries";
import type { ConfigResponse } from "@/lib/schemas/config";
import { useSettingsStore } from "@/stores/settings-store";

interface ProviderPreset {
  id: string;
  label: string;
  base_url: string;
  model: string;
  placeholder: string;
}

const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: "openai",
    label: "OpenAI",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    placeholder: "sk-...",
  },
  {
    id: "anthropic",
    label: "Anthropic",
    base_url: "https://api.anthropic.com/v1",
    model: "claude-3-5-sonnet-20241022",
    placeholder: "sk-ant-...",
  },
  {
    id: "zai",
    label: "Z.AI (miễn phí)",
    base_url: "https://api.z.ai/v1",
    model: "glm-4-flash",
    placeholder: "z-...",
  },
];

export interface SettingsWizardControllerProps {
  config: ConfigResponse | undefined;
}

export function SettingsWizardController({ config }: SettingsWizardControllerProps) {
  const update = useUpdateConfig();
  const wizardDismissed = useSettingsStore((s) => s.wizardDismissed);
  const dismissWizard = useSettingsStore((s) => s.dismissWizard);

  const hasKey = Boolean(config?.llm.api_key_masked);
  const shouldOpen = !!config && !hasKey && !wizardDismissed;

  const [open, setOpen] = React.useState(shouldOpen);
  const [step, setStep] = React.useState(0);
  const [providerId, setProviderId] = React.useState<string>(PROVIDER_PRESETS[0].id);
  const [apiKey, setApiKey] = React.useState("");
  const [finishing, setFinishing] = React.useState(false);

  // Sync open state once we know the config status.
  React.useEffect(() => {
    setOpen(shouldOpen);
  }, [shouldOpen]);

  const provider = React.useMemo(
    () => PROVIDER_PRESETS.find((p) => p.id === providerId) ?? PROVIDER_PRESETS[0],
    [providerId],
  );

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      // Closing always counts as a dismissal so we don't nag.
      dismissWizard();
      // Clear secret immediately.
      setApiKey("");
    }
    setOpen(next);
  };

  const handleFinish = async () => {
    setFinishing(true);
    try {
      await update.mutateAsync({
        api_key: apiKey,
        base_url: provider.base_url,
        model: provider.model,
      });
      toast.success("Đã lưu khóa API");
      setApiKey("");
      dismissWizard();
      setOpen(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Lưu thất bại";
      toast.error(msg);
    } finally {
      setFinishing(false);
    }
  };

  const steps: SettingsWizardStep[] = [
    {
      id: "provider",
      title: "Chọn nhà cung cấp",
      description: "Bạn có thể đổi sau trong tab Cài đặt > Chung.",
      content: (
        <div className="flex flex-col gap-2">
          <label htmlFor="wiz-provider" className="text-sm font-medium">
            Nhà cung cấp
          </label>
          <Select
            value={providerId}
            onValueChange={(v) => setProviderId(v ?? PROVIDER_PRESETS[0].id)}
          >
            <SelectTrigger id="wiz-provider">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PROVIDER_PRESETS.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Base URL: <span className="font-mono">{provider.base_url}</span>
          </p>
        </div>
      ),
    },
    {
      id: "key",
      title: "Dán API key",
      description: "Khóa được gửi trực tiếp tới máy chủ — không lưu trong URL.",
      content: (
        <div className="flex flex-col gap-2">
          <label htmlFor="wiz-key" className="text-sm font-medium">
            API key
          </label>
          <Input
            id="wiz-key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder={provider.placeholder}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="font-mono"
          />
          <p className="text-xs text-muted-foreground">
            Không sao chép giá trị này từ trình duyệt khác — dán trực tiếp.
          </p>
        </div>
      ),
    },
    {
      id: "confirm",
      title: "Xác nhận",
      description: "Kiểm tra lại trước khi lưu.",
      content: (
        <dl className="flex flex-col gap-2 text-sm">
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Nhà cung cấp</dt>
            <dd className="font-medium">{provider.label}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Mô hình</dt>
            <dd className="font-mono text-xs">{provider.model}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">API key</dt>
            <dd className="font-mono text-xs">
              {apiKey ? `${"•".repeat(Math.min(apiKey.length, 12))}` : "—"}
            </dd>
          </div>
        </dl>
      ),
    },
  ];

  const canNextPerStep = [true, apiKey.trim().length > 0, apiKey.trim().length > 0];
  const canNext = canNextPerStep[step] ?? false;

  return (
    <SettingsWizard
      open={open}
      onOpenChange={handleOpenChange}
      steps={steps}
      currentStep={step}
      onNext={() => setStep((s) => Math.min(s + 1, steps.length - 1))}
      onPrev={() => setStep((s) => Math.max(s - 1, 0))}
      onFinish={handleFinish}
      canNext={canNext}
      isFinishing={finishing}
    />
  );
}
