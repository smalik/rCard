# Postgres for cards. Only Cloud SQL connectors can reach it (no direct IP
# access), and services sign in with their IAM identity, so there is no
# database password anywhere.

resource "google_sql_database_instance" "main" {
  name                = "plytos"
  database_version    = "POSTGRES_18"
  region              = var.region
  deletion_protection = var.deletion_protection

  settings {
    tier                        = var.db_tier
    edition                     = "ENTERPRISE"
    availability_type           = "ZONAL"
    disk_autoresize             = true
    deletion_protection_enabled = var.deletion_protection
    retain_backups_on_delete    = true
    connector_enforcement       = "REQUIRED"

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      start_time                     = "08:00"

      backup_retention_settings {
        retained_backups = 14
      }
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    insights_config {
      query_insights_enabled  = true
      record_application_tags = false
      record_client_address   = false
    }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_sql_database" "plytos" {
  name     = "plytos"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "api" {
  name     = local.api_db_user
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

# Migrations create schemas and roles, so this user gets Cloud SQL's
# superuser group. The API user gets only plytos_app, granted by migrations.
resource "google_sql_user" "migrate" {
  name           = local.migrate_db_user
  instance       = google_sql_database_instance.main.name
  type           = "CLOUD_IAM_SERVICE_ACCOUNT"
  database_roles = ["cloudsqlsuperuser"]
}
