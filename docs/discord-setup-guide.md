# StoryForge Discord Server Setup Guide

## Channel Structure

| Channel | Purpose |
|---------|---------|
| `#announcements` | Releases, blog posts — maintainers only, all members can read |
| `#general` | Open discussion, introductions, off-topic |
| `#bug-reports` | Structured bug reports (use the pinned template) |
| `#feature-requests` | Proposals and voting on new features |
| `#showcase` | Share stories generated with StoryForge |

## Bot Recommendations

**GitHub Webhook (releases)**
1. GitHub repo → Settings → Webhooks → Add webhook
2. Payload URL: Discord channel webhook URL (Edit Channel → Integrations)
3. Content type: `application/json`
4. Events: Releases, Discussions — posts to `#announcements` automatically

**Carl-bot** — recommended for role assignment and moderation logging.

## Role Setup

| Role | Color | How Assigned |
|------|-------|-------------|
| `@core-team` | Purple | Manual — project founders and lead maintainers |
| `@maintainer` | Blue | Manual — active maintainers with merge rights |
| `@contributor` | Green | Auto-assigned via bot after first merged GitHub PR |
| `@member` | Gray | Default role granted on join |

## Moderation Guidelines

- Slow-mode 10 s on `#general` to prevent spam
- Auto-delete invite links posted by non-moderators
- 3-strike system: warn → 24 h mute → permanent ban
- Keep `#bug-reports` and `#feature-requests` on-topic; off-topic posts moved to `#general`
- All moderation actions logged to a private `#mod-log` channel visible to `@maintainer`+
