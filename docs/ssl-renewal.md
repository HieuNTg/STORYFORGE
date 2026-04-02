# SSL Certificate Renewal

## Certificate Paths

| File | Path |
|---|---|
| Full chain | `/etc/letsencrypt/live/<domain>/fullchain.pem` |
| Private key | `/etc/letsencrypt/live/<domain>/privkey.pem` |
| Renewal config | `/etc/letsencrypt/renewal/<domain>.conf` |

In Docker Compose the `nginx/ssl/` directory is bind-mounted to `/etc/letsencrypt` inside both the `nginx` and `certbot` containers.

## Renewal Schedule

The `certbot` service in `docker-compose.production.yml` runs a loop that:

1. Calls `certbot renew --quiet` immediately on startup.
2. Sleeps 12 hours, then repeats.

Certbot only issues a new certificate when the current one expires within **30 days**, so the actual renewal happens roughly every **60 days**. The 12-hour polling cadence ensures the window is never missed.

## Manual Renewal

```bash
# Trigger an immediate check inside the running certbot container
docker compose -f docker-compose.production.yml exec certbot certbot renew

# Force renewal regardless of expiry (for testing)
docker compose -f docker-compose.production.yml exec certbot certbot renew --force-renewal

# After manual renewal, reload nginx
docker compose -f docker-compose.production.yml exec nginx nginx -s reload
```

Using the standalone script:

```bash
sudo bash scripts/ssl-renew.sh
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Certbot exits with "No renewals were attempted" | Certificate is valid for > 30 days — this is normal. |
| Port 80 blocked during renewal | Ensure the ACME challenge path `/.well-known/acme-challenge/` is reachable and `nginx/webroot` is mounted correctly. |
| nginx reload fails after renewal | Run `docker compose exec nginx nginx -t` to validate config, then reload manually. |
| Certificate not found | Re-run initial issuance: `docker compose exec certbot certbot certonly --webroot -w /var/www/certbot -d <domain>`. |
