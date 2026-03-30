#!/usr/bin/env bash
# =============================================================================
# Estatio — Set GitHub Repository Secrets
# Reads values from backend/.env (never hardcoded here)
#
# Usage: ./scripts/set-github-secrets.sh <owner/repo>
# Example: ./scripts/set-github-secrets.sh rajmanda/estatio
# =============================================================================

set -euo pipefail

REPO="${1:-}"
if [[ -z "$REPO" ]]; then
  echo "Usage: $0 <owner/repo>"
  echo "Example: $0 rajmanda/estatio"
  exit 1
fi

# Check gh CLI
if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not installed.  brew install gh  then  gh auth login"
  exit 1
fi
if ! gh auth status &>/dev/null; then
  echo "ERROR: Not authenticated. Run: gh auth login"
  exit 1
fi

# Load .env from backend/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../backend/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: backend/.env not found at $ENV_FILE"
  echo "Copy backend/.env.example to backend/.env and fill in your values first."
  exit 1
fi

# Parse .env — export KEY=VALUE lines, ignore comments and blanks
while IFS= read -r line; do
  [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  export "$key=$val"
done < "$ENV_FILE"

# Also read WIF values which are GCP-specific (not in .env)
# These are passed as env vars or prompted
WIF_PROVIDER="${WIF_PROVIDER:-}"
WIF_SERVICE_ACCOUNT="${WIF_SERVICE_ACCOUNT:-}"
GCP_PROJECT_ID="${GCP_PROJECT_ID:-}"

prompt_if_empty() {
  local var_name="$1"
  local prompt_text="$2"
  local current_val="${!var_name:-}"
  if [[ -z "$current_val" ]]; then
    read -rp "  $prompt_text: " current_val
    export "$var_name=$current_val"
  fi
}

echo ""
echo "Setting GitHub secrets for: $REPO"
echo "(reading credentials from backend/.env)"
echo ""

prompt_if_empty GCP_PROJECT_ID      "GCP Project ID"
prompt_if_empty WIF_PROVIDER        "WIF Provider resource name"
prompt_if_empty WIF_SERVICE_ACCOUNT "WIF Service Account email"

set_secret() {
  local name="$1"
  local value="${2:-}"
  if [[ -z "$value" ]]; then
    echo "  SKIP  $name (empty)"
    return
  fi
  echo -n "$value" | gh secret set "$name" --repo="$REPO" --body=-
  echo "  ✓  $name"
}

set_secret "GCP_PROJECT_ID"       "$GCP_PROJECT_ID"
set_secret "WIF_PROVIDER"         "$WIF_PROVIDER"
set_secret "WIF_SERVICE_ACCOUNT"  "$WIF_SERVICE_ACCOUNT"
set_secret "MONGODB_URL"          "${MONGODB_URL:-}"
set_secret "GOOGLE_CLIENT_ID"     "${GOOGLE_CLIENT_ID:-}"
set_secret "GOOGLE_CLIENT_SECRET" "${GOOGLE_CLIENT_SECRET:-}"
set_secret "APP_SECRET_KEY"       "${SECRET_KEY:-}"
set_secret "GEMINI_API_KEY"       "${GEMINI_API_KEY:-}"
set_secret "SENDGRID_API_KEY"     "${SENDGRID_API_KEY:-}"

echo ""
echo "✅ All secrets set on $REPO"
echo ""
echo "Next: git push -u origin main"
