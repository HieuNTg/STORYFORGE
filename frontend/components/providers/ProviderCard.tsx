"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ProviderRowData, ProviderTestStatus } from "./ProviderRow";
import type { ProviderEditPayload } from "./ProviderTable";

export interface ProviderCardProps {
  data: ProviderRowData;
  onTestConnection: (index: number) => void;
  onToggleEnabled: (index: number, enabled: boolean) => void;
  onEditBaseUrl: (index: number, url: string) => void;
  onEditProfile: (index: number, payload: ProviderEditPayload) => void;
  onDeleteProfile: (index: number) => void;
  isTesting?: boolean;
  testResult?: ProviderTestStatus;
  className?: string;
}

import { useTranslations } from "next-intl";

const statusDot: Record<ProviderTestStatus, string> = {
  idle: "bg-muted-foreground/40",
  pass: "bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.18)]",
  fail: "bg-rose-500 shadow-[0_0_0_3px_rgba(244,63,94,0.18)]",
};

export function ProviderCard({
  data,
  onTestConnection,
  onToggleEnabled,
  onEditBaseUrl,
  onEditProfile,
  onDeleteProfile,
  isTesting = false,
  testResult = "idle",
  className,
}: ProviderCardProps) {
  const t = useTranslations("providers");
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(data.baseUrl ?? "");

  const [editOpen, setEditOpen] = React.useState(false);
  const [editName, setEditName] = React.useState(data.name);
  const [editBaseUrl, setEditBaseUrl] = React.useState(data.baseUrl ?? "");
  const [editModel, setEditModel] = React.useState(data.model ?? "");
  const [editApiKey, setEditApiKey] = React.useState("");

  const [confirmDelete, setConfirmDelete] = React.useState(false);

  const startEdit = React.useCallback(() => {
    setDraft(data.baseUrl ?? "");
    setEditing(true);
  }, [data.baseUrl]);

  const commit = React.useCallback(() => {
    setEditing(false);
    const trimmed = draft.trim();
    if (trimmed !== (data.baseUrl ?? "")) {
      onEditBaseUrl(data.index, trimmed);
    }
  }, [draft, data.baseUrl, data.index, onEditBaseUrl]);

  const cancel = React.useCallback(() => {
    setEditing(false);
    setDraft(data.baseUrl ?? "");
  }, [data.baseUrl]);

  const openEditDialog = React.useCallback(() => {
    setEditName(data.name);
    setEditBaseUrl(data.baseUrl ?? "");
    setEditModel(data.model ?? "");
    setEditApiKey("");
    setEditOpen(true);
  }, [data.name, data.baseUrl, data.model]);

  const submitEdit = React.useCallback(() => {
    onEditProfile(data.index, {
      name: editName.trim(),
      base_url: editBaseUrl.trim(),
      api_key: editApiKey,
      model: editModel.trim(),
      enabled: data.enabled,
    });
    setEditOpen(false);
  }, [
    data.index,
    data.enabled,
    editName,
    editBaseUrl,
    editApiKey,
    editModel,
    onEditProfile,
  ]);

  const confirmDeleteAction = React.useCallback(() => {
    onDeleteProfile(data.index);
    setConfirmDelete(false);
  }, [data.index, onDeleteProfile]);

  const getStatusLabel = (status: ProviderTestStatus) => {
    switch (status) {
      case "idle": return t("idle");
      case "pass": return t("verified");
      case "fail": return t("failed");
      default: return status;
    }
  };

  const urlLabel = typeof window !== "undefined" && document.documentElement.lang === "en" ? "Base URL" : "URL gốc";

  return (
    <article
      className={cn(
        "group flex flex-col gap-3 rounded-xl border border-accent/30 bg-card/50 p-4 transition-all",
        "hover:-translate-y-0.5 hover:border-accent hover:shadow-md",
        className,
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col">
          <h3 className="truncate font-serif text-base text-foreground">
            {data.label ?? data.name}
          </h3>
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <span aria-hidden className={cn("size-2 rounded-full", statusDot[testResult])} />
            {getStatusLabel(testResult)}
          </span>
        </div>
        <Switch
          checked={data.enabled}
          onCheckedChange={(checked) => onToggleEnabled(data.index, checked)}
          aria-label={data.enabled ? t("enabled") : t("disabled")}
        />
      </header>

      <div className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {urlLabel}
        </span>
        {editing ? (
          <Input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commit();
              } else if (e.key === "Escape") {
                e.preventDefault();
                cancel();
              }
            }}
            placeholder="https://api.example.com"
            className="h-8 font-mono text-xs"
          />
        ) : (
          <button
            type="button"
            onClick={startEdit}
            className="truncate rounded-md bg-background/40 px-2 py-1 text-left font-mono text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {data.baseUrl?.trim() ? data.baseUrl : t("set_base_url")}
          </button>
        )}
      </div>

      <footer className="mt-1 flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={openEditDialog}
        >
          {t("edit")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setConfirmDelete(true)}
          className="text-rose-500 hover:bg-rose-500/10 hover:text-rose-500"
        >
          {t("delete")}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isTesting}
          onClick={() => onTestConnection(data.index)}
        >
          {isTesting ? t("testing") : t("test")}
        </Button>
      </footer>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("edit_provider_title")}</DialogTitle>
            <DialogDescription>
              {t("edit_provider_desc")}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">{t("display_name")}</span>
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                placeholder="Google Gemini"
              />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">{urlLabel}</span>
              <Input
                value={editBaseUrl}
                onChange={(e) => setEditBaseUrl(e.target.value)}
                placeholder="https://api.example.com"
                className="font-mono text-xs"
              />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">Model</span>
              <Input
                value={editModel}
                onChange={(e) => setEditModel(e.target.value)}
                placeholder="gemini-2.5-flash"
                className="font-mono text-xs"
              />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">
                {t("api_key_placeholder_desc")}
              </span>
              <Input
                type="password"
                value={editApiKey}
                onChange={(e) => setEditApiKey(e.target.value)}
                placeholder="••••••••"
                className="font-mono text-xs"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditOpen(false)}>
              {t("cancel")}
            </Button>
            <Button
              onClick={submitEdit}
              disabled={!editName.trim() || !editBaseUrl.trim()}
            >
              {t("save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("delete_provider_title")}</DialogTitle>
            <DialogDescription>
              {t("delete_provider_desc", { name: data.label ?? data.name })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              {t("cancel")}
            </Button>
            <Button
              onClick={confirmDeleteAction}
              className="bg-rose-500 text-white hover:bg-rose-600"
            >
              {t("delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </article>
  );
}
