/**
 * settings store — config/settings state.
 *
 * Extracted from app.ts. Store key: 'settings'.
 * Behavior is identical to the original inline definition.
 */

interface ConnectionTestResponse {
  ok: boolean;
  message: string;
}

export function createSettingsStore() {
  return {
    config: null as Record<string, unknown> | null,
    saving: false,
    message: '' as string,

    async load(): Promise<void> {
      try {
        this.config = await API.get<Record<string, unknown>>('/config');
      } catch (e) { console.error('Load config failed:', e); }
    },

    async save(formData: Record<string, unknown>): Promise<void> {
      this.saving = true;
      this.message = '';
      try {
        await API.put('/config', formData);
        this.message = 'Settings saved!';
        await this.load();
      } catch (e) {
        this.message = 'Error: ' + (e as Error).message;
      }
      this.saving = false;
    },

    async testConnection(): Promise<string> {
      try {
        const res = await API.post<ConnectionTestResponse>('/config/test-connection');
        return res.ok ? 'OK: ' + res.message : 'Error: ' + res.message;
      } catch (e) { return 'Error: ' + (e as Error).message; }
    },
  };
}
