#!/bin/sh
# Deploy the API to Fly with the Neon connection string and the write token as secrets.
# Reads FLY_API_TOKEN, LOOKAHEAD_DATABASE_URL (or DATABASE_URL, then the tables go in the
# `lookahead` schema of that database) and LOOKAHEAD_WRITE_TOKEN from the environment or from
# .env in the repository root. Uses Fly's remote builder, so no local Docker is needed.
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi
APP="${LOOKAHEAD_FLY_APP_NAME:-lookahead-grid-api}"
SCHEMA=""
if [ -n "${LOOKAHEAD_DATABASE_URL:-}" ]; then
  URL="$LOOKAHEAD_DATABASE_URL"
else
  URL="${DATABASE_URL:?set LOOKAHEAD_DATABASE_URL or DATABASE_URL to the Neon connection string}"
  SCHEMA="lookahead"
fi
: "${LOOKAHEAD_WRITE_TOKEN:?set LOOKAHEAD_WRITE_TOKEN}"
command -v flyctl >/dev/null 2>&1 || { echo "flyctl is not installed: https://fly.io/docs/flyctl/install/"; exit 1; }
if ! flyctl apps list 2>/dev/null | grep -q "^$APP"; then
  flyctl apps create "$APP" --org personal
fi
flyctl secrets set --app "$APP" --stage DATABASE_URL="$URL" LOOKAHEAD_WRITE_TOKEN="$LOOKAHEAD_WRITE_TOKEN" LOOKAHEAD_DB_SCHEMA="$SCHEMA"
flyctl deploy --app "$APP" --remote-only --ha=false
echo "deployed: https://$APP.fly.dev/v1/health"
