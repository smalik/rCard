variable "project_id" {
  description = "The GCP project that holds everything Plytos runs on."
  type        = string
}

variable "region" {
  description = "Region for every regional resource. US only, since v1 serves the US labor market."
  type        = string
  default     = "us-central1"
}

variable "billing_label" {
  description = "Value of the billing label on every resource that takes labels."
  type        = string
  default     = "rcard"
}

variable "app_users" {
  description = "Who the sign-in gate lets in, as IAM members such as \"user:you@example.com\". With the Google-managed sign-in, only accounts in the project's organization can be added."
  type        = list(string)
  default     = []
}

variable "github_repository_id" {
  description = "Numeric ID of the GitHub repository allowed to deploy (smalik/rCard). IDs survive renames."
  type        = string
  default     = "62817016"
}

variable "api_image" {
  description = "Initial API image. Deploys replace it, and Terraform ignores later changes."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "web_image" {
  description = "Initial web image. Deploys replace it, and Terraform ignores later changes."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "cloud_sql_proxy_image" {
  description = "Cloud SQL Auth Proxy sidecar that signs the API in to Postgres with its service account."
  type        = string
  default     = "gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.14.1"
}

variable "db_tier" {
  description = "Cloud SQL machine tier. Shared-core is enough while one person uses it; move to a dedicated tier before outside users."
  type        = string
  default     = "db-f1-micro"
}

variable "deletion_protection" {
  description = "Guards the database against accidental terraform destroy."
  type        = bool
  default     = true
}
