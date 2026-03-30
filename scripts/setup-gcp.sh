#!/usr/bin/env bash
# =============================================================================
# Estatio — One-time GCP + GitHub Setup Script
# =============================================================================
# What this does:
#   1. Enables required GCP APIs
#   2. Creates Artifact Registry repository
#   3. Creates GCS bucket for documents
#   4. Creates CI/CD service account + grants roles
#   5. Creates Workload Identity Federation pool + provider
#   6. Binds GitHub repo to service account
#   7. Creates all GCP Secret Manager secrets
#   8. Writes .env (backend) and .github-secrets.txt (for GitHub UI)
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - gh CLI installed and authenticated (gh auth login) [optional, for auto-setting secrets]
#   - A GCP project already created
#   - A MongoDB Atlas connection string ready
# =============================================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }
step()    { echo -e "\n${BOLD}${CYAN}══ $* ${RESET}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ███████╗███████╗████████╗ █████╗ ████████╗██╗ ██████╗"
echo "  ██╔════╝██╔════╝╚══██╔══╝██╔══██╗╚══██╔══╝██║██╔═══██╗"
echo "  █████╗  ███████╗   ██║   ███████║   ██║   ██║██║   ██║"
echo "  ██╔══╝  ╚════██║   ██║   ██╔══██║   ██║   ██║██║   ██║"
echo "  ███████╗███████║   ██║   ██║  ██║   ██║   ██║╚██████╔╝"
echo "  ╚══════╝╚══════╝   ╚═╝   ╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝"
echo -e "${RESET}"
echo -e "  ${BOLD}GCP + GitHub Setup Script${RESET}"
echo "  ──────────────────────────────────────────────────────"
echo ""

# ── Script directory (repo root) ──────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Collect inputs ────────────────────────────────────────────────────────────
step "Configuration"

prompt() {
  local var_name="$1"
  local prompt_text="$2"
  local default="${3:-}"
  local secret="${4:-false}"

  if [[ -n "$default" ]]; then
    prompt_text="$prompt_text [${default}]"
  fi

  if [[ "$secret" == "true" ]]; then
    read -rsp "  ${BOLD}${prompt_text}:${RESET} " value
    echo ""
  else
    read -rp "  ${BOLD}${prompt_text}:${RESET} " value
  fi

  if [[ -z "$value" && -n "$default" ]]; then
    value="$default"
  fi

  if [[ -z "$value" ]]; then
    error "$var_name cannot be empty."
  fi

  printf -v "$var_name" '%s' "$value"
}

# Try to auto-detect project from gcloud
DEFAULT_PROJECT="$(gcloud config get-value project 2>/dev/null || echo "")"
DEFAULT_REGION="us-central1"

prompt GCP_PROJECT_ID     "GCP Project ID"                         "$DEFAULT_PROJECT"
prompt GCP_REGION         "GCP Region"                             "$DEFAULT_REGION"
prompt GITHUB_REPO        "GitHub repo (owner/repo)"               ""
prompt MONGODB_URL        "MongoDB connection string (mongodb+srv://...)" "" true
prompt GOOGLE_CLIENT_ID   "Google OAuth Client ID"                 ""
prompt GOOGLE_CLIENT_SECRET "Google OAuth Client Secret"           "" true
prompt GEMINI_API_KEY     "Gemini API Key (or press Enter to skip)" "" true
prompt SENDGRID_API_KEY   "SendGrid API Key (or press Enter to skip)" "" true

# Derived values
APP_NAME="estatio"
SA_NAME="${APP_NAME}-cicd-sa"
SA_EMAIL="${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
POOL_ID="github-pool"
PROVIDER_ID="github-provider"
REGISTRY_REPO="${APP_NAME}-images"
DOCS_BUCKET="${APP_NAME}-documents-${GCP_PROJECT_ID}"
TERRAFORM_BUCKET="${APP_NAME}-terraform-state-${GCP_PROJECT_ID}"
REGISTRY_URL="${GCP_REGION}-docker.pkg.dev"
SECRET_KEY="$(openssl rand -base64 32)"

echo ""
info "Project:       ${GCP_PROJECT_ID}"
info "Region:        ${GCP_REGION}"
info "GitHub repo:   ${GITHUB_REPO}"
info "Service acct:  ${SA_EMAIL}"
info "Registry:      ${REGISTRY_URL}/${GCP_PROJECT_ID}/${REGISTRY_REPO}"
info "Docs bucket:   gs://${DOCS_BUCKET}"
echo ""
read -rp "  ${BOLD}Proceed? (y/N):${RESET} " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# ── Set gcloud project ────────────────────────────────────────────────────────
gcloud config set project "$GCP_PROJECT_ID" --quiet

PROJECT_NUMBER="$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(projectNumber)')"
info "Project number: ${PROJECT_NUMBER}"

# ── 1. Enable APIs ────────────────────────────────────────────────────────────
step "Enabling GCP APIs"

APIS=(
  run.googleapis.com
  cloudbuild.googleapis.com
  secretmanager.googleapis.com
  storage.googleapis.com
  iam.googleapis.com
  iamcredentials.googleapis.com
  cloudresourcemanager.googleapis.com
  artifactregistry.googleapis.com
  monitoring.googleapis.com
  logging.googleapis.com
  compute.googleapis.com
  sts.googleapis.com
)

for api in "${APIS[@]}"; do
  info "Enabling $api …"
  gcloud services enable "$api" --project="$GCP_PROJECT_ID" --quiet
done
success "All APIs enabled"

# ── 2. Artifact Registry ──────────────────────────────────────────────────────
step "Creating Artifact Registry"

if gcloud artifacts repositories describe "$REGISTRY_REPO" \
     --location="$GCP_REGION" --project="$GCP_PROJECT_ID" &>/dev/null; then
  warn "Artifact Registry repo already exists — skipping"
else
  gcloud artifacts repositories create "$REGISTRY_REPO" \
    --repository-format=docker \
    --location="$GCP_REGION" \
    --project="$GCP_PROJECT_ID" \
    --description="Estatio Docker images"
  success "Artifact Registry created: ${REGISTRY_URL}/${GCP_PROJECT_ID}/${REGISTRY_REPO}"
fi

# ── 3. GCS Buckets ────────────────────────────────────────────────────────────
step "Creating GCS Buckets"

create_bucket() {
  local bucket="$1"
  local desc="$2"
  if gsutil ls -b "gs://${bucket}" &>/dev/null; then
    warn "Bucket gs://${bucket} already exists — skipping"
  else
    gsutil mb -p "$GCP_PROJECT_ID" -l "$GCP_REGION" "gs://${bucket}"
    # Enable versioning
    gsutil versioning set on "gs://${bucket}"
    # Lifecycle: delete old non-current versions after 90 days
    cat > /tmp/lifecycle.json <<'LIFECYCLE'
{
  "rule": [{
    "action": {"type": "Delete"},
    "condition": {"numNewerVersions": 3, "daysSinceNoncurrentTime": 90}
  }]
}
LIFECYCLE
    gsutil lifecycle set /tmp/lifecycle.json "gs://${bucket}"
    success "Bucket created: gs://${bucket} (${desc})"
  fi
}

create_bucket "$DOCS_BUCKET"      "Document storage"
create_bucket "$TERRAFORM_BUCKET" "Terraform state"

# ── 4. CI/CD Service Account ──────────────────────────────────────────────────
step "Creating CI/CD Service Account"

if gcloud iam service-accounts describe "$SA_EMAIL" \
     --project="$GCP_PROJECT_ID" &>/dev/null; then
  warn "Service account ${SA_EMAIL} already exists — skipping creation"
else
  gcloud iam service-accounts create "$SA_NAME" \
    --project="$GCP_PROJECT_ID" \
    --display-name="Estatio CI/CD Service Account"
  success "Service account created: ${SA_EMAIL}"
fi

info "Granting IAM roles …"
ROLES=(
  roles/run.admin
  roles/storage.admin
  roles/artifactregistry.writer
  roles/iam.serviceAccountUser
  roles/secretmanager.secretAccessor
  roles/secretmanager.viewer
  roles/logging.logWriter
  roles/monitoring.metricWriter
)

for role in "${ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$role" \
    --quiet
  info "  Granted $role"
done
success "IAM roles granted"

# ── 5. Workload Identity Federation ──────────────────────────────────────────
step "Setting up Workload Identity Federation"

POOL_RESOURCE="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}"
PROVIDER_RESOURCE="${POOL_RESOURCE}/providers/${PROVIDER_ID}"

# Create pool
if gcloud iam workload-identity-pools describe "$POOL_ID" \
     --location=global --project="$GCP_PROJECT_ID" &>/dev/null; then
  warn "WIF pool '${POOL_ID}' already exists — skipping"
else
  gcloud iam workload-identity-pools create "$POOL_ID" \
    --project="$GCP_PROJECT_ID" \
    --location=global \
    --display-name="GitHub Actions Pool"
  success "WIF pool created: ${POOL_ID}"
fi

# Create provider
if gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
     --workload-identity-pool="$POOL_ID" \
     --location=global --project="$GCP_PROJECT_ID" &>/dev/null; then
  warn "WIF provider '${PROVIDER_ID}' already exists — skipping"
else
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --project="$GCP_PROJECT_ID" \
    --location=global \
    --workload-identity-pool="$POOL_ID" \
    --display-name="GitHub OIDC Provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref,attribute.actor=assertion.actor" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
    --issuer-uri="https://token.actions.githubusercontent.com"
  success "WIF provider created"
fi

# Bind GitHub repo → service account
info "Binding GitHub repo to service account …"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --project="$GCP_PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_RESOURCE}/attribute.repository/${GITHUB_REPO}" \
  --quiet
success "GitHub repo '${GITHUB_REPO}' can now impersonate ${SA_EMAIL}"

# ── 6. Secret Manager secrets ─────────────────────────────────────────────────
step "Creating Secret Manager Secrets"

create_secret() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    warn "Skipping empty secret: ${name}"
    return
  fi
  if gcloud secrets describe "$name" --project="$GCP_PROJECT_ID" &>/dev/null; then
    info "Secret ${name} exists — adding new version"
    echo -n "$value" | gcloud secrets versions add "$name" \
      --project="$GCP_PROJECT_ID" --data-file=-
  else
    echo -n "$value" | gcloud secrets create "$name" \
      --project="$GCP_PROJECT_ID" \
      --replication-policy=automatic \
      --data-file=-
    success "Secret created: ${name}"
  fi
}

