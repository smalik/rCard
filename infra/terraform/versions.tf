terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.10"
    }
  }

  # State lives in a GCS bucket you create once by hand (see README.md):
  #   terraform init -backend-config="bucket=<project>-tfstate" -backend-config="prefix=plytos"
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}
