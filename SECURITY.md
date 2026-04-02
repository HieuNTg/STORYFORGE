# Security Policy

## Supported Versions

Only the latest stable release receives security patches.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | Yes                |
| < 1.0   | No (end-of-life)   |

---

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

### Option 1 — GitHub Security Advisories (preferred)

Use the private disclosure channel built into this repository:
1. Go to the **Security** tab of this repository.
2. Click **"Report a vulnerability"**.
3. Fill in the form with as much detail as possible.

### Option 2 — Email

Send a report to **security@storyforge.dev** with the subject line:
`[SECURITY] <brief description>`

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce (proof-of-concept preferred)
- Any relevant logs, screenshots, or code snippets
- Your preferred credit name/handle (optional)

Encrypt sensitive reports with our PGP key (available on request).

---

## Response Timeline

| Milestone              | Target SLA         |
| ---------------------- | ------------------ |
| Acknowledgment         | 48 hours           |
| Initial assessment     | 7 days             |
| Patch / mitigation     | 30 days (critical: 7 days) |
| Public disclosure      | After patch ships  |

We follow **coordinated disclosure**: we will work with you to agree on a
disclosure date once a fix is ready. We will not disclose your report publicly
without your consent before the patch is released.

---

## What Qualifies as a Security Issue

- Remote code execution (RCE) or arbitrary command injection
- Authentication bypass or privilege escalation
- Server-Side Request Forgery (SSRF) that exposes internal services
- Insecure direct object references leaking user data
- API key / secret exposure through logs or responses
- Path traversal giving read/write access outside intended directories
- Cross-Site Scripting (XSS) or Cross-Site Request Forgery (CSRF) with real impact
- SQL injection or NoSQL injection
- Denial-of-service via resource exhaustion (unauthenticated)
- Insecure deserialization leading to code execution

---

## Out of Scope

The following are **not** considered security vulnerabilities for this project:

- Bugs that require physical access to the server
- Issues in third-party services (OpenRouter, OpenAI, etc.) — report those upstream
- Self-XSS requiring the attacker to already have account access
- Theoretical vulnerabilities with no practical exploit path
- Rate-limit bypasses that require a valid authenticated session
- Missing security headers on static assets served from localhost
- Outdated dependency versions with no known exploitable path
- Social engineering or phishing attacks

---

## Credit Policy

We gratefully acknowledge responsible reporters. With your permission, we will:

- Add your name / handle to the release notes and CHANGELOG under "Security"
- List you in the **Hall of Fame** section of this document (future)

We do not currently offer a monetary bug bounty.

---

## Hall of Fame

_No entries yet. Be the first responsible reporter!_