create_secret "estatio-mongodb-url"          "$MONGODB_URL"
create_secret "estatio-secret-key"           "$SECRET_KEY"
create_secret "estatio-google-client-id"     "$GOOGLE_CLIENT_ID"
create_secret "estatio-google-client-secret" "$GOOGLE_CLIENT_SECRET"
create_secret "estatio-gcs-bucket-name"      "$DOCS_BUCKET"
create_secret "estatio-gemini-api-key"       "$GEMINI_API_KEY"
create_secret "estatio-sendgrid-api-key"     "$SENDGRID_API_KEY"

# Grant backend Cloud Run SA access to secrets (create it if needed)
BACKEND_SA="${APP_NAME}-backend-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$BACKEND_SA" --project="$GCP_PROJECT_ID" &>/dev/null; then
  gcloud iam service-accounts create "${APP_NAME}-backend-sa" \
    --project="$GCP_PROJECT_ID" \
    --display-name="Estatio Backend Service Account"
fi
for role in roles/secretmanager.secretAccessor roles/storage.objectAdmin roles/logging.logWriter roles/monitoring.metricWriter; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:${BACKEND_SA}" \
    --role="$role" --quiet
done
success "Backend service account configured"

# ── 7. Resolve final WIF values ───────────────────────────────────────────────
step "Resolving output values"

