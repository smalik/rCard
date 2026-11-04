# Private files: sent snapshots, voice notes and photos. Never public;
# served only through short-lived signed URLs.

resource "google_storage_bucket" "vault" {
  name                        = "${var.project_id}-plytos-vault"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  # Files older than a year move to a colder, cheaper class.
  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_storage_bucket_iam_member" "api_files" {
  bucket = google_storage_bucket.vault.name
  role   = "roles/storage.objectAdmin"
  member = google_service_account.api.member
}
