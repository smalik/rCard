# Google Cloud setup

Terraform for everything Plytos runs on: Cloud Run (web app and API), Cloud SQL
for Postgres 18, Cloud KMS, a private Storage bucket, Artifact Registry, and
the identity GitHub Actions deploys with. No cloud keys or database passwords
exist: services sign in with their service accounts. The one outside
credential, the Claude API key, lives in Secret Manager.

## One-time bootstrap

1. Create a GCP project inside your Google Workspace or Cloud Identity
   organization, and link it to a billing account. Inside an organization,
   IAP signs people in with a Google-managed OAuth client, so there is no
   consent screen to set up; it can then let in only accounts from that
   organization.
2. Sign in: `gcloud auth login && gcloud auth application-default login`.
3. Turn on the services the first apply leans on, and make IAP's service
   agent, which the web app's invoker grant names:

   ```sh
   PROJECT=<your-project-id>
   gcloud services enable cloudresourcemanager.googleapis.com iap.googleapis.com \
     secretmanager.googleapis.com --project "$PROJECT"
   gcloud beta services identity create --service=iap.googleapis.com --project "$PROJECT"
   ```

4. Create a bucket for Terraform state:

   ```sh
   gcloud storage buckets create "gs://$PROJECT-tfstate" --project "$PROJECT" \
     --location us-central1 --uniform-bucket-level-access --public-access-prevention
   gcloud storage buckets update "gs://$PROJECT-tfstate" --versioning
   ```

5. Apply in two steps, adding the Claude API key in between, so the API
   never starts without it and the key never passes through Terraform:

   ```sh
   cp terraform.tfvars.example terraform.tfvars   # set project_id and app_users
   terraform init -backend-config="bucket=$PROJECT-tfstate" -backend-config="prefix=plytos"
   terraform providers lock -platform=linux_amd64 -platform=darwin_arm64
   terraform apply -target=google_secret_manager_secret.anthropic_api_key
   read -rs KEY && printf %s "$KEY" | gcloud secrets versions add anthropic-api-key \
     --data-file=- --project "$PROJECT" && unset KEY
   terraform apply
   ```

   Commit the generated `.terraform.lock.hcl`. If the last apply stops with
   "Provider produced inconsistent final plan" for `plytos-web`, run
   `terraform apply` again: the web app's API address isn't known until the
   API exists, and the provider trips over that on a first build.

6. Check that `terraform output github_actions_variables` matches the names
   at the top of `.github/workflows/deploy.yml`. They are written there for
   rcard-dev; for another project, set each one as a repository variable of
   the same name (Settings, Secrets and variables, Actions, Variables), which
   wins over what the file says.
7. Run the **Deploy** workflow on `main` from the Actions tab. It builds both
   images, runs migrations through the Cloud SQL Auth Proxy, and updates both
   services. Its first run creates the `production` environment.

## Bringing someone over from the Supabase preview

`python -m plytos_api.transfer` copies one person, with everything they have,
from one database to another. Content moves still encrypted; only their data
key is unsealed with the preview's key and sealed again with KMS. Both
databases must be at the same migrations, so deploy first.

1. Sign in to the deployed app once. That makes an empty account under your
   IAP sign-in, which the copy replaces, and tells you your subject:
   `select auth_subject from plytos.app_user` on Cloud SQL. The running API
   remembers that empty account until one request finds it gone, so the
   first page after the copy may fail once; a reload shows the copy.
2. For the length of the copy, let your account reach the database as the
   migrations account and seal keys with the KMS key:

   ```sh
   ME=user:you@example.com
   MIGRATE=plytos-migrate@$PROJECT.iam.gserviceaccount.com
   gcloud iam service-accounts add-iam-policy-binding "$MIGRATE" \
     --member "$ME" --role roles/iam.serviceAccountTokenCreator --project "$PROJECT"
   gcloud kms keys add-iam-policy-binding user-data-kek --keyring plytos \
     --location us-central1 --member "$ME" \
     --role roles/cloudkms.cryptoKeyEncrypterDecrypter --project "$PROJECT"
   cloud-sql-proxy --auto-iam-authn --impersonate-service-account "$MIGRATE" \
     --port 5433 "$(terraform output -raw sql_connection_name)" &
   ```

3. Rehearse, then copy. Without `--commit` it does everything and keeps
   nothing; either way it prints only table names and row counts.

   ```sh
   export PLYTOS_TRANSFER_SOURCE_URL=...   # the preview's owner connection
   export PLYTOS_TRANSFER_SOURCE_KEK=...   # the preview's local: key
   DB_USER=${MIGRATE%.gserviceaccount.com}   # its @ is escaped in the URL below
   export PLYTOS_TRANSFER_TARGET_URL="postgresql://${DB_USER//@/%40}@127.0.0.1:5433/plytos?sslmode=disable"
   export PLYTOS_TRANSFER_TARGET_KEK="gcp-kms:projects/$PROJECT/locations/us-central1/keyRings/plytos/cryptoKeys/user-data-kek"
   cd ../../services/api
   uv run --extra gcp python -m plytos_api.transfer --from-subject dev:<you> --to-subject iap:accounts.google.com:<id>
   uv run --extra gcp python -m plytos_api.transfer --from-subject dev:<you> --to-subject iap:accounts.google.com:<id> --commit
   ```

4. Stop the proxy and remove both grants (`remove-iam-policy-binding` with
   the same arguments).

## What it costs while one person uses it

Everything scales to zero when nobody is using it. The standing costs are the
shared-core database (about $10 a month with storage and backups), plus a few
dollars for KMS, Artifact Registry, Secret Manager and logs; the API and web
app mostly fit in Cloud Run's free tier. Every labelled resource carries
`billing = var.billing_label` (default `rcard`). Move `db_tier` to a dedicated
tier before outside users: shared-core instances have no SLA.

## What talks to what

- Google's Identity-Aware Proxy stands in front of the web app. Only the
  accounts in `app_users` get through, and only IAP may invoke the service.
  IAP signs an assertion naming the person on every request; the web app
  checks its signature against Google's published keys (`src/lib/iap.ts`)
  and uses `iap:<subject>` as the person's sign-in until passkeys land.
- The web app calls the API with its service identity and names the person
  in `X-Plytos-Subject`. The API trusts that header only with
  `PLYTOS_SIGN_IN=iap`, which is safe because it accepts calls only from the
  web app's service account.
- The API reaches Postgres through a Cloud SQL Auth Proxy sidecar, signed in
  as its service account, and wraps data keys with the KMS key-encryption
  key. Its agents and resume reading run on threads inside it, with the
  Claude API key from Secret Manager.
- Cloud SQL accepts only connector connections (`connector_enforcement =
  REQUIRED`) over TLS.
- GitHub Actions can deploy only from `main` of this repository, matched by
  its numeric ID so a rename doesn't break it.
