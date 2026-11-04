# The key-encryption key that wraps each person's own data key. Destroying a
# person's wrapped data key erases their content everywhere (crypto-shredding).

resource "google_kms_key_ring" "plytos" {
  name     = "plytos"
  location = var.region

  depends_on = [google_project_service.enabled]
}

resource "google_kms_crypto_key" "user_kek" {
  name            = "user-data-kek"
  key_ring        = google_kms_key_ring.plytos.id
  purpose         = "ENCRYPT_DECRYPT"
  rotation_period = "7776000s" # 90 days

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key_iam_member" "api_wraps_keys" {
  crypto_key_id = google_kms_crypto_key.user_kek.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = google_service_account.api.member
}
