# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Use GitHub's private vulnerability reporting: open the **Security** tab of this
repository, choose **Report a vulnerability**, and describe the issue. Include
what is affected, steps to reproduce, and the impact you see. This is a
volunteer-maintained project, so replies are best effort; we aim to acknowledge
a report within a few days and to coordinate disclosure with you once a fix is
ready.

## Supported versions

Security fixes go to the latest release and to `main`. Older releases are not
patched; update to the latest one.

## Security model

StoryForge is built to run on your own machine. What it protects, and how:

- **Loopback only by default.** The Docker compose files publish the API (7860)
  and the web UI (3001) on `127.0.0.1` only. Outside Docker, the API binds to
  `127.0.0.1` and refuses to start on any other address unless an access token
  is set.
- **Host and Origin checks (DNS rebinding, CSRF).** Every request's `Host`
  header must be on an allow-list. Behind the web UI's proxy the API sees the
  browser's host in `X-Forwarded-Host`, which must pass the same list, so a page
  that re-points its own domain at your machine is refused. A browser `Origin`
  on a POST, PUT, PATCH or DELETE must be an allowed origin (403 otherwise), and
  WebSocket upgrades check `Origin` too. The defaults cover `localhost` and
  `127.0.0.1` on ports 3001 and 7860; `STORYFORGE_ALLOWED_ORIGINS` adds origins
  (their host names are trusted as hosts as well) and `STORYFORGE_ALLOWED_HOSTS`
  adds host names. State-changing requests also need the double-submit CSRF token.
- **Optional shared access token.** Set `STORYFORGE_ACCESS_TOKEN` to require it
  on every API call. The browser UI trades the token for an httponly session
  cookie. Sessions are not individually revocable; rotating the token revokes
  all of them. There are no user accounts or roles.
- **API keys are encrypted at rest.** Keys saved in Settings are stored in
  `data/config.json` encrypted with a Fernet key. The key is generated on first
  start and saved to `data/.secret_key` (or supplied through
  `STORYFORGE_SECRET_KEY`). Back it up with `config.json`; without it saved keys
  cannot be read.
- **Keys follow the provider host.** If you change the provider base URL to a
  different host, the stored key is not sent there; you must enter the key again.
  Base URLs that point at private network addresses are blocked unless you opt in
  (`STORYFORGE_ALLOW_PRIVATE_BASE_URL`); `host.docker.internal` is the one
  built-in exception, for local model servers.
- **No web-session providers.** StoryForge only talks to API providers with an
  API key you supply. It does not drive consumer web logins or browser sessions.

If you expose the app beyond your machine (see `docs/self-hosting.md`), set an
access token and put it behind a network you trust; it is not hardened for the
open internet.

## In scope

Authentication or Host/Origin bypass, SSRF, path traversal, leaking stored API
keys through logs or responses, XSS or CSRF with real impact, and remote code
execution.

## Out of scope

Issues that need physical or shell access to the host, vulnerabilities in the
LLM providers or other third-party services (report those upstream), and
findings with no practical exploit path.
