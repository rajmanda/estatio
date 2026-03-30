##############################################################################
# Estatio – Root Outputs
##############################################################################

output "backend_service_url" {
  description = "Public HTTPS URL of the Estatio backend Cloud Run service."
  value       = module.cloudrun.backend_url
}

output "frontend_service_url" {
  description = "Public HTTPS URL of the Estatio frontend Cloud Run service."
  value       = module.cloudrun.frontend_url
}

output "documents_bucket_name" {
  description = "Name of the GCS bucket used for property documents and assets."
  value       = google_storage_bucket.documents.name
}

output "artifact_registry_url" {
  description = "Base URL of the Artifact Registry Docker repository (use as image prefix)."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.estatio_images.repository_id}"
}

output "backend_service_account_email" {
  description = "Email address of the backend Cloud Run service account."
  value       = module.iam.backend_sa_email
}

output "frontend_service_account_email" {
  description = "Email address of the frontend Cloud Run service account."
  value       = module.iam.frontend_sa_email
}

output "cicd_service_account_email" {
  description = "Email address of the CI/CD (GitHub Actions) service account."
  value       = module.iam.cicd_sa_email
}

output "workload_identity_provider" {
  description = "Full resource name of the Workload Identity provider for GitHub Actions OIDC auth."
  value       = module.iam.workload_identity_provider
}

output "terraform_state_bucket" {
  description = "Name of the GCS bucket holding Terraform remote state."
  value       = google_storage_bucket.terraform_state.name
}
