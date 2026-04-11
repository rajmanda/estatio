##############################################################################
# Estatio – IAM Module
# Service accounts and project-level role bindings.
#
# Workload Identity Federation (WIF) is managed outside Terraform
# (created by setup-gcp.sh). The pool, provider, and SA binding already
# exist and are working — Terraform only manages the service accounts
# and their project-level IAM roles.
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
  backend_roles = [
    "roles/run.invoker",
    "roles/storage.objectAdmin",
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ]

  frontend_roles = [
    "roles/run.invoker",
  ]

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
  description  = "Impersonated by GitHub Actions via Workload Identity Federation."
}

resource "google_project_iam_member" "cicd" {
  for_each = toset(local.cicd_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

##############################################################################
# Variables
##############################################################################

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository in 'owner/repo' format (e.g. acme/estatio). Kept for interface compatibility."
  type        = string
  default     = ""
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
