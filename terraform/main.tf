##############################################################################
# Estatio – Root Infrastructure Configuration
# Provider setup, API enablement, Artifact Registry, and GCS buckets.
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

  backend "gcs" {
    bucket = "estatio-terraform-state"
    prefix = "terraform/state"
  }
}

##############################################################################
# Providers
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
# Random suffix – appended to globally-unique resource names
##############################################################################

resource "random_id" "suffix" {
  byte_length = 4
}

##############################################################################
# GCP API Enablement
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

  project = var.project_id
  service = each.value

  # Prevent Terraform from disabling an API that may be shared with other
  # resources outside this configuration.
  disable_on_destroy         = false
  disable_dependent_services = false
}

##############################################################################
# Artifact Registry – Docker repository for container images
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
# GCS – Document / asset storage bucket
##############################################################################

resource "google_storage_bucket" "documents" {
  project  = var.project_id
  name     = var.documents_bucket_name
  location = upper(var.region)

  # Prevent accidental deletion when the bucket still contains objects.
  force_destroy = false

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
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age        = 90
      with_state = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  # Restrict access from known frontend origins.
  cors {
    origin          = ["https://${var.domain_name != null ? var.domain_name : "*"}"]
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
# GCS – Terraform remote-state bucket
# This bucket must exist before the first `terraform init`.  If bootstrapping
# from scratch, create it manually or use a local backend for the first run.
##############################################################################

resource "google_storage_bucket" "terraform_state" {
  project  = var.project_id
  name     = "estatio-terraform-state"
  location = upper(var.region)

  force_destroy = false

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    app         = var.app_name
    environment = var.environment
    managed_by  = "terraform"
    purpose     = "remote-state"
  }

  depends_on = [google_project_service.apis]
}
