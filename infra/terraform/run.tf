# The web app is the only front door, and Google's Identity-Aware Proxy (IAP)
# stands in front of it: only the people in var.app_users get through. The API
# accepts calls only from the web app's service account, so there is no public
# API.

locals {
  web_service_name = "plytos-web"
  # What IAP puts in the "aud" claim of the assertion it signs for the web app.
  iap_audience = "/projects/${data.google_project.this.number}/locations/${var.region}/services/${local.web_service_name}"
  iap_agent    = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-iap.iam.gserviceaccount.com"
}

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
      # The web app names the person IAP let in; only it can call the API.
      env {
        name  = "PLYTOS_SIGN_IN"
        value = "iap"
      }
      # One service while one person uses it: the agents and resume reading
      # run on threads inside the API instead of a worker service of their own.
      env {
        name  = "PLYTOS_AGENTS_INLINE"
        value = "true"
      }
      env {
        name  = "PLYTOS_AI_PROVIDER"
        value = "anthropic"
      }
      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_api_key.secret_id
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # The agents and resume reading run on background threads, which need
        # CPU between requests. Instances still scale to zero when idle.
        cpu_idle          = false
        startup_cpu_boost = true
      }
    }

    # Signs in to Postgres as the API's service account. The connection
    # from the API to the proxy never leaves the instance: Postgres listens on
    # loopback only. Cloud Run's probes don't arrive over loopback, so the
    # proxy answers its health checks on a separate port.
    containers {
      name  = "cloud-sql-proxy"
      image = var.cloud_sql_proxy_image
      args = [
        "--auto-iam-authn",
        "--structured-logs",
        "--address=127.0.0.1",
        "--port=5432",
        "--health-check",
        "--http-address=0.0.0.0",
        "--http-port=9090",
        google_sql_database_instance.main.connection_name,
      ]

      startup_probe {
        http_get {
          path = "/startup"
          port = 9090
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

  depends_on = [
    google_project_iam_member.api,
    google_secret_manager_secret_iam_member.api_reads_anthropic_key,
  ]
}

resource "google_cloud_run_v2_service" "web" {
  name                = local.web_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection
  iap_enabled         = true

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
      # The web app checks IAP's signed assertion itself (src/lib/iap.ts)
      # rather than trusting plain headers.
      env {
        name  = "PLYTOS_SIGN_IN"
        value = "iap"
      }
      env {
        name  = "PLYTOS_IAP_AUDIENCE"
        value = local.iap_audience
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
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

  depends_on = [google_project_service.enabled]
}

resource "google_cloud_run_v2_service_iam_member" "web_calls_api" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = google_service_account.web.member
}

# Only IAP may invoke the web app; nobody reaches it without passing the gate.
resource "google_cloud_run_v2_service_iam_member" "iap_reaches_web" {
  name     = google_cloud_run_v2_service.web.name
  location = google_cloud_run_v2_service.web.location
  role     = "roles/run.invoker"
  member   = local.iap_agent
}

# The people IAP lets through.
resource "google_iap_web_cloud_run_service_iam_member" "app_users" {
  for_each               = toset(var.app_users)
  location               = google_cloud_run_v2_service.web.location
  cloud_run_service_name = google_cloud_run_v2_service.web.name
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = each.value
}
