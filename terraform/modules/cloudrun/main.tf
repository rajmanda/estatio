##############################################################################
# Estatio – Cloud Run Module
# Deploys the backend API and frontend web services as Cloud Run services.
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
  # Base labels applied to both services.
  common_labels = {
    app        = "estatio"
    managed_by = "terraform"
    region     = var.region
  }

  # Google's official Cloud Run placeholder — a tiny "Hello" container.
  # Used for initial creation when real images haven't been built yet.
  # The CI/CD pipelines replace this on their first deploy, and
  # ignore_changes on the image field keeps Terraform from reverting it.
  placeholder_image = "us-docker.pkg.dev/cloudrun/container/hello:latest"

  backend_image  = var.backend_image != "" ? var.backend_image : local.placeholder_image
  frontend_image = var.frontend_image != "" ? var.frontend_image : local.placeholder_image
}

##############################################################################
# Backend – estatio-api
##############################################################################

resource "google_cloud_run_v2_service" "backend" {
  project  = var.project_id
  name     = "estatio-api"
  location = var.region

  # Allow direct HTTPS traffic (no VPC connector required for public APIs).
  ingress = "INGRESS_TRAFFIC_ALL"

  labels = merge(local.common_labels, { tier = "backend" })

  template {
    service_account = var.backend_sa_email

    # Scaling boundaries.
    scaling {
      min_instance_count = var.backend_min_instances
      max_instance_count = var.backend_max_instances
    }

    # Per-instance resource limits.
    containers {
      image = local.backend_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # Allow CPU to be allocated only during request processing
        # (cost optimisation for low-traffic environments).
        cpu_idle          = true
        startup_cpu_boost = true
      }

      # Maximum concurrent requests served by a single instance.
      # 80 is the Cloud Run default; tune based on observed latency.
      # (set on the template, not per-container – see annotation below)

      # ----------------------------------------------------------------
      # Plain environment variables (non-sensitive)
      # ----------------------------------------------------------------
      env {
        name  = "APP_ENV"
        value = var.environment
      }

      env {
        name  = "GCS_PROJECT_ID"
        value = var.project_id
      }

      # GCS_BUCKET_NAME is also exposed via Secret Manager for consistency,
      # but having it as a plain env var allows the app to start even before
      # the secret version is accessible.
      env {
        name  = "GCS_BUCKET_NAME"
        value = var.gcs_bucket_name
      }

      # ----------------------------------------------------------------
      # Secret-backed environment variables
      # Each secret must exist in Secret Manager before deployment.
      # ----------------------------------------------------------------
      env {
        name = "MONGODB_URL"
        value_source {
          secret_key_ref {
            secret  = var.secret_names["estatio-mongodb-url"]
            version = "latest"
          }
        }
      }

      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = var.secret_names["estatio-secret-key"]
            version = "latest"
          }
        }
      }

      env {
        name = "GOOGLE_CLIENT_ID"
        value_source {
          secret_key_ref {
            secret  = var.secret_names["estatio-google-client-id"]
            version = "latest"
          }
        }
      }

      env {
        name = "GOOGLE_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = var.secret_names["estatio-google-client-secret"]
            version = "latest"
          }
        }
      }

      # Optional AI secrets – only injected when the secrets exist.
      dynamic "env" {
        for_each = contains(keys(var.secret_names), "estatio-openai-api-key") ? [1] : []
        content {
          name = "OPENAI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = var.secret_names["estatio-openai-api-key"]
              version = "latest"
            }
          }
        }
      }

      dynamic "env" {
        for_each = contains(keys(var.secret_names), "estatio-gemini-api-key") ? [1] : []
        content {
          name = "GEMINI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = var.secret_names["estatio-gemini-api-key"]
              version = "latest"
            }
          }
        }
      }

      # ----------------------------------------------------------------
      # Health check – Cloud Run startup probe
      # ----------------------------------------------------------------
      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 5
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 0
        timeout_seconds       = 3
        period_seconds        = 30
        failure_threshold     = 3
      }

      ports {
        container_port = 8080
        name           = "http1"
      }
    }

    # Request concurrency (Cloud Run v2 is per-template).
    max_instance_request_concurrency = 80

    # Allow 60 seconds for a cold start before Cloud Run kills the instance.
    timeout = "60s"
  }

  # Route 100% of traffic to the latest ready revision.
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    # Prevent Terraform from blocking deployments triggered by CI/CD pipelines
    # that update the image tag externally.
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

