/**
 * app store — general UI state (theme, navigation, loading overlay, storage).
 *
 * Extracted from app.ts. Store key: 'app'.
 * Behavior is identical to the original inline definition.
 */

interface NavItem {
  id: string;
  label: string;
  icon: string;
  group: 'main' | 'bottom';
}

interface PipelineResult {
  session_id?: string;
  livePreview?: string;
  filename?: string;
  [key: string]: unknown;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'pipeline',  label: 'Create Story',  icon: 'pencil-square',         group: 'main'   },
  { id: 'library',   label: 'Library',       icon: 'building-library',       group: 'main'   },
  { id: 'export',    label: 'Export',        icon: 'arrow-down-tray',        group: 'main'   },
  { id: 'analytics', label: 'Analytics',     icon: 'chart-bar',              group: 'main'   },
  { id: 'branching', label: 'Branching',     icon: 'arrows-pointing-out',    group: 'main'   },
  { id: 'providers', label: 'Providers',     icon: 'server-stack',           group: 'bottom' },
  { id: 'settings',  label: 'Settings',      icon: 'cog-6-tooth',            group: 'bottom' },
  { id: 'guide',     label: 'Guide',         icon: 'question-mark-circle',   group: 'bottom' },
] as const;

export function createAppStore() {
  return {
    page: 'pipeline' as string,
    sidebarOpen: window.innerWidth > 768,
    /** @deprecated use isLoading instead */
    loading: false,
    /** Global loading overlay flag. Set via setLoading() / clearLoading(). */
    isLoading: false,
    /** Human-readable message shown in the global loading overlay. */
    loadingMessage: '' as string,
    sessionId: null as string | null,
    pipelineResult: null as PipelineResult | null,
    storageWarning: '' as string,
    /** Current theme: 'dark' | 'light'. Reflects the <html> .dark class. */
    darkMode: document.documentElement.classList.contains('dark'),

    navItems: NAV_ITEMS,

    /**
     * Toggle dark mode: flip the .dark class on <html>, persist choice.
     */
    toggleDarkMode(): void {
      this.darkMode = !this.darkMode;
      if (this.darkMode) {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }
      document.documentElement.style.colorScheme = this.darkMode ? 'dark' : 'light';
      try { localStorage.setItem('sf_theme', this.darkMode ? 'dark' : 'light'); } catch (_) {}
    },

    setLoading(msg?: string): void {
      this.isLoading = true;
      this.loadingMessage = msg || '';
    },

    clearLoading(): void {
      this.isLoading = false;
      this.loadingMessage = '';
    },

    navigate(page: string): void {
      this.page = page;
      if (window.innerWidth <= 768) this.sidebarOpen = false;
      window.location.hash = page;
    },

    toggleSidebar(): void {
      this.sidebarOpen = !this.sidebarOpen;
    },

    async savePipelineResult(data: PipelineResult): Promise<void> {
      this.pipelineResult = data;
      this.storageWarning = '';
      const toStore: PipelineResult = { ...data };
      delete toStore.livePreview;
      const json = JSON.stringify(toStore);

      if (json.length > 4 * 1024 * 1024) {
        console.warn('Pipeline result large (' + Math.round(json.length / 1024) + 'KB)');
      }

      await window.storageManager.setItem('sf_result', json);

      if (window.storageManager.isUsingFallback()) {
        console.info('[StorageManager] Saved to IndexedDB fallback.');
      }
    },

    async init(): Promise<void> {
      const resolveHash = (raw: string): string | null => {
        const id = raw.replace(/^#?\/?/, '');
        return NAV_ITEMS.some((n: NavItem) => n.id === id) ? id : null;
      };

      const initialPage = resolveHash(window.location.hash);
      if (initialPage) this.page = initialPage;

      const _controller = new AbortController();
      const _signal = _controller.signal;

      window.addEventListener('hashchange', (_e: Event): void => {
        const page = resolveHash(window.location.hash);
        if (page && page !== this.page) this.page = page;
      }, { signal: _signal });

      window.addEventListener('resize', (_e: Event): void => {
        if (window.innerWidth > 768 && !this.sidebarOpen) {
          this.sidebarOpen = true;
        } else if (window.innerWidth <= 768 && this.sidebarOpen) {
          this.sidebarOpen = false;
        }
      }, { signal: _signal });

      let _storageErrorShown = false;
      window.addEventListener('storage-error', (_e: Event): void => {
        if (_storageErrorShown) return;
        _storageErrorShown = true;
        if (typeof window.sfShowToast === 'function') {
          window.sfShowToast('Storage unavailable — progress may not be saved', 'warning');
        }
      }, { signal: _signal });

      await window.storageManager.init();
      try {
        const saved = await window.storageManager.getItem('sf_result');
        if (saved) {
          const parsed: unknown = JSON.parse(saved);
          if (parsed && typeof parsed === 'object') {
            this.pipelineResult = parsed as PipelineResult;
            Alpine.store('pipeline').result = parsed;
            Alpine.store('pipeline').status = 'done';
            Alpine.store('pipeline').progress = 4;
          }
        }
      } catch (e) {
        console.warn('Failed to restore pipeline result:', (e as Error).message);
        await window.storageManager.removeItem('sf_result');
      }
    },
  };
}

export { NAV_ITEMS };
export type { NavItem, PipelineResult };
