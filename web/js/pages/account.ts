/**
 * Account page — login, register.
 */

interface UserProfile {
  username: string;
  [key: string]: unknown;
}

interface AccountApiResponse {
  ok: boolean;
  profile?: UserProfile;
  message?: string;
}

function accountPage() {
  return {
    username: '' as string,
    password: '' as string,
    loading: false as boolean,
    message: '' as string,
    profile: null as UserProfile | null,

    async login(): Promise<void> {
      if (!this.username || !this.password) {
        this.message = 'Enter username and password';
        return;
      }
      this.loading = true;
      this.message = '';
      try {
        const res = await API.post<AccountApiResponse>('/account/login', {
          username: this.username, password: this.password,
        });
        if (res.ok) {
          this.profile = res.profile ?? null;
          this.message = 'Login successful!';
        } else {
          this.message = res.message || 'Wrong username or password';
        }
      } catch (e) {
        this.message = 'Error: ' + (e as Error).message;
      }
      this.loading = false;
    },

    async register(): Promise<void> {
      if (!this.username || !this.password) {
        this.message = 'Enter username and password';
        return;
      }
      this.loading = true;
      this.message = '';
      try {
        const res = await API.post<AccountApiResponse>('/account/register', {
          username: this.username, password: this.password,
        });
        if (res.ok) {
          this.profile = res.profile ?? null;
          this.message = 'Registration successful!';
        } else {
          this.message = res.message || 'Username already exists';
        }
      } catch (e) {
        this.message = 'Error: ' + (e as Error).message;
      }
      this.loading = false;
    },

    logout(): void {
      this.profile = null;
      this.message = 'Signed out';
    },
  };
}
