##############################################################################
# Estatio – Secrets Module
# Creates Secret Manager secrets, stores their initial values, and grants
# the backend service account read access to each secret.
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
# Local helpers
##############################################################################

locals {
  # Core secrets that are always required.
  core_secrets = {
    "estatio-mongodb-url"           = var.mongodb_url
    "estatio-secret-key"            = var.secret_key
    "estatio-google-client-id"      = var.google_client_id
    "estatio-google-client-secret"  = var.google_client_secret
    "estatio-gcs-bucket-name"       = var.gcs_bucket_name
  }

  # Optional AI secrets – only created when a non-empty value is supplied.
  optional_secrets = {
    for k, v in {
      "estatio-openai-api-key"  = var.openai_api_key
      "estatio-gemini-api-key"  = var.gemini_api_key
    } : k => v if v != null && v != ""
  }

  # All secrets merged for iteration.
  all_secrets = merge(local.core_secrets, local.optional_secrets)
}

##############################################################################
# Secret Manager – create secret resources
##############################################################################

resource "google_secret_manager_secret" "secrets" {
  for_each = local.all_secrets

  project   = var.project_id
  secret_id = each.key

  replication {
    auto {}
  }

  labels = {
    app        = "estatio"
    managed_by = "terraform"
  }
}

##############################################################################
# Secret Manager – store secret values (initial version)
##############################################################################

resource "google_secret_manager_secret_version" "versions" {
  for_each = local.all_secrets

  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = each.value

  # Changing the secret value in tfvars will automatically create a new
  # version.  The previous version is NOT automatically destroyed to preserve
  # an audit trail; destroy it manually if required.
  lifecycle {
    # Prevent Terraform plan noise when the sensitive value hasn't changed.
    ignore_changes = [secret_data]
  }
}

##############################################################################
# IAM – grant the backend SA the ability to read all secrets
##############################################################################

resource "google_secret_manager_secret_iam_member" "backend_accessor" {
  for_each = local.all_secrets

  project   = var.project_id
  secret_id = google_secret_manager_secret.secrets[each.key].secret_id
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
  description = "Email address of the backend service account that needs secret access."
  type        = string
}

variable "mongodb_url" {
  description = "MongoDB connection string."
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "Application secret / JWT signing key."
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
  description = "GCS bucket name to store as a secret (read by the backend at runtime)."
  type        = string
}

variable "openai_api_key" {
  description = "OpenAI API key. Leave empty to skip secret creation."
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "Google Gemini API key. Leave empty to skip secret creation."
  type        = string
  sensitive   = true
  default     = ""
}

##############################################################################
# Outputs
##############################################################################

output "secret_ids" {
  description = "Map of secret name to Secret Manager resource ID."
  value = {
    for k, v in google_secret_manager_secret.secrets : k => v.id
  }
}

output "secret_names" {
  description = "Map of secret name to the short secret_id (used for Cloud Run secret references)."
  value = {
    for k, v in google_secret_manager_secret.secrets : k => v.secret_id
  }
}
