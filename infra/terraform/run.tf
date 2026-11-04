# The web app is the only front door. The API accepts calls only from the
# web app's service account, so there is no public API.

resource "google_cloud_run_v2_service" "api" {
  name                = "plytos-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection

  template {
    service_account = google_service_account.api.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      name       = "api"
      image      = var.api_image
      depends_on = ["cloud-sql-proxy"]

      ports {
        container_port = 8080
      }

      env {
        name  = "PLYTOS_ENV"
        value = "prod"
      }
      env {
        name  = "PLYTOS_DATABASE_URL"
        value = "postgresql://${urlencode(local.api_db_user)}@127.0.0.1:5432/${google_sql_database.plytos.name}?sslmode=disable"
      }
      env {
        name  = "PLYTOS_KEK"
        value = "gcp-kms:${google_kms_crypto_key.user_kek.id}"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # The API reads uploaded resumes on a background thread, which needs CPU
        # between requests. Instances still scale to zero when idle.
        cpu_idle = false
      }
    }

    # Signs in to Postgres as the API's service account. The connection
    # from the API to the proxy never leaves the instance.
    containers {
      name  = "cloud-sql-proxy"
      image = var.cloud_sql_proxy_image
      args = [
        "--auto-iam-authn",
        "--structured-logs",
        "--address=127.0.0.1",
        "--port=5432",
        google_sql_database_instance.main.connection_name,
      ]

      startup_probe {
        tcp_socket {
          port = 5432
        }
        period_seconds    = 1
        failure_threshold = 30
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [google_project_iam_member.api]
}

resource "google_cloud_run_v2_service" "web" {
  name                = "plytos-web"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection

  template {
    service_account = google_service_account.web.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.web_image

      ports {
        container_port = 8080
      }

      env {
        name  = "PLYTOS_ENV"
        value = "prod"
      }
      env {
        name  = "PLYTOS_API_URL"
        value = google_cloud_run_v2_service.api.uri
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "web_calls_api" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = google_service_account.web.member
}

resource "google_cloud_run_v2_service_iam_member" "web_is_reachable" {
  name     = google_cloud_run_v2_service.web.name
  location = google_cloud_run_v2_service.web.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
