# Sprint 8: Security & Frontend Build
**Duration:** 1 week | **Owner:** Security + Frontend | **Priority:** HIGH

## Objectives
- Frontend build pipeline (eliminate Tailwind CDN)
- JWT secret rotation & audit logging
- Dependency vulnerability scanning
- API versioning

## Tasks

### 8.1 Frontend Build Pipeline [Frontend] — 2 days
- [ ] Initialize `package.json` with Vite + Tailwind CSS
- [ ] Create `vite.config.js`:
  - Input: web/js/*.js, web/css/*.css
  - Output: web/dist/ (minified, hashed filenames)
  - Dev server with hot reload proxy to FastAPI :7860
- [ ] Create `tailwind.config.js`:
  - Scan web/**/*.html, web/**/*.js for classes
  - Custom theme tokens from web/css/tokens.css
- [ ] Create `postcss.config.js` with Tailwind + autoprefixer
- [ ] Update `web/index.html`:
  - Replace CDN links with built assets
  - Add `<script type="module">` for Vite
- [ ] Add build step to Dockerfile:
  - Node.js stage for `npm run build`
  - Copy dist/ to runtime stage
- [ ] Create `web/js/error-boundary.js`:
  - Global error handler with fallback UI
  - Error reporting to /api/metrics

### 8.2 Security Hardening [Security] — 2 days
- [ ] JWT Secret Rotation:
  - Create `services/jwt_manager.py` with key rotation support
  - Support multiple valid signing keys during rotation window
  - Config for rotation interval (default 30 days)
- [ ] Audit Logging:
  - Create `services/audit_logger.py`:
    - Log: who, what, when, where (IP), result
    - Structured JSON format
    - Async write to avoid blocking requests
  - Create `middleware/audit_middleware.py`:
    - Auto-log all write operations (POST/PUT/DELETE)
    - Log auth events (login, logout, failed attempts)
    - Log config changes
    - Log pipeline executions
- [ ] Dependency Scanning:
  - Create `.github/dependabot.yml` for Python + GitHub Actions
  - Add `pip-audit` to CI pipeline
  - Create `scripts/security-scan.sh` for local scanning

### 8.3 API Versioning [Backend] — 1 day
- [ ] Create `api/v1/` directory
- [ ] Mount all existing routes under `/api/v1/`
- [ ] Add `/api/v1` prefix to all route files
- [ ] Keep `/api/health` unversioned (operational endpoint)
- [ ] Add deprecation header middleware for future `/api/` → `/api/v1/` redirect
- [ ] Update frontend API client base URL

### 8.4 HTTPS Enforcement [Security + DevOps] — 1 day
- [ ] Nginx TLS configuration with Let's Encrypt
- [ ] HSTS header (Strict-Transport-Security)
- [ ] HTTP → HTTPS redirect
- [ ] Secure cookie flags (if applicable)

## Success Criteria
- [ ] `npm run build` produces minified CSS < 50KB (vs 300KB CDN)
- [ ] Lighthouse performance score > 85
- [ ] Audit logs capture all write operations
- [ ] `pip-audit` runs in CI with zero critical vulnerabilities
- [ ] All API calls work via `/api/v1/` prefix
