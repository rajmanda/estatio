##############################################################################
# Estatio – Root Input Variables
##############################################################################

# ---------------------------------------------------------------------------
# Project & deployment context
# ---------------------------------------------------------------------------

variable "project_id" {
  description = "The GCP project ID where all Estatio resources will be deployed."
  type        = string

  validation {
    condition     = length(var.project_id) > 0
    error_message = "project_id must be a non-empty string."
  }
}

variable "region" {
  description = "GCP region for all regional resources (Cloud Run, Artifact Registry, etc.)."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment. Must be one of: prod, staging, dev."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["prod", "staging", "dev"], var.environment)
    error_message = "environment must be one of: prod, staging, dev."
  }
}

variable "app_name" {
  description = "Short application name used as a label on all GCP resources."
  type        = string
  default     = "estatio"
}

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

variable "documents_bucket_name" {
  description = "Globally unique name for the GCS bucket used to store property documents and assets."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9_.-]{1,61}[a-z0-9]$", var.documents_bucket_name))
    error_message = "documents_bucket_name must be a valid GCS bucket name (3-63 lowercase alphanumeric characters, hyphens, underscores, or dots)."
  }
}

# ---------------------------------------------------------------------------
# Secrets / sensitive configuration
# ---------------------------------------------------------------------------

variable "mongodb_connection_string" {
  description = "MongoDB Atlas (or self-hosted) connection string. Stored in Secret Manager."
  type        = string
  sensitive   = true
}

variable "google_client_id" {
  description = "Google OAuth 2.0 client ID for user authentication. Stored in Secret Manager."
  type        = string
  sensitive   = true
}

variable "google_client_secret" {
  description = "Google OAuth 2.0 client secret. Stored in Secret Manager."
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "Application secret key used for session signing / JWT. Stored in Secret Manager."
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key. Optional – leave empty to skip secret creation."
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "Google Gemini API key. Optional – leave empty to skip secret creation."
  type        = string
  sensitive   = true
  default     = ""
}

# ---------------------------------------------------------------------------
# Container images
# ---------------------------------------------------------------------------

variable "backend_image" {
  description = "Full Artifact Registry image path for the backend service, e.g. us-central1-docker.pkg.dev/PROJECT/estatio-images/backend:latest"
  type        = string
}

variable "frontend_image" {
  description = "Full Artifact Registry image path for the frontend service, e.g. us-central1-docker.pkg.dev/PROJECT/estatio-images/frontend:latest"
  type        = string
}

# ---------------------------------------------------------------------------
# Cloud Run scaling
# ---------------------------------------------------------------------------

variable "backend_min_instances" {
  description = "Minimum number of backend Cloud Run instances. Set to 1 to eliminate cold starts in production."
  type        = number
  default     = 0

  validation {
    condition     = var.backend_min_instances >= 0
    error_message = "backend_min_instances must be >= 0."
  }
}

variable "backend_max_instances" {
  description = "Maximum number of backend Cloud Run instances."
  type        = number
  default     = 10

  validation {
    condition     = var.backend_max_instances >= 1
    error_message = "backend_max_instances must be >= 1."
  }
}

variable "frontend_min_instances" {
  description = "Minimum number of frontend Cloud Run instances."
  type        = number
  default     = 0

  validation {
    condition     = var.frontend_min_instances >= 0
    error_message = "frontend_min_instances must be >= 0."
  }
}

variable "frontend_max_instances" {
  description = "Maximum number of frontend Cloud Run instances."
  type        = number
  default     = 5

  validation {
    condition     = var.frontend_max_instances >= 1
    error_message = "frontend_max_instances must be >= 1."
  }
}

# ---------------------------------------------------------------------------
# Networking / DNS (optional)
# ---------------------------------------------------------------------------

variable "domain_name" {
  description = "Custom domain name for the frontend (e.g. app.estatio.io). Optional – if omitted the Cloud Run default URL is used."
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# CI/CD (GitHub Actions Workload Identity)
# ---------------------------------------------------------------------------

variable "github_repo" {
  description = "GitHub repository in 'owner/repo' format used to scope the Workload Identity binding."
  type        = string
  default     = ""
}
