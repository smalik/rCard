# Google Cloud setup

Terraform for everything Plytos runs on: Cloud Run (web app and API), Cloud SQL
for Postgres 18, Cloud KMS, a private Storage bucket, Artifact Registry, and
the identity GitHub Actions deploys with. No long-lived keys or database
passwords exist: services sign in with their service accounts.

## One-time bootstrap

1. Create a GCP project with billing turned on, and in Vertex AI's Model
   Garden enable the Claude models you plan to use.
2. Sign in: `gcloud auth login && gcloud auth application-default login`.
3. Create a bucket for Terraform state:

   ```sh
   PROJECT=<your-project-id>
   gcloud storage buckets create "gs://$PROJECT-tfstate" --project "$PROJECT" \
     --location us-central1 --uniform-bucket-level-access --public-access-prevention
   gcloud storage buckets update "gs://$PROJECT-tfstate" --versioning
   ```

4. Apply:

   ```sh
   cp terraform.tfvars.example terraform.tfvars   # set project_id
   terraform init -backend-config="bucket=$PROJECT-tfstate" -backend-config="prefix=plytos"
   terraform providers lock -platform=linux_amd64 -platform=darwin_arm64
   terraform apply
   ```

   Commit the generated `.terraform.lock.hcl`.

5. Copy each value from `terraform output github_actions_variables` into the
   repository's Actions variables (Settings, Secrets and variables, Actions,
   Variables), and create a `production` environment there.
6. Run the **Deploy** workflow from the Actions tab. It builds both images,
   runs migrations through the Cloud SQL Auth Proxy, and updates both services.

## What talks to what

- The web app is public (`allUsers` can invoke it) and serves only sign-in
  until passkeys land. It calls the API with its service identity.
- The API accepts calls only from the web app's service account. It reaches
  Postgres through a Cloud SQL Auth Proxy sidecar, signed in as its service
  account, and wraps data keys with the KMS key-encryption key.
- Cloud SQL accepts only connector connections (`connector_enforcement =
  REQUIRED`) over TLS.
- GitHub Actions can deploy only from `main` of this repository, matched by
  its numeric ID so a rename doesn't break it.
