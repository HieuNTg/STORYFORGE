/**
 * Account page — login, register.
 */
function accountPage() {
  return {
    username: '',
    password: '',
    loading: false,
    message: '',
    profile: null,

    async login() {
      if (!this.username || !this.password) {
        this.message = 'Enter username and password';
        return;
      }
      this.loading = true;
      this.message = '';
      try {
        const res = await API.post('/account/login', {
          username: this.username, password: this.password,
        });
        if (res.ok) {
          this.profile = res.profile;
          this.message = 'Login successful!';
        } else {
          this.message = res.message || 'Wrong username or password';
        }
      } catch (e) {
        this.message = 'Error: ' + e.message;
      }
      this.loading = false;
    },

    async register() {
      if (!this.username || !this.password) {
        this.message = 'Enter username and password';
        return;
      }
      this.loading = true;
      this.message = '';
      try {
        const res = await API.post('/account/register', {
          username: this.username, password: this.password,
        });
        if (res.ok) {
          this.profile = res.profile;
          this.message = 'Registration successful!';
        } else {
          this.message = res.message || 'Username already exists';
        }
      } catch (e) {
        this.message = 'Error: ' + e.message;
      }
      this.loading = false;
    },

    logout() {
      this.profile = null;
      this.message = 'Signed out';
    },
  };
}
