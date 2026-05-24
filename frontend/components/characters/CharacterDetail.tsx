"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { Loader2, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PortraitPanel } from "./PortraitPanel";
import { TraitRadar } from "./TraitRadar";
import { NarrativePanels } from "./NarrativePanels";
import { RoleBadge } from "./RoleBadge";
import { rebuildCharacterAvatar } from "@/lib/api/illustration";
import type { ForgeCharacter } from "@/types/story";

export interface CharacterDetailProps {
  character: ForgeCharacter;
  genre?: string | null;
  portraitUrl?: string | null;
  /** Backend session id (= local story.id). Required to enable avatar regeneration. */
  sessionId?: string | null;
  /** Called when the avatar rebuild succeeds, so the parent can refetch profiles. */
  onAvatarRegenerated?: () => void;
  /** Called when the user confirms deletion. Parent owns store mutation + selection cleanup. */
  onDelete?: (name: string) => void;
}

export function CharacterDetail({
  character,
  genre,
  portraitUrl,
  sessionId,
  onAvatarRegenerated,
  onDelete,
}: CharacterDetailProps) {
  const t = useTranslations("characters");
  const [isRegenerating, setIsRegenerating] = React.useState(false);
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const handleRegenerate = React.useCallback(async () => {
    if (!sessionId || isRegenerating) return;
    setIsRegenerating(true);
    try {
      await rebuildCharacterAvatar(sessionId, character.name);
      toast.success(t("regenerate_success"));
      onAvatarRegenerated?.();
    } catch (err) {
      toast.error(t("regenerate_failed"), {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsRegenerating(false);
    }
  }, [sessionId, character.name, isRegenerating, onAvatarRegenerated, t]);

  const handleConfirmDelete = React.useCallback(() => {
    onDelete?.(character.name);
    setConfirmOpen(false);
  }, [onDelete, character.name]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void handleRegenerate()}
          disabled={!sessionId || isRegenerating}
          className="h-8 gap-1.5 text-xs"
        >
          {isRegenerating ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <RefreshCw className="size-3.5" />
          )}
          {isRegenerating ? t("regenerating_avatar") : t("regenerate_avatar")}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setConfirmOpen(true)}
          disabled={!onDelete}
          className="h-8 gap-1.5 border-rose-500/40 text-xs text-rose-300 hover:bg-rose-500/10 hover:text-rose-200"
        >
          <Trash2 className="size-3.5" />
          {t("delete_character")}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_1.4fr]">
        <div className="space-y-3">
          <PortraitPanel name={character.name} src={portraitUrl} />
          <div className="flex items-center justify-between gap-2">
            <h3 className="truncate text-lg font-semibold">{character.name}</h3>
            <RoleBadge role={character.role} />
          </div>
          <div className="rounded-xl border border-border/40 bg-card/40 p-3">
            <TraitRadar traits={character.traits} genre={genre} />
          </div>
        </div>
        <NarrativePanels character={character} />
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("delete_confirm_title")}</DialogTitle>
            <DialogDescription>
              {t("delete_confirm_body", { name: character.name })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmOpen(false)}
            >
              {t("delete_confirm_cancel")}
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleConfirmDelete}
            >
              {t("delete_confirm_action")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
