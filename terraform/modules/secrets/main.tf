##############################################################################
# Estatio – Secrets Module
#
# Flow:
#   1. GitHub Actions secrets hold the plaintext values.
#   2. The Terraform workflow passes them as TF_VAR_* env vars.
#   3. This module creates the Secret Manager resources and stores the values.
#   4. The backend Cloud Run SA is granted secretAccessor on each secret.
#
# To rotate a secret:
#   - Update the GitHub Actions secret value.
#   - Re-run the Terraform workflow (push to main or workflow_dispatch).
#   - Terraform will create a new secret version; previous versions are
#     preserved automatically for auditing.
#
# Design note:
#   Terraform forbids iterating `for_each` over sensitive values because the
#   map keys would leak into resource addresses. We solve this by keeping two
#   separate structures:
#     • secret_names  — a plain set of strings used for for_each
#     • secret_values — a sensitive map used only inside secret_data
##############################################################################

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

##############################################################################
# Locals
##############################################################################

locals {
  # Non-sensitive set of secret names — safe to use as for_each keys.
  core_secret_names = toset([
    "estatio-mongodb-url",
    "estatio-secret-key",
    "estatio-google-client-id",
    "estatio-google-client-secret",
    "estatio-gcs-bucket-name",
  ])

  optional_secret_names = toset(concat(
    var.gemini_api_key != "" ? ["estatio-gemini-api-key"] : [],
    var.openai_api_key != "" ? ["estatio-openai-api-key"] : [],
  ))

  all_secret_names = setunion(local.core_secret_names, local.optional_secret_names)

  # Sensitive map of name → value.  Only referenced inside secret_data,
  # never as a for_each key — so Terraform won't complain.
  secret_values = {
    "estatio-mongodb-url"          = var.mongodb_url
    "estatio-secret-key"           = var.secret_key
    "estatio-google-client-id"     = var.google_client_id
    "estatio-google-client-secret" = var.google_client_secret
    "estatio-gcs-bucket-name"      = var.gcs_bucket_name
    "estatio-gemini-api-key"       = var.gemini_api_key
    "estatio-openai-api-key"       = var.openai_api_key
  }
}

##############################################################################
# Secret Manager – secret resources (container objects, no data yet)
##############################################################################

resource "google_secret_manager_secret" "secrets" {
  for_each = local.all_secret_names

  project   = var.project_id
  secret_id = each.value

  replication {
    auto {}
  }

  labels = {
    app        = "estatio"
    managed-by = "terraform"
  }
}

##############################################################################
# Secret Manager – secret versions (the actual plaintext values)
##############################################################################

resource "google_secret_manager_secret_version" "versions" {
  for_each = local.all_secret_names

  secret      = google_secret_manager_secret.secrets[each.value].id
  secret_data = local.secret_values[each.value]
}

##############################################################################
# IAM – grant the backend service account secretAccessor on every secret
##############################################################################

resource "google_secret_manager_secret_iam_member" "backend_accessor" {
  for_each = local.all_secret_names

  project   = var.project_id
  secret_id = google_secret_manager_secret.secrets[each.value].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.backend_sa_email}"
}

##############################################################################
# Variables
##############################################################################

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "backend_sa_email" {
  description = "Email of the backend service account that needs to read secrets."
  type        = string
}

variable "mongodb_url" {
  description = "MongoDB connection string."
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "JWT / session signing key."
  type        = string
  sensitive   = true
}

variable "google_client_id" {
  description = "Google OAuth 2.0 client ID."
  type        = string
  sensitive   = true
}

variable "google_client_secret" {
  description = "Google OAuth 2.0 client secret."
  type        = string
  sensitive   = true
}

variable "gcs_bucket_name" {
  description = "GCS bucket name (stored as a secret so the backend reads it at runtime)."
  type        = string
}

variable "gemini_api_key" {
  description = "Google Gemini API key. Leave empty to skip creation."
  type        = string
  sensitive   = true
  default     = ""
}

variable "openai_api_key" {
  description = "OpenAI API key. Leave empty to skip creation."
  type        = string
  sensitive   = true
  default     = ""
}

##############################################################################
# Outputs
##############################################################################

output "secret_ids" {
  description = "Map of secret name to full Secret Manager resource ID."
  value       = { for k, v in google_secret_manager_secret.secrets : k => v.id }
}

output "secret_names" {
  description = "Map of secret name to short secret_id (used in Cloud Run --set-secrets)."
  value       = { for k, v in google_secret_manager_secret.secrets : k => v.secret_id }
}