# Allow unauthenticated (public) invocations of the backend API.
resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

##############################################################################
# Frontend – estatio-web
##############################################################################

resource "google_cloud_run_v2_service" "frontend" {
  project  = var.project_id
  name     = "estatio-web"
  location = var.region

  ingress = "INGRESS_TRAFFIC_ALL"

  labels = merge(local.common_labels, { tier = "frontend" })

  template {
    service_account = var.frontend_sa_email

    scaling {
      min_instance_count = var.frontend_min_instances
      max_instance_count = var.frontend_max_instances
    }

    containers {
      image = local.frontend_image

      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "VITE_API_URL"
        value = google_cloud_run_v2_service.backend.uri
      }

      env {
        name  = "APP_ENV"
        value = var.environment
      }

      startup_probe {
        http_get {
          path = "/"
          port = 8080
        }
        initial_delay_seconds = 3
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 5
      }

      liveness_probe {
        http_get {
          path = "/"
          port = 8080
        }
        initial_delay_seconds = 0
        timeout_seconds       = 3
        period_seconds        = 30
        failure_threshold     = 3
      }

      ports {
        container_port = 8080
        name           = "http1"
      }
    }

    max_instance_request_concurrency = 80
    timeout                          = "30s"
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  # Frontend depends on the backend being ready so VITE_API_URL resolves.
  depends_on = [google_cloud_run_v2_service.backend]
}

# Allow unauthenticated (public) access to the frontend.
resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

##############################################################################
# Variables
##############################################################################

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run services."
  type        = string
}

variable "environment" {
  description = "Deployment environment (prod | staging | dev)."
  type        = string
}

variable "backend_image" {
  description = "Full container image reference for the backend service. Falls back to a placeholder for initial creation."
  type        = string
  default     = ""
}

variable "frontend_image" {
  description = "Full container image reference for the frontend service. Falls back to a placeholder for initial creation."
  type        = string
  default     = ""
}

variable "backend_sa_email" {
  description = "Service account email for the backend Cloud Run service."
  type        = string
}

variable "frontend_sa_email" {
  description = "Service account email for the frontend Cloud Run service."
  type        = string
}

variable "gcs_bucket_name" {
  description = "GCS bucket name injected as GCS_BUCKET_NAME environment variable."
  type        = string
}

variable "secret_names" {
  description = "Map of logical secret name to Secret Manager secret_id, as produced by the secrets module."
  type        = map(string)
}

variable "backend_min_instances" {
  description = "Minimum backend instances."
  type        = number
  default     = 0
}

variable "backend_max_instances" {
  description = "Maximum backend instances."
  type        = number
  default     = 10
}

variable "frontend_min_instances" {
  description = "Minimum frontend instances."
  type        = number
  default     = 0
}

variable "frontend_max_instances" {
  description = "Maximum frontend instances."
  type        = number
  default     = 5
}

##############################################################################
# Outputs
##############################################################################

output "backend_url" {
  description = "HTTPS URL of the backend Cloud Run service."
  value       = google_cloud_run_v2_service.backend.uri
}

output "frontend_url" {
  description = "HTTPS URL of the frontend Cloud Run service."
  value       = google_cloud_run_v2_service.frontend.uri
}

output "backend_service_name" {
  description = "Cloud Run service name for the backend (used in gcloud deploy commands)."
  value       = google_cloud_run_v2_service.backend.name
}

output "frontend_service_name" {
  description = "Cloud Run service name for the frontend."
  value       = google_cloud_run_v2_service.frontend.name
}
