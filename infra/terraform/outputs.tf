output "web_url" {
  value = google_cloud_run_v2_service.web.uri
}

output "api_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "artifact_registry" {
  value = "${google_artifact_registry_repository.images.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "sql_connection_name" {
  value = google_sql_database_instance.main.connection_name
}

output "github_actions_variables" {
  description = "Set these as repository variables (Settings, Secrets and variables, Actions, Variables)."
  value = {
    GCP_PROJECT_ID         = var.project_id
    GCP_REGION             = var.region
    GCP_WIF_PROVIDER       = google_iam_workload_identity_pool_provider.github.name
    GCP_DEPLOYER_SA        = google_service_account.deployer.email
    GCP_MIGRATE_SA         = google_service_account.migrate.email
    GCP_SQL_INSTANCE       = google_sql_database_instance.main.connection_name
    PLYTOS_API_DB_USER     = local.api_db_user
    PLYTOS_MIGRATE_DB_USER = local.migrate_db_user
  }
}
