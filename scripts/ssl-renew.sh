#!/usr/bin/env bash
# ssl-renew.sh — Certbot SSL certificate renewal script
# Run via cron: 0 3 * * 1 /opt/storyforge/scripts/ssl-renew.sh >> /var/log/ssl-renew.log 2>&1
#
# Prerequisites:
#   - certbot installed (or use the certbot Docker container)
#   - nginx running with write access to /etc/letsencrypt

set -euo pipefail

LOG_TAG="[ssl-renew] $(date '+%Y-%m-%d %H:%M:%S')"
NGINX_CONTAINER="${NGINX_CONTAINER:-storyforge-nginx}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/storyforge/docker-compose.production.yml}"

echo "$LOG_TAG Starting certificate renewal check..."

# Attempt renewal (certbot only renews if cert expires within 30 days)
if certbot renew --quiet --no-self-upgrade; then
    echo "$LOG_TAG Renewal check completed successfully."
else
    echo "$LOG_TAG WARNING: certbot renew exited with non-zero status." >&2
    exit 1
fi

# Reload nginx to pick up any newly-issued certificate
echo "$LOG_TAG Reloading nginx..."
if docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -s reload 2>/dev/null; then
    echo "$LOG_TAG nginx reloaded successfully."
elif docker exec "$NGINX_CONTAINER" nginx -s reload 2>/dev/null; then
    echo "$LOG_TAG nginx reloaded via docker exec."
else
    echo "$LOG_TAG WARNING: Could not reload nginx — reload manually if cert was renewed." >&2
fi

echo "$LOG_TAG Done."
