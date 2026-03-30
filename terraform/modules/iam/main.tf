##############################################################################
# Estatio – IAM Module
# Service accounts, project-level role bindings, and Workload Identity
# Federation for GitHub Actions CI/CD.
##############################################################################

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}

##############################################################################
# Local helpers
##############################################################################

locals {
  # Backend SA needs broad permissions to serve requests, write to GCS,
  # access secrets, and emit telemetry.
  backend_roles = [
    "roles/run.invoker",
    "roles/storage.objectAdmin",
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ]

  # Frontend SA only needs the ability to invoke Cloud Run (backend calls).
  frontend_roles = [
    "roles/run.invoker",
  ]

  # CI/CD SA needs broad deployment rights scoped to this project.
  cicd_roles = [
    "roles/run.admin",
    "roles/storage.admin",
    "roles/artifactregistry.writer",
    "roles/iam.serviceAccountUser",
    "roles/secretmanager.secretAccessor",
  ]
}

##############################################################################
# Service Account – Backend (estatio-api Cloud Run)
##############################################################################

resource "google_service_account" "backend" {
  project      = var.project_id
  account_id   = "estatio-backend-sa"
  display_name = "Estatio Backend Service Account"
  description  = "Runtime identity for the estatio-api Cloud Run service."
}

resource "google_project_iam_member" "backend" {
  for_each = toset(local.backend_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.backend.email}"
}

##############################################################################
# Service Account – Frontend (estatio-web Cloud Run)
##############################################################################

resource "google_service_account" "frontend" {
  project      = var.project_id
  account_id   = "estatio-frontend-sa"
  display_name = "Estatio Frontend Service Account"
  description  = "Runtime identity for the estatio-web Cloud Run service."
}

resource "google_project_iam_member" "frontend" {
  for_each = toset(local.frontend_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.frontend.email}"
}

##############################################################################
# Service Account – CI/CD (GitHub Actions)
##############################################################################

resource "google_service_account" "cicd" {
  project      = var.project_id
  account_id   = "estatio-cicd-sa"
  display_name = "Estatio CI/CD Service Account"
  description  = "Impersonated by GitHub Actions via Workload Identity Federation to deploy Estatio."
}

resource "google_project_iam_member" "cicd" {
  for_each = toset(local.cicd_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

##############################################################################
# Workload Identity Federation – GitHub Actions OIDC
##############################################################################

# Pool – a container for external identity providers.
resource "google_iam_workload_identity_pool" "github" {
  provider = google-beta

  project                   = var.project_id
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Workload Identity Pool for GitHub Actions OIDC tokens."
  disabled                  = false
}

# Provider – maps GitHub OIDC token claims to a Google identity.
resource "google_iam_workload_identity_pool_provider" "github" {
  provider = google-beta

  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Actions OIDC Provider"
  description                        = "Accepts OIDC tokens issued by GitHub Actions."

  attribute_mapping = {
    # Map standard OIDC claims to Google attributes.
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Restrict tokens to only the configured repository to prevent other GitHub
  # repos from impersonating this service account.
  attribute_condition = "assertion.repository == \"${var.github_repo}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Binding – allows the GitHub repo's OIDC identity to impersonate the CI/CD SA.
resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.cicd.name

  # The principalSet matches any token whose repository attribute equals
  # var.github_repo, so all workflow runs in that repo can authenticate.
  role   = "roles/iam.workloadIdentityUser"
  member = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

##############################################################################
# Variables
##############################################################################

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository in 'owner/repo' format (e.g. acme/estatio)."
  type        = string

  validation {
    condition     = can(regex("^[\\w.-]+/[\\w.-]+$", var.github_repo))
    error_message = "github_repo must be in 'owner/repo' format."
  }
}

##############################################################################
# Outputs
##############################################################################

output "backend_sa_email" {
  description = "Email of the backend service account."
  value       = google_service_account.backend.email
}

output "frontend_sa_email" {
  description = "Email of the frontend service account."
  value       = google_service_account.frontend.email
}

output "cicd_sa_email" {
  description = "Email of the CI/CD service account."
  value       = google_service_account.cicd.email
}

output "workload_identity_provider" {
  description = "Full resource name of the Workload Identity provider, used in GitHub Actions 'with: workload_identity_provider'."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "workload_identity_pool_name" {
  description = "Full resource name of the Workload Identity pool."
  value       = google_iam_workload_identity_pool.github.name
}
