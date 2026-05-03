/**
 * Providers page — live health/rate-limit observability for the LLM
 * fallback chain. Polls /api/providers/health every 10s while visible.
 *
 * Dev-only diagnostic page: no auth, no persistence, in-memory state only.
 * Counts down cooldown values client-side between polls so the UI feels live.
 */

interface ProviderHealth {
  model: string;
  healthy: boolean;
  last_latency_ms: number | null;
  avg_latency_ms: number | null;
  consecutive_failures: number;
  cooldown_remaining_s: number;
  last_error_class: string | null;
}

interface RateLimitedKey {
  key_id: string;
  cooldown_remaining_s: number;
}

interface RateLimitedModel {
  model: string;
  key_id: string;
  cooldown_remaining_s: number;
}

interface HealthResponse {
  providers: ProviderHealth[];
  rate_limited_keys: RateLimitedKey[];
  rate_limited_models: RateLimitedModel[];
  snapshot_ts: string;
}

const REFRESH_INTERVAL_MS = 10_000;
const TICK_INTERVAL_MS = 1_000;

function providersPage() {
  return {
    snapshot: null as HealthResponse | null,
    loading: false,
    error: '',
    lastFetchAt: 0 as number,
    _refreshTimer: 0 as number,
    _tickTimer: 0 as number,

    async init(): Promise<void> {
      await this.loadHealth();
      // Auto-refresh from server every 10s
      this._refreshTimer = window.setInterval(() => {
        this.loadHealth();
      }, REFRESH_INTERVAL_MS);
      // Local cooldown countdown every 1s (no network)
      this._tickTimer = window.setInterval(() => this._tickCooldowns(), TICK_INTERVAL_MS);
    },

    destroy(): void {
      if (this._refreshTimer) window.clearInterval(this._refreshTimer);
      if (this._tickTimer) window.clearInterval(this._tickTimer);
    },

    async loadHealth(): Promise<void> {
      this.loading = !this.snapshot; // only show big spinner on first load
      this.error = '';
      try {
        const res = await API.get<HealthResponse>('/providers/health');
        this.snapshot = res;
        this.lastFetchAt = Date.now();
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to load health snapshot';
      } finally {
        this.loading = false;
      }
    },

    /** Decrement cooldown counters between server polls so the UI feels live. */
    _tickCooldowns(): void {
      if (!this.snapshot) return;
      for (const p of this.snapshot.providers) {
        if (p.cooldown_remaining_s > 0) p.cooldown_remaining_s = Math.max(0, p.cooldown_remaining_s - 1);
      }
      for (const k of this.snapshot.rate_limited_keys) {
        if (k.cooldown_remaining_s > 0) k.cooldown_remaining_s = Math.max(0, k.cooldown_remaining_s - 1);
      }
      for (const m of this.snapshot.rate_limited_models) {
        if (m.cooldown_remaining_s > 0) m.cooldown_remaining_s = Math.max(0, m.cooldown_remaining_s - 1);
      }
    },

    statusLabel(p: ProviderHealth): string {
      if (!p.healthy) return 'Lỗi';
      if (p.cooldown_remaining_s > 0) return 'Cooldown';
      return 'Khoẻ';
    },

    statusDotClass(p: ProviderHealth): string {
      if (!p.healthy) return 'bg-red-500';
      if (p.cooldown_remaining_s > 0) return 'bg-amber-500';
      return 'bg-green-500';
    },

    statusBadgeClass(p: ProviderHealth): string {
      if (!p.healthy) return 'bg-red-50 text-red-700';
      if (p.cooldown_remaining_s > 0) return 'bg-amber-50 text-amber-700';
      return 'bg-green-50 text-green-700';
    },

    formatLatency(ms: number | null): string {
      if (ms === null || ms === undefined) return '—';
      return `${ms} ms`;
    },

    formatCooldown(s: number): string {
      if (s <= 0) return '—';
      if (s < 60) return `${s}s`;
      const m = Math.floor(s / 60);
      const rem = s % 60;
      return `${m}m ${rem}s`;
    },

    get providers(): ProviderHealth[] {
      return this.snapshot?.providers || [];
    },

    get rateLimitedKeys(): RateLimitedKey[] {
      return this.snapshot?.rate_limited_keys || [];
    },

    get rateLimitedModels(): RateLimitedModel[] {
      return this.snapshot?.rate_limited_models || [];
    },

    get isEmpty(): boolean {
      return this.providers.length === 0 && this.rateLimitedKeys.length === 0 && this.rateLimitedModels.length === 0;
    },
  };
}
