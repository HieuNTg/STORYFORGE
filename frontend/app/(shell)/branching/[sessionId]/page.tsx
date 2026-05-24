"use client";

/**
 * Branching page — composes BranchGraph (dagre client layout) +
 * ChoiceCardGrid + BranchToolbar + BookmarksDrawer
 * with useBranchSession + nuqs `?node=`.
 *
 * Layout:
 *   Phase 4: client-side dagre LR layout via `BranchGraph` — we feed
 *   `parentId` + `childCount` and let xyflow render. Server layout (legacy
 *   integer grid) is ignored to allow much richer card content (288×152
 *   nodes with serif title + summary + child-count pill).
 *
 * Streaming:
 *   `chooseStream(idx)` is wired into `useBranchSession`. Streaming text is
 *   piped to `branching-store.streamingText`; the panel renders it live
 *   while `isStreaming` is true. On `complete`, the hook invalidates the
 *   session queries.
 */

import * as React from "react";
import { useParams } from "next/navigation";
import { useQueryState } from "nuqs";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { BranchGraph } from "@/components/branching/BranchGraph";
import type {
  BranchGraphEdge,
  BranchGraphNode,
  BranchNodeStatus,
} from "@/components/branching/BranchGraph";
import { ChoiceCardGrid } from "@/components/branching/ChoiceCardGrid";
import type { ChoiceCardItem } from "@/components/branching/ChoiceCardGrid";
import { BranchToolbar } from "@/components/branching/BranchToolbar";
import { BookmarksDrawer } from "@/components/branching/BookmarksDrawer";
import type { BookmarkItem } from "@/components/branching/BookmarksDrawer";

import { useBranchSession } from "@/hooks/useBranchSession";
import { useBranchingStore } from "@/stores/branching-store";
import type {
  BranchNode,
  BranchTreeNode,
  BranchTreeResponse,
  BranchLayoutResponse,
  BranchBookmark,
} from "@/lib/api/branching";

function normalizeChoiceLabel(c: string | { text?: string; label?: string }, fallback: string): string {
  if (typeof c === "string") return c;
  return c?.text ?? c?.label ?? fallback;
}

function normalizeChoiceSummary(
  c: string | { text?: string; label?: string; summary?: string; description?: string },
): string | undefined {
  if (typeof c === "string") return undefined;
  return c?.summary ?? c?.description ?? undefined;
}

/** Pull the canonical current node id from any of the session payloads. */
function pickCurrentId(
  current?: { node?: BranchNode } | null,
  tree?: BranchTreeResponse | null,
  layout?: BranchLayoutResponse | null,
): string | null {
  return (
    current?.node?.id ??
    tree?.current ??
    layout?.current ??
    null
  );
}

/** Compose nodes/edges for xyflow from tree dict (dagre handles layout). */
function buildGraph(
  tree: BranchTreeResponse | null | undefined,
  currentId: string | null,
  bookmarks: BranchBookmark[],
): { nodes: BranchGraphNode[]; edges: BranchGraphEdge[] } {
  const nodes: BranchGraphNode[] = [];
  const edges: BranchGraphEdge[] = [];
  if (!tree) return { nodes, edges };

  const bookmarkNodeIds = new Set(bookmarks.map((b) => b.node_id));
  const treeNodes: Record<string, BranchTreeNode> = tree.nodes ?? {};

  for (const [id, tn] of Object.entries(treeNodes)) {
    const isCurrent = id === currentId;
    const childCount = tn.child_ids?.length ?? 0;
    const hasChildren = childCount > 0;
    let status: BranchNodeStatus;
    if (isCurrent) status = "current";
    else if (hasChildren) status = "visited";
    else if ((tn.choices?.length ?? 0) > 0) status = "choice";
    else status = "pending";

    const text = (tn.text ?? "").trim();
    const labelBase = bookmarkNodeIds.has(id) ? "★ " : "";
    const label = labelBase + (text ? text.slice(0, 60) : id);
    const summary = text ? text.slice(0, 200) : undefined;

    nodes.push({
      id,
      parentId: tn.parent ?? null,
      data: {
        label,
        summary,
        status,
        childCount,
        word_count:
          text.length > 0 ? text.split(/\s+/).filter(Boolean).length : undefined,
      },
    });

    if (tn.parent) {
      edges.push({ id: `e-${tn.parent}-${id}`, source: tn.parent, target: id });
    }
  }
  return { nodes, edges };
}

