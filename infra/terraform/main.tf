locals {
  services = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudkms.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ]

  # Cloud SQL IAM database users are the service account email without the
  # ".gserviceaccount.com" suffix.
  api_db_user     = trimsuffix(google_service_account.api.email, ".gserviceaccount.com")
  migrate_db_user = trimsuffix(google_service_account.migrate.email, ".gserviceaccount.com")
}

resource "google_project_service" "enabled" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "plytos"
  location      = var.region
  format        = "DOCKER"
  description   = "Plytos container images"

  depends_on = [google_project_service.enabled]
}