WIF_PROVIDER_VALUE="$(gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --workload-identity-pool="$POOL_ID" \
  --location=global \
  --project="$GCP_PROJECT_ID" \
  --format='value(name)')"

WIF_SERVICE_ACCOUNT_VALUE="$SA_EMAIL"

BACKEND_IMAGE="${REGISTRY_URL}/${GCP_PROJECT_ID}/${REGISTRY_REPO}/backend:latest"
FRONTEND_IMAGE="${REGISTRY_URL}/${GCP_PROJECT_ID}/${REGISTRY_REPO}/frontend:latest"

# ── 8. Write backend/.env ─────────────────────────────────────────────────────
step "Writing backend/.env"

ENV_FILE="${REPO_ROOT}/backend/.env"

cat > "$ENV_FILE" <<EOF
# =============================================================================
# Estatio Backend — Environment Variables
# Generated by scripts/setup-gcp.sh on $(date)
# DO NOT COMMIT THIS FILE — it is in .gitignore
# =============================================================================

# App
APP_NAME=Estatio
APP_ENV=development
SECRET_KEY=${SECRET_KEY}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# MongoDB
MONGODB_URL=${MONGODB_URL}
MONGODB_DB=estatio

# Google OAuth
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

# Google Cloud Storage
GCS_BUCKET_NAME=${DOCS_BUCKET}
GCS_PROJECT_ID=${GCP_PROJECT_ID}
# For local dev, point to your downloaded service account key:
# GOOGLE_APPLICATION_CREDENTIALS=./service-account.json

# AI
GEMINI_API_KEY=${GEMINI_API_KEY}
AI_PROVIDER=gemini

# Redis (used by Celery worker)
REDIS_URL=redis://localhost:6379/0

# Email
SENDGRID_API_KEY=${SENDGRID_API_KEY}
FROM_EMAIL=noreply@estatio.app

# Frontend
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=["http://localhost:3000","https://app.estatio.app"]
EOF