export default function BranchingPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params?.sessionId ?? null;
  const t = useTranslations("branching");

  const s = useBranchSession(sessionId);
  const streamingText = useBranchingStore((st) => st.streamingText);
  const streaming = useBranchingStore((st) => st.streaming);
  const lastError = useBranchingStore((st) => st.lastError);
  const setSelected = useBranchingStore((st) => st.setSelected);

  // nuqs ?node= — keep in sync with selectedNodeId.
  const [nodeParam, setNodeParam] = useQueryState("node");

  const currentNode: BranchNode | undefined = s.current.data?.node;
  const treeData = s.tree.data ?? null;
  const layoutData = s.layout.data ?? null;
  const bookmarksRaw = s.bookmarks.data?.bookmarks;
  const bookmarkList: BranchBookmark[] = React.useMemo<BranchBookmark[]>(
    () => bookmarksRaw ?? [],
    [bookmarksRaw]
  );

  const currentId = pickCurrentId(s.current.data, treeData, layoutData);

  // Selected node id: prefer URL, fall back to current node.
  const selectedId = nodeParam ?? currentId ?? undefined;

  React.useEffect(() => {
    setSelected(selectedId ?? null);
  }, [selectedId, setSelected]);

  const { nodes, edges } = React.useMemo(
    () => buildGraph(treeData, currentId, bookmarkList),
    [treeData, currentId, bookmarkList]
  );

  // Choices for the card grid — taken from the current node.
  const choices: ChoiceCardItem[] = React.useMemo(() => {
    if (!currentNode?.choices) return [];
    return currentNode.choices.map((c, idx) => ({
      id: String(idx),
      title: normalizeChoiceLabel(c, t("choice_label_default")),
      summary: normalizeChoiceSummary(
        c as string | { text?: string; label?: string; summary?: string; description?: string },
      ),
    }));
  }, [currentNode, t]);

  // Toolbar capabilities.
  const undoRedo = s.undoRedo.data;
  const canBack = !!currentNode?.parent; // back walks to parent
  const canUndo = !!undoRedo?.can_undo;
  const canRedo = !!undoRedo?.can_redo;
  const pending =
    s.choose.isPending ||
    s.back.isPending ||
    s.undo.isPending ||
    s.redo.isPending ||
    streaming;

  const [bookmarksOpen, setBookmarksOpen] = React.useState(false);

  // ----- Actions -----------------------------------------------------------

  const handleNodeClick = React.useCallback(
    (id: string) => {
      void setNodeParam(id);
      // If user clicks a node that isn't current, jump to it via /goto.
      if (id !== currentId) {
        s.gotoNode.mutate(
          { node_id: id },
          {
            onError: (err) => toast.error(t("choice_switch_failed", { msg: err.message })),
          }
        );
      }
    },
    [setNodeParam, s.gotoNode, currentId, t]
  );

  const handleChoose = React.useCallback(
    (id: string) => {
      const idx = Number(id);
      if (!Number.isFinite(idx)) return;
      // Prefer streaming choose. The hook auto-invalidates on `complete`.
      s.chooseStream(idx);
    },
    [s]
  );

  const handleBack = React.useCallback(() => {
    s.back.mutate(undefined, {
      onError: (err) => toast.error(err.message),
    });
  }, [s.back]);

  const handleUndo = React.useCallback(() => {
    s.undo.mutate(undefined, {
      onError: (err) => toast.error(err.message),
    });
  }, [s.undo]);

  const handleRedo = React.useCallback(() => {
    s.redo.mutate(undefined, {
      onError: (err) => toast.error(err.message),
    });
  }, [s.redo]);

  // Bookmark CRUD — for the focused node.
  const bookmarkItems: BookmarkItem[] = React.useMemo(
    () =>
      bookmarkList.map((b) => ({
        id: b.id,
        label: b.label ?? t("toolbar_bookmark"),
        created_at: b.created_at ?? "",
        node_id: b.node_id,
      })),
    [bookmarkList, t]
  );

  const handleAddBookmark = React.useCallback(
    (label: string) => {
      const target = selectedId ?? currentId;
      if (!target) {
        toast.error(t("bookmark_no_node"));
        return;
      }
      s.addBookmark.mutate(
        { node_id: target, label },
        {
          onSuccess: () => toast.success(t("bookmark_add_success")),
          onError: (err) => toast.error(err.message),
        }
      );
    },
    [s.addBookmark, selectedId, currentId, t]
  );

  const handleDeleteBookmark = React.useCallback(
    (id: string) => {
      s.deleteBookmark.mutate(id, {
        onError: (err) => toast.error(err.message),
      });
    },
    [s.deleteBookmark]
  );

  const handleGotoBookmark = React.useCallback(
    (id: string) => {
      s.gotoBookmark.mutate(id, {
        onSuccess: () => setBookmarksOpen(false),
        onError: (err) => toast.error(err.message),
      });
    },
    [s.gotoBookmark]
  );

  // ----- Render ------------------------------------------------------------

  if (!sessionId) {
    return (
      <div className="text-sm text-muted-foreground">{t("session_not_found")}</div>
    );
  }

  if (s.current.isLoading && !currentNode) {
    return (
      <div className="text-sm text-muted-foreground">{t("loading_session")}</div>
    );
  }

  if (s.current.error) {
    return (
      <div className="text-sm text-destructive">
        {t("load_failed", { msg: s.current.error.message })}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
        <BranchToolbar
          onBack={handleBack}
          onUndo={handleUndo}
          onRedo={handleRedo}
          canBack={canBack}
          canUndo={canUndo}
          canRedo={canRedo}
          onOpenBookmarks={() => setBookmarksOpen(true)}
          isPending={pending}
        />
      </div>

      {lastError ? (
        <p className="text-sm text-destructive" role="alert">
          {t("error_label", { msg: lastError })}
        </p>
      ) : null}

      <BranchGraph
        nodes={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
        onReadNode={handleNodeClick}
        selectedId={selectedId}
        height={420}
      />

      <section className="flex flex-col gap-3 rounded-xl border bg-card/40 p-4">
        <header className="flex items-center justify-between">
          <h2 className="font-serif text-lg text-foreground">{t("choice_current_segment")}</h2>
          {streaming ? (
            <span className="text-xs text-accent">{t("choice_generating_inline")}</span>
          ) : null}
        </header>
        <p className="whitespace-pre-wrap font-serif text-sm leading-relaxed text-foreground/90">
          {streaming && streamingText ? streamingText : (currentNode?.text ?? "")}
        </p>
        <div>
          <h3 className="mb-2 font-serif text-sm font-medium text-muted-foreground">
            {t("choice_next_pick")}
          </h3>
          <ChoiceCardGrid
            choices={choices}
            onChoose={handleChoose}
            disabled={pending}
          />
        </div>
      </section>

      <BookmarksDrawer
        open={bookmarksOpen}
        onOpenChange={setBookmarksOpen}
        bookmarks={bookmarkItems}
        onGoto={handleGotoBookmark}
        onDelete={handleDeleteBookmark}
        onAdd={handleAddBookmark}
      />
    </div>
  );
}
