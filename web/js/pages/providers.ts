/**
 * Providers page — LLM provider status, quotas, and fallbacks.
 */

interface ProviderStatus {
  provider: string;
  status: 'ok' | 'degraded' | 'down' | 'unknown';
  quota_pct?: number;
  reset_at?: string;
  models_available?: number;
  last_error?: string;
}

interface ProvidersResponse {
  providers: Record<string, ProviderStatus>;
  configured_providers: string[];
}

interface QuotaCheckResponse {
  low_quota_providers: Array<{ provider: string; quota_pct: number | null; reset_at: string | null }>;
  ok_providers: string[];
  threshold: number;
  should_switch: boolean;
}

interface FallbacksResponse {
  fallbacks: Record<string, string[]>;
}

function providersPage() {
  return {
    providers: {} as Record<string, ProviderStatus>,
    configured: [] as string[],
    quotaWarnings: [] as Array<{ provider: string; quota_pct: number | null; reset_at: string | null }>,
    fallbacks: {} as Record<string, string[]>,
    loading: false,
    refreshing: false,
    error: '',

    async init(): Promise<void> {
      await this.loadAll();
    },

    async loadAll(): Promise<void> {
      this.loading = true;
      this.error = '';
      try {
        const [statusRes, quotaRes, fallbackRes] = await Promise.all([
          API.get<ProvidersResponse>('/providers/status'),
          API.get<QuotaCheckResponse>('/providers/quota-check?threshold=0.2'),
          API.get<FallbacksResponse>('/providers/fallbacks'),
        ]);
        this.providers = statusRes.providers || {};
        this.configured = statusRes.configured_providers || [];
        this.quotaWarnings = quotaRes.low_quota_providers || [];
        this.fallbacks = fallbackRes.fallbacks || {};
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to load providers';
      } finally {
        this.loading = false;
      }
    },

    async refresh(): Promise<void> {
      this.refreshing = true;
      try {
        await API.post('/providers/refresh');
        await this.loadAll();
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Refresh failed';
      } finally {
        this.refreshing = false;
      }
    },

    getStatusColor(status: string): string {
      switch (status) {
        case 'ok': return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
        case 'degraded': return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400';
        case 'down': return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';
        default: return 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400';
      }
    },

    getStatusIcon(status: string): string {
      switch (status) {
        case 'ok': return '<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />';
        case 'degraded': return '<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />';
        case 'down': return '<path stroke-linecap="round" stroke-linejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />';
        default: return '<path stroke-linecap="round" stroke-linejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />';
      }
    },

    formatQuota(pct: number | null): string {
      if (pct === null || pct === undefined) return 'N/A';
      return Math.round(pct * 100) + '%';
    },

    formatResetTime(iso: string | null): string {
      if (!iso) return '';
      const d = new Date(iso);
      const now = Date.now();
      const diff = d.getTime() - now;
      if (diff < 0) return 'now';
      if (diff < 60000) return 'in <1m';
      if (diff < 3600000) return `in ${Math.ceil(diff / 60000)}m`;
      return `in ${Math.ceil(diff / 3600000)}h`;
    },

    get providerList(): Array<{ name: string; status: ProviderStatus }> {
      return this.configured.map(name => ({
        name,
        status: this.providers[name] || { provider: name, status: 'unknown' },
      }));
    },

    get hasWarnings(): boolean {
      return this.quotaWarnings.length > 0;
    },
  };
}