success "Written: ${ENV_FILE}"

# ── 9. Write .github-secrets.txt ─────────────────────────────────────────────
step "Writing GitHub secrets reference file"

SECRETS_FILE="${REPO_ROOT}/.github-secrets.txt"

cat > "$SECRETS_FILE" <<EOF
# =============================================================================
# Estatio — GitHub Repository Secrets
# Generated by scripts/setup-gcp.sh on $(date)
#
# Go to: https://github.com/${GITHUB_REPO}/settings/secrets/actions
# Add each of the following as a "Repository secret"
#
# ⚠️  DELETE THIS FILE after you have added the secrets to GitHub.
#     Do NOT commit it.
# =============================================================================

WIF_PROVIDER=${WIF_PROVIDER_VALUE}

WIF_SERVICE_ACCOUNT=${WIF_SERVICE_ACCOUNT_VALUE}

GCP_PROJECT_ID=${GCP_PROJECT_ID}

MONGODB_URL=${MONGODB_URL}

GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}

GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}

APP_SECRET_KEY=${SECRET_KEY}

GEMINI_API_KEY=${GEMINI_API_KEY}

SENDGRID_API_KEY=${SENDGRID_API_KEY}
EOF

success "Written: ${SECRETS_FILE}"

# ── 10. Auto-set GitHub secrets (if gh CLI available) ─────────────────────────
step "GitHub Secrets — auto-upload"

if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  info "gh CLI detected and authenticated — uploading secrets automatically …"

  gh_set() {
    local name="$1"; local value="$2"
    if [[ -z "$value" ]]; then warn "Skipping empty secret: ${name}"; return; fi
    echo -n "$value" | gh secret set "$name" --repo="$GITHUB_REPO" --body=-
    success "  GitHub secret set: ${name}"
  }

  gh_set WIF_PROVIDER              "$WIF_PROVIDER_VALUE"
  gh_set WIF_SERVICE_ACCOUNT       "$WIF_SERVICE_ACCOUNT_VALUE"
  gh_set GCP_PROJECT_ID            "$GCP_PROJECT_ID"
  gh_set MONGODB_URL               "$MONGODB_URL"
  gh_set GOOGLE_CLIENT_ID          "$GOOGLE_CLIENT_ID"
  gh_set GOOGLE_CLIENT_SECRET      "$GOOGLE_CLIENT_SECRET"
  gh_set APP_SECRET_KEY            "$SECRET_KEY"
  gh_set GEMINI_API_KEY            "$GEMINI_API_KEY"
  gh_set SENDGRID_API_KEY          "$SENDGRID_API_KEY"

  success "All GitHub secrets uploaded automatically!"
else
  warn "gh CLI not found or not authenticated."
  warn "Manually add secrets from: ${SECRETS_FILE}"
  warn "Then delete that file."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║           ✅  Setup Complete!                        ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${RESET}"

echo -e "  ${BOLD}Summary${RESET}"
echo "  ──────────────────────────────────────────────────────"
echo -e "  GCP Project:        ${CYAN}${GCP_PROJECT_ID}${RESET}"
echo -e "  Artifact Registry:  ${CYAN}${REGISTRY_URL}/${GCP_PROJECT_ID}/${REGISTRY_REPO}${RESET}"
echo -e "  Documents bucket:   ${CYAN}gs://${DOCS_BUCKET}${RESET}"
echo -e "  Terraform bucket:   ${CYAN}gs://${TERRAFORM_BUCKET}${RESET}"
echo -e "  WIF Provider:       ${CYAN}${WIF_PROVIDER_VALUE}${RESET}"
echo -e "  CI/CD SA:           ${CYAN}${SA_EMAIL}${RESET}"
echo -e "  Backend SA:         ${CYAN}${BACKEND_SA}${RESET}"
echo ""
echo -e "  ${BOLD}Files written${RESET}"
echo -e "  • ${CYAN}backend/.env${RESET}          — local dev environment"
echo -e "  • ${CYAN}.github-secrets.txt${RESET}   — GitHub secrets reference (delete after use)"
echo ""
echo -e "  ${BOLD}Next steps${RESET}"
echo "  1. If gh CLI was NOT available, add secrets from .github-secrets.txt"
echo "     then DELETE that file."
echo "  2. Push to GitHub to trigger CI/CD:"
echo -e "     ${CYAN}git remote add origin https://github.com/${GITHUB_REPO}.git${RESET}"
echo -e "     ${CYAN}git push -u origin main${RESET}"
echo "  3. For local dev:"
echo -e "     ${CYAN}cd ${REPO_ROOT} && docker-compose up${RESET}"
echo ""
