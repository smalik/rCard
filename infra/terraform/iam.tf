# One service account per workload, each with only what it needs.

resource "google_service_account" "api" {
  account_id   = "plytos-api"
  display_name = "Plytos API (Cloud Run)"
}

resource "google_service_account" "web" {
  account_id   = "plytos-web"
  display_name = "Plytos web app (Cloud Run)"
}

resource "google_service_account" "migrate" {
  account_id   = "plytos-migrate"
  display_name = "Plytos database migrations"
}

resource "google_service_account" "deployer" {
  account_id   = "plytos-deployer"
  display_name = "Plytos deploys from GitHub Actions"
}

resource "google_project_iam_member" "api" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/cloudsql.instanceUser",
    "roles/aiplatform.user",
  ])
  project = var.project_id
  role    = each.value
  member  = google_service_account.api.member
}

resource "google_project_iam_member" "migrate" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/cloudsql.instanceUser",
  ])
  project = var.project_id
  role    = each.value
  member  = google_service_account.migrate.member
}

resource "google_project_iam_member" "deployer_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = google_service_account.deployer.member
}

resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deployer.member
}

# Deploys revise services that run as these accounts.
resource "google_service_account_iam_member" "deployer_acts_as" {
  for_each           = { api = google_service_account.api.name, web = google_service_account.web.name }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}

# Deploys run migrations as the migrate account through the Cloud SQL proxy.
resource "google_service_account_iam_member" "deployer_impersonates_migrate" {
  service_account_id = google_service_account.migrate.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = google_service_account.deployer.member
}

# GitHub Actions signs in with short-lived tokens, so no cloud key ever
# exists. Only the main branch of the one repository can deploy.
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "plytos-repo"
  display_name                       = "Plytos repository"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.repository_id"    = "assertion.repository_id"
    "attribute.ref"              = "assertion.ref"
    "attribute.repository_owner" = "assertion.repository_owner"
  }
  attribute_condition = "assertion.repository_id == '${var.github_repository_id}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_deploys_as_deployer" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.github_repository_id}"
}
