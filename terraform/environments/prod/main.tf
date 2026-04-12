##############################################################################
# Estatio – Production Environment Root Module
#
# This is the entry-point for `terraform apply` in the production environment.
# It wires together the iam, secrets, and cloudrun child modules and passes
# the shared root infrastructure outputs as inputs.
#
# Usage:
#   cd terraform/environments/prod
#   cp terraform.tfvars.example terraform.tfvars   # fill in real values
#   terraform init
#   terraform plan
#   terraform apply
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
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state is stored in the bucket created by the root main.tf.
  # On first bootstrap use a local backend, apply the root module to create
  # the bucket, then migrate state with `terraform init -migrate-state`.
  backend "gcs" {
    bucket = "estatio-terraform-state"
    prefix = "environments/prod"
  }
}

##############################################################################
# Providers (inherit project / region from tfvars)
##############################################################################

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

provider "random" {}

##############################################################################
# GCP API Enablement
# (Repeated here so the env module is self-contained when run independently.)
##############################################################################

locals {
  required_apis = [
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "compute.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.required_apis)

  project                    = var.project_id
  service                    = each.value
  disable_on_destroy         = false
  disable_dependent_services = false
}

##############################################################################
# Artifact Registry – Docker repository
##############################################################################

resource "google_artifact_registry_repository" "estatio_images" {
  provider = google-beta

  project       = var.project_id
  location      = var.region
  repository_id = "estatio-images"
  description   = "Docker images for the Estatio platform (${var.environment})"
  format        = "DOCKER"

  docker_config {
    immutable_tags = false
  }

  labels = {
    app         = var.app_name
    environment = var.environment
    managed_by  = "terraform"
  }

  depends_on = [google_project_service.apis]
}

##############################################################################
# GCS – Document storage bucket
##############################################################################

resource "random_id" "suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "documents" {
  project  = var.project_id
  name     = var.documents_bucket_name
  location = upper(var.region)

  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 3
      with_state         = "ARCHIVED"
    }
    action { type = "Delete" }
  }

  lifecycle_rule {
    condition {
      age        = 90
      with_state = "ARCHIVED"
    }
    action { type = "Delete" }
  }

  cors {
    origin          = [var.domain_name != null ? "https://${var.domain_name}" : "*"]
    method          = ["GET", "HEAD", "PUT", "POST", "DELETE"]
    response_header = ["*"]
    max_age_seconds = 3600
  }

  labels = {
    app         = var.app_name
    environment = var.environment
    managed_by  = "terraform"
  }

  depends_on = [google_project_service.apis]
}

##############################################################################
# Module: IAM
# Creates service accounts and Workload Identity Federation for GitHub Actions.
##############################################################################

module "iam" {
  source = "../../modules/iam"

  project_id  = var.project_id
  github_repo = var.github_repo
}

##############################################################################
# Module: Secrets
# Stores sensitive configuration in Secret Manager and grants the backend SA
# read access.
##############################################################################

module "secrets" {
  source = "../../modules/secrets"

  project_id           = var.project_id
  backend_sa_email     = module.iam.backend_sa_email
  mongodb_url          = var.mongodb_connection_string
  secret_key           = var.secret_key
  google_client_id     = var.google_client_id
  google_client_secret = var.google_client_secret
  gcs_bucket_name      = google_storage_bucket.documents.name
  openai_api_key       = var.openai_api_key
  gemini_api_key       = var.gemini_api_key

  depends_on = [module.iam, google_project_service.apis]
}

##############################################################################
# Module: Cloud Run
# Deploys the backend API and frontend web services.
##############################################################################

module "cloudrun" {
  source = "../../modules/cloudrun"

  project_id        = var.project_id
  region            = var.region
  environment       = var.environment
  backend_image     = var.backend_image
  frontend_image    = var.frontend_image
  backend_sa_email  = module.iam.backend_sa_email
  frontend_sa_email = module.iam.frontend_sa_email
  gcs_bucket_name   = google_storage_bucket.documents.name
  secret_names      = module.secrets.secret_names

  google_redirect_uri = var.google_redirect_uri
  frontend_url        = var.frontend_url

  backend_min_instances  = var.backend_min_instances
  backend_max_instances  = var.backend_max_instances
  frontend_min_instances = var.frontend_min_instances
  frontend_max_instances = var.frontend_max_instances

  depends_on = [module.iam, module.secrets]
}

##############################################################################
# Variables (declared here so this env module is self-contained)
##############################################################################

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment (prod | staging | dev)."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["prod", "staging", "dev"], var.environment)
    error_message = "environment must be one of: prod, staging, dev."
  }
}

variable "app_name" {
  description = "Application name label."
  type        = string
  default     = "estatio"
}

variable "documents_bucket_name" {
  description = "Globally unique GCS bucket name for documents."
  type        = string
}

variable "mongodb_connection_string" {
  description = "MongoDB connection string (stored in Secret Manager)."
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

variable "secret_key" {
  description = "Application secret key for JWT signing."
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key (optional)."
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "Google Gemini API key (optional)."
  type        = string
  sensitive   = true
  default     = ""
}

variable "backend_image" {
  description = "Backend container image URI. Empty = use placeholder for initial creation."
  type        = string
  default     = ""
}

variable "frontend_image" {
  description = "Frontend container image URI. Empty = use placeholder for initial creation."
  type        = string
  default     = ""
}

variable "backend_min_instances" {
  description = "Backend minimum Cloud Run instances."
  type        = number
  default     = 1
}

variable "backend_max_instances" {
  description = "Backend maximum Cloud Run instances."
  type        = number
  default     = 10
}

variable "frontend_min_instances" {
  description = "Frontend minimum Cloud Run instances."
  type        = number
  default     = 0
}

variable "frontend_max_instances" {
  description = "Frontend maximum Cloud Run instances."
  type        = number
  default     = 5
}

variable "domain_name" {
  description = "Optional custom domain for the frontend."
  type        = string
  default     = null
}

variable "github_repo" {
  description = "GitHub repository for Workload Identity (owner/repo)."
  type        = string
  default     = ""
}

variable "google_redirect_uri" {
  description = "Google OAuth callback URI for the backend."
  type        = string
  default     = ""
}

variable "frontend_url" {
  description = "Public URL of the frontend."
  type        = string
  default     = ""
}

##############################################################################
# Outputs
##############################################################################

output "backend_service_url" {
  description = "Public HTTPS URL of the backend Cloud Run service."
  value       = module.cloudrun.backend_url
}

output "frontend_service_url" {
  description = "Public HTTPS URL of the frontend Cloud Run service."
  value       = module.cloudrun.frontend_url
}

output "documents_bucket_name" {
  description = "GCS bucket name for documents."
  value       = google_storage_bucket.documents.name
}

output "artifact_registry_url" {
  description = "Artifact Registry Docker repository base URL."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.estatio_images.repository_id}"
}

output "backend_service_account_email" {
  description = "Backend service account email."
  value       = module.iam.backend_sa_email
}

output "frontend_service_account_email" {
  description = "Frontend service account email."
  value       = module.iam.frontend_sa_email
}

output "cicd_service_account_email" {
  description = "CI/CD service account email for GitHub Actions."
  value       = module.iam.cicd_sa_email
}
