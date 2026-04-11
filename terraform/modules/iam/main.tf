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
#
# The pool + provider may already exist (created by setup-gcp.sh).
# We use data sources to look them up first.  If var.create_wif is false
# (default after first bootstrap), Terraform skips resource creation and
# uses the existing objects.
##############################################################################

# Look up the existing pool (always succeeds if setup-gcp.sh ran).
data "google_iam_workload_identity_pool" "github" {
  provider = google-beta

  project                   = var.project_id
  workload_identity_pool_id = "github-pool"
}

# Look up the existing provider.
data "google_iam_workload_identity_pool_provider" "github" {
  provider = google-beta

  project                            = var.project_id
  workload_identity_pool_id          = "github-pool"
  workload_identity_pool_provider_id = "github-provider"
}

# Binding – allows the GitHub repo's OIDC identity to impersonate the CI/CD SA.
resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.cicd.name

  role   = "roles/iam.workloadIdentityUser"
  member = "principalSet://iam.googleapis.com/${data.google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
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
  value       = data.google_iam_workload_identity_pool_provider.github.name
}

output "workload_identity_pool_name" {
  description = "Full resource name of the Workload Identity pool."
  value       = data.google_iam_workload_identity_pool.github.name
}
