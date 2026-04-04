/**
 * Settings page — LLM provider configuration, API keys, and image settings.
 */

interface SettingsModel {
  id: string;
  label: string;
}

interface SettingsProvider {
  id: string;
  name: string;
  icon: string;
  hint: string;
  url: string;
  keyPlaceholder: string;
  guide: string;
  models: SettingsModel[];
}

function settingsPage() {
  return {
    showAddKey: false as boolean,
    newKeyInput: '' as string,
    showAddProfile: false as boolean,
    editingProfile: null as number | null,
    profileForm: { name: '', base_url: '', api_key: '', model: '', enabled: true },
    profileDetected: null as { provider: string; name: string; model: string } | null,
    profiles: [] as { name: string; provider: string; base_url: string; api_key_masked: string; model: string; enabled: boolean }[],
    form: {
      api_key: '' as string,
      base_url: 'https://api.openai.com/v1' as string,
      model: 'gpt-4o-mini' as string,
      temperature: 0.8 as number,
      max_tokens: 4096 as number,
      cheap_model: '' as string,
      cheap_base_url: '' as string,
      image_provider: 'none' as string,
      hf_token: '' as string,
      hf_image_model: 'black-forest-labs/FLUX.1-schnell' as string,
      image_prompt_style: 'cinematic' as string,
    },
    maskedKey: '' as string,
    maskedHfToken: '' as string,
    savedKeysMasked: [] as string[],
    saving: false as boolean,
    testing: false as boolean,
    message: '' as string,
    showKey: false as boolean,
    selectedProvider: 'openai' as string,
    presetApplied: '' as string,
    // Alpine magic property — injected at runtime; stub satisfies TypeScript without unsafe double-cast
    $watch: null! as (
      expr: string | (() => unknown),
      cb: (val: unknown) => void
    ) => void,

    providers: [
      {
        id: 'openai', name: 'OpenAI', icon: 'chip', hint: 'GPT-5.4, o3, o4',
        url: 'https://api.openai.com/v1',
        keyPlaceholder: 'sk-proj-...',
        guide: 'Get your API key at <a href="https://platform.openai.com/api-keys" target="_blank" class="text-brand-600 underline font-medium">platform.openai.com</a> → Create new secret key → Copy and paste here.',
        models: [
          { id: 'gpt-5.4-nano', label: 'GPT-5.4 Nano (cheapest)' },
          { id: 'gpt-5.4-mini', label: 'GPT-5.4 Mini' },
          { id: 'gpt-5.4', label: 'GPT-5.4' },
          { id: 'o4-mini', label: 'o4-mini (reasoning)' },
          { id: 'o3', label: 'o3 (advanced reasoning)' },
        ],
      },
      {
        id: 'gemini', name: 'Google Gemini', icon: 'sparkles', hint: 'Gemini 2.5 / 3.1',
        url: 'https://generativelanguage.googleapis.com/v1beta/openai/',
        keyPlaceholder: 'AIza...',
        guide: 'Get a free API key at <a href="https://aistudio.google.com/apikey" target="_blank" class="text-brand-600 underline font-medium">aistudio.google.com</a> → Create API Key → Copy.',
        models: [
          { id: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite (cheapest)' },
          { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
          { id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
          { id: 'gemini-3-flash-preview', label: 'Gemini 3 Flash (preview)' },
          { id: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro (latest)' },
          { id: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash Lite (preview)' },
          { id: 'gemma-4-31b-it', label: 'Gemma 4 31B (free, 262K ctx)' },
          { id: 'gemma-4-26b-a4b-it', label: 'Gemma 4 26B MoE (free, 262K ctx)' },
        ],
      },
      {
        id: 'anthropic', name: 'Anthropic', icon: 'academic-cap', hint: 'Claude 4.5 / 4.6',
        url: 'https://api.anthropic.com/v1/',
        keyPlaceholder: 'sk-ant-...',
        guide: 'Get your API key at <a href="https://console.anthropic.com/settings/keys" target="_blank" class="text-brand-600 underline font-medium">console.anthropic.com</a> → Create Key → Copy.',
        models: [
          { id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5 (cheapest)' },
          { id: 'claude-sonnet-4-6-20260217', label: 'Sonnet 4.6' },
          { id: 'claude-opus-4-6-20260205', label: 'Opus 4.6 (most powerful)' },
        ],
      },
      {
        id: 'openrouter', name: 'OpenRouter', icon: 'arrows-right-left', hint: '290+ models',
        url: 'https://openrouter.ai/api/v1',
        keyPlaceholder: 'sk-or-...',
        guide: 'Register at <a href="https://openrouter.ai/keys" target="_blank" class="text-brand-600 underline font-medium">openrouter.ai</a> → Keys → Create Key. 29+ free models available!',
        models: [
          { id: 'qwen/qwen3.6-plus:free', label: 'Qwen 3.6 Plus (free, 1M ctx)' },
          { id: 'qwen/qwen3-next-80b-a3b-instruct:free', label: 'Qwen3 Next 80B (free, 262K ctx)' },
          { id: 'nousresearch/hermes-3-llama-3.1-405b:free', label: 'Hermes 3 405B (free, 131K ctx)' },
          { id: 'nvidia/nemotron-3-super-120b-a12b:free', label: 'Nemotron 3 Super 120B (free)' },
          { id: 'meta-llama/llama-3.3-70b-instruct:free', label: 'Llama 3.3 70B (free, 65K ctx)' },
          { id: 'google/gemma-4-31b-it', label: 'Gemma 4 31B (262K ctx, cheap)' },
          { id: 'google/gemma-4-26b-a4b-it', label: 'Gemma 4 26B MoE (262K ctx, cheap)' },
          { id: 'google/gemma-3-27b-it:free', label: 'Gemma 3 27B (free, 131K ctx)' },
          { id: 'z-ai/glm-4.5-air:free', label: 'GLM 4.5 Air (free, 131K ctx)' },
          { id: 'google/gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
          { id: 'deepseek/deepseek-r1', label: 'DeepSeek R1' },
          { id: 'anthropic/claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
        ],
      },
      {
        id: 'local', name: 'Local / Ollama', icon: 'computer-desktop', hint: 'Free, self-hosted',
        url: 'http://localhost:11434/v1',
        keyPlaceholder: 'Leave blank or enter token...',
        guide: 'Install <a href="https://ollama.com" target="_blank" class="text-brand-600 underline font-medium">Ollama</a> → run <code class="bg-slate-100 px-1.5 py-0.5 rounded text-xs">ollama run qwen3.5:9b</code> → ready to use, no API key needed.',
        models: [
          { id: 'qwen3.5:9b', label: 'Qwen 3.5 9B (recommended)' },
          { id: 'llama3.1:8b', label: 'Llama 3.1 8B' },
          { id: 'deepseek-r1', label: 'DeepSeek R1' },
          { id: 'mistral-large-2', label: 'Mistral Large 2' },
          { id: 'gemma2:9b', label: 'Gemma 2 9B' },
        ],
      },
      {
        id: 'custom', name: 'Custom', icon: 'cog-6-tooth', hint: 'Any URL',
        url: '',
        keyPlaceholder: 'API key...',
        guide: 'Enter the base URL and model name manually in the <strong>Advanced Settings</strong> section below.',
        models: [] as SettingsModel[],
      },
    ] as SettingsProvider[],

    get currentProvider(): SettingsProvider | undefined {
      return this.providers.find(p => p.id === this.selectedProvider);
    },

    async applyModelPreset(key: string): Promise<void> {
      try {
        const res = await API.post<{ status: string; label?: string }>(`/config/model-presets/${key}`);
        if (res.status === 'ok') {
          this.presetApplied = `Applied: ${res.label}`;
          this.selectedProvider = 'openrouter';
          await Alpine.store('settings').load();
          const cfg = Alpine.store('settings').config;
          if (cfg?.llm) {
            this.form.base_url = cfg.llm.base_url;
            this.form.model = cfg.llm.model;
            this.form.cheap_model = cfg.llm.cheap_model || '';
            this.form.cheap_base_url = cfg.llm.cheap_base_url || '';
          }
          setTimeout(() => { this.presetApplied = ''; }, 4000);
        }
      } catch (e) { this.message = 'Preset error: ' + (e as Error).message; }
    },

    providerIconIds: { openai: 'chip', gemini: 'sparkles', anthropic: 'academic-cap', openrouter: 'arrows-right-left', local: 'computer-desktop', custom: 'cog-6-tooth' } as Record<string, string>,

    openAddProfile(): void {
      this.profileForm = { name: '', base_url: '', api_key: '', model: '', enabled: true };
      this.profileDetected = null;
      this.editingProfile = null;
      this.showAddProfile = true;
    },

    openEditProfile(index: number): void {
      const p = this.profiles[index];
      this.profileForm = { name: p.name, base_url: p.base_url, api_key: '', model: p.model, enabled: p.enabled };
      this.profileDetected = null;
      this.editingProfile = index;
      this.showAddProfile = true;
    },

    async detectFromKey(): Promise<void> {
      const key = this.profileForm.api_key.trim();
      if (key.length < 4) { this.profileDetected = null; return; }
      try {
        const res = await API.post<{ detected: boolean; provider?: string; name?: string; model?: string; base_url?: string }>('/config/profiles/detect', { api_key: key });
        if (res.detected) {
          this.profileDetected = { provider: res.provider!, name: res.name!, model: res.model! };
          this.profileForm.name = res.name!;
          this.profileForm.base_url = res.base_url!;
          this.profileForm.model = res.model!;
        } else {
          this.profileDetected = null;
        }
      } catch { this.profileDetected = null; }
    },

    async saveProfile(): Promise<void> {
      if (!this.profileForm.api_key && this.editingProfile === null) return;
      try {
        if (this.editingProfile !== null) {
          await API.put(`/config/profiles/${this.editingProfile}`, this.profileForm);
        } else {
          await API.post('/config/profiles', { api_key: this.profileForm.api_key, name: this.profileForm.name, base_url: this.profileForm.base_url, model: this.profileForm.model, enabled: true });
        }
        this.showAddProfile = false;
        this.editingProfile = null;
        this.profileDetected = null;
        await Alpine.store('settings').load();
        this.message = 'Provider added.';
        setTimeout(() => { this.message = ''; }, 2000);
      } catch (e) { this.message = 'Error: ' + (e as Error).message; }
    },

    async deleteProfile(index: number): Promise<void> {
      try {
        await API.del(`/config/profiles/${index}`);
        await Alpine.store('settings').load();
        this.message = 'Profile removed.';
        setTimeout(() => { this.message = ''; }, 2000);
      } catch (e) { this.message = 'Error: ' + (e as Error).message; }
    },

    async toggleProfile(index: number): Promise<void> {
      try {
        const res = await API.patch<{ enabled: boolean }>(`/config/profiles/${index}/toggle`);
        this.profiles[index].enabled = res.enabled;
      } catch (e) { this.message = 'Error: ' + (e as Error).message; }
    },

    setProfileProvider(providerId: string): void {
      const p = this.providers.find(x => x.id === providerId);
      if (p?.url) this.profileForm.base_url = p.url;
      if (p?.models?.length) this.profileForm.model = p.models[0].id;
    },

    async addKey(): Promise<void> {
      const key = this.newKeyInput.trim();
      if (!key) return;
      try {
        await API.put('/config', { append_api_keys: [key] });
        this.newKeyInput = '';
        this.showAddKey = false;
        await Alpine.store('settings').load();
        this.message = 'API key added.';
        setTimeout(() => { this.message = ''; }, 2000);
      } catch (e) { this.message = 'Error: ' + (e as Error).message; }
    },

    async removeKey(index: number): Promise<void> {
      try {
        await API.del(`/config/api-keys/${index}`);
        this.savedKeysMasked.splice(index, 1);
        this.message = 'API key removed.';
        setTimeout(() => { this.message = ''; }, 2000);
      } catch (e) { this.message = 'Error: ' + (e as Error).message; }
    },

    selectProvider(id: string): void {
      this.selectedProvider = id;
      const p = this.providers.find(x => x.id === id);
      if (p?.url) this.form.base_url = p.url;
      if (p?.models?.length) this.form.model = p.models[0].id;
    },

    init(): void {
      // Wait for config to load, then populate form
      const apply = () => {
        const cfg = Alpine.store('settings').config;
        if (!cfg?.llm) return;
        this.form.base_url = cfg.llm.base_url || this.form.base_url;
        this.form.model = cfg.llm.model || this.form.model;
        this.form.temperature = cfg.llm.temperature ?? this.form.temperature;
        this.form.max_tokens = cfg.llm.max_tokens || this.form.max_tokens;
        this.form.cheap_model = cfg.llm.cheap_model || '';
        this.form.cheap_base_url = cfg.llm.cheap_base_url || '';
        this.maskedKey = cfg.llm.api_key_masked || '';
        this.savedKeysMasked = cfg.llm.api_keys_masked || [];
        this.profiles = cfg.llm.profiles || [];
        if (cfg.pipeline) {
          this.form.image_provider = cfg.pipeline.image_provider || 'none';
          this.form.hf_image_model = cfg.pipeline.hf_image_model || 'black-forest-labs/FLUX.1-schnell';
          this.form.image_prompt_style = cfg.pipeline.image_prompt_style || 'cinematic';
          this.maskedHfToken = cfg.pipeline.hf_token_masked || '';
        }
        // Auto-detect provider from base_url
        const url = (cfg.llm.base_url || '').toLowerCase();
        if (url.includes('openai.com')) this.selectedProvider = 'openai';
        else if (url.includes('googleapis.com') || url.includes('generativelanguage')) this.selectedProvider = 'gemini';
        else if (url.includes('anthropic.com')) this.selectedProvider = 'anthropic';
        else if (url.includes('openrouter.ai')) this.selectedProvider = 'openrouter';
        else if (url.includes('localhost') || url.includes('127.0.0.1')) this.selectedProvider = 'local';
        else this.selectedProvider = 'custom';
      };
      apply();
      // Config may still be loading — watch for it
      this.$watch(() => Alpine.store('settings').config, () => apply());
    },

    async save(): Promise<void> {
      this.saving = true;
      this.message = '';
      try {
        // Don't send empty secrets — they would overwrite saved values
        const data: Record<string, unknown> = { ...this.form };
        if (!data['api_key']) delete data['api_key'];
        if (!data['hf_token']) delete data['hf_token'];
        delete data['api_keys'];
        // Auto-set backend_type based on provider selection
        data['backend_type'] = 'api';
        await API.put('/config', data);
        this.message = 'Settings saved successfully!';
        // Reload config to refresh masked keys
        await Alpine.store('settings').load();
      } catch (e) { this.message = 'Error: ' + (e as Error).message; }
      this.saving = false;
    },

    async testConn(): Promise<void> {
      this.testing = true;
      this.message = 'Testing connection...';
      this.message = await Alpine.store('settings').testConnection();
      this.testing = false;
    },
  };
}
