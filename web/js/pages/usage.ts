/**
 * Usage page — token and cost tracking.
 */

interface LayerBreakdown {
  tokens: number;
  cost_usd: number;
}

interface SessionSummary {
  call_count: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  by_story: Record<string, LayerBreakdown>;
  by_model: Record<string, LayerBreakdown>;
}

interface StoryCost {
  story_id: string;
  call_count: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  by_layer: Record<string, LayerBreakdown>;
  by_agent: Record<string, LayerBreakdown>;
  by_model: Record<string, LayerBreakdown>;
}

function usagePage() {
  return {
    session: null as SessionSummary | null,
    selectedStory: null as StoryCost | null,
    loading: false,
    error: '',

    async init(): Promise<void> {
      await this.loadSession();
    },

    async loadSession(): Promise<void> {
      this.loading = true;
      this.error = '';
      try {
        this.session = await API.get<SessionSummary>('/usage/session');
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to load usage';
      } finally {
        this.loading = false;
      }
    },

    async loadStory(storyId: string): Promise<void> {
      this.loading = true;
      this.error = '';
      try {
        this.selectedStory = await API.get<StoryCost>(`/usage/${encodeURIComponent(storyId)}`);
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to load story usage';
      } finally {
        this.loading = false;
      }
    },

    async resetSession(): Promise<void> {
      if (!confirm('Reset all session usage data?')) return;
      try {
        await API.del('/usage/session');
        this.session = null;
        this.selectedStory = null;
        await this.loadSession();
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Reset failed';
      }
    },

    formatCost(usd: number): string {
      return '$' + usd.toFixed(4);
    },

    formatTokens(n: number): string {
      if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M';
      if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
      return n.toString();
    },

    get storyList(): string[] {
      if (!this.session?.by_story) return [];
      return Object.keys(this.session.by_story);
    },

    get modelList(): Array<{ model: string; tokens: number; cost: number }> {
      if (!this.session?.by_model) return [];
      return Object.entries(this.session.by_model).map(([model, data]) => ({
        model,
        tokens: data.tokens,
        cost: data.cost_usd,
      })).sort((a, b) => b.cost - a.cost);
    },

    get storyBreakdown(): Array<{ key: string; tokens: number; cost: number }> {
      if (!this.selectedStory) return [];
      const layers = Object.entries(this.selectedStory.by_layer || {}).map(([key, data]) => ({
        key: `Layer ${key}`,
        tokens: data.tokens,
        cost: data.cost_usd,
      }));
      const agents = Object.entries(this.selectedStory.by_agent || {}).map(([key, data]) => ({
        key,
        tokens: data.tokens,
        cost: data.cost_usd,
      }));
      return [...layers, ...agents].sort((a, b) => b.cost - a.cost);
    },
  };
}
