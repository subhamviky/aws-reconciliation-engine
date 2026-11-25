# reconciliation-service on Google Cloud, free tier only (hub design note GCP-01).
#
# Cloud Run (scale to zero, one instance), state in the landscape's shared Firestore database
# (collections prefixed "recon_"), bank lines through Pub/Sub push with a dead-letter topic, and
# one Cloud Scheduler job for the feed poll, ledger retries and dead-letter reconciliation.
# The project-wide pieces (APIs, the (default) Firestore database, Artifact Registry, Workload
# Identity Federation) come from the landscape foundation (enterprise-finance-genai-assistant,
# infra/foundation). AWS stays in ../ (DynamoDB, SQS, Lambda). No secrets here.

terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "this" {}

locals {
  name         = "reconciliation-service"
  labels       = { app = "reconciliation-service", landscape = "finance-ai", managed-by = "terraform" }
  lines        = "recon-bank-lines"
  pubsub_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  # GCP-01, E2A v1.11.0: Cloud Run IAM verifies every caller's Google ID token; the deployment grants
  # each caller (email) this tenant and its roles. Calls to settlement carry this service's ID token.
  identity_env = {
    E2A_IDENTITY_SOURCE          = "gcp_cloud_run"
    E2A_IDENTITY_TRUSTED_ISSUERS = jsonencode(["https://accounts.google.com"])
    E2A_IDENTITY_SUBJECT_ROLES   = jsonencode(var.identity_subject_roles)
    E2A_WORKLOAD_IDENTITY        = "gcp_id_token"
  }
  llm_env = merge(
    { E2A_PROVIDER_PROFILE = var.llm_profile },
    var.llm_model_id == "" ? {} : { LLM_MODEL_ID = var.llm_model_id },
  )
}

# ------------------------------------------------------------------ identities
resource "google_service_account" "app" {
  account_id   = "recon-app"
  display_name = "reconciliation-service runtime"
}

resource "google_service_account" "push" {
  account_id   = "recon-push"
  display_name = "Pub/Sub push to reconciliation-service"
}

resource "google_service_account" "scheduler" {
  account_id   = "recon-scheduler"
  display_name = "Cloud Scheduler job of reconciliation-service"
}

resource "google_project_iam_member" "firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# ------------------------------------------------------------------ Pub/Sub
resource "google_pubsub_topic" "lines" {
  name                       = local.lines
  labels                     = local.labels
  message_retention_duration = "86400s"
}

resource "google_pubsub_topic" "lines_dlq" {
  name                       = "${local.lines}-dlq"
  labels                     = local.labels
  message_retention_duration = "604800s"
}

resource "google_pubsub_subscription" "lines" {
  name                       = local.lines
  topic                      = google_pubsub_topic.lines.id
  ack_deadline_seconds       = 60
  message_retention_duration = "86400s"
  labels                     = local.labels

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.app.uri}/pubsub/bank-lines"
    oidc_token {
      service_account_email = google_service_account.push.email
      audience              = google_cloud_run_v2_service.app.uri
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.lines_dlq.id
    max_delivery_attempts = var.max_delivery_attempts
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "300s"
  }
}

# The scheduled job reads dead letters here (pull) and replays only what never took effect.
resource "google_pubsub_subscription" "lines_dlq" {
  name                       = "${local.lines}-dlq"
  topic                      = google_pubsub_topic.lines_dlq.id
  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"
  labels                     = local.labels
}

resource "google_pubsub_topic_iam_member" "app_publishes_lines" {
  topic  = google_pubsub_topic.lines.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.app.email}"
}

resource "google_pubsub_topic_iam_member" "app_publishes_dead_letters" {
  topic  = google_pubsub_topic.lines_dlq.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.app.email}"
}

resource "google_pubsub_subscription_iam_member" "app_reads_dead_letters" {
  subscription = google_pubsub_subscription.lines_dlq.id
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.app.email}"
}

# Pub/Sub's own agent forwards a message to the dead-letter topic after max_delivery_attempts.
resource "google_pubsub_topic_iam_member" "agent_dead_letters" {
  topic  = google_pubsub_topic.lines_dlq.id
  role   = "roles/pubsub.publisher"
  member = local.pubsub_agent
}

resource "google_pubsub_subscription_iam_member" "agent_acks_source" {
  subscription = google_pubsub_subscription.lines.id
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_agent
}

# ------------------------------------------------------------------ Cloud Run
resource "google_cloud_run_v2_service" "app" {
  name                = local.name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL" # Pub/Sub push and Cloud Scheduler call it; IAM decides who may
  deletion_protection = false
  labels              = local.labels

  template {
    service_account = google_service_account.app.email
    timeout         = "60s"
    scaling {
      min_instance_count = 0 # scale to zero: Always Free
      max_instance_count = var.max_instance_count
    }
    containers {
      image = var.image
      ports {
        container_port = 8000
      }
      resources {
        cpu_idle = true # CPU only while a request is served
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
      dynamic "env" {
        for_each = merge(local.llm_env, local.identity_env, {
          RECON_STATE_BACKEND       = "firestore"
          GOOGLE_CLOUD_PROJECT      = var.project_id
          FIRESTORE_DATABASE        = var.firestore_database
          RECON_FIRESTORE_PREFIX    = "recon"
          PUBSUB_LINES_TOPIC        = google_pubsub_topic.lines.name
          PUBSUB_LINES_SUBSCRIPTION = local.lines
          SETTLEMENT_API_URL        = var.settlement_api_url
          RECON_TENANT              = var.tenant
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      # the Gemini Developer API key, only with the gemini_api profile (Secret Manager; never in state)
      dynamic "env" {
        for_each = var.gemini_api_key_secret == "" ? [] : [var.gemini_api_key_secret]
        content {
          name = "GEMINI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
      startup_probe {
        http_get {
          path = "/health"
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "push" {
  name     = google_cloud_run_v2_service.app.name
  location = google_cloud_run_v2_service.app.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.push.email}"
}

resource "google_cloud_run_v2_service_iam_member" "scheduler" {
  name     = google_cloud_run_v2_service.app.name
  location = google_cloud_run_v2_service.app.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = toset(var.invoker_members)
  name     = google_cloud_run_v2_service.app.name
  location = google_cloud_run_v2_service.app.location
  role     = "roles/run.invoker"
  member   = each.value
}

resource "google_secret_manager_secret_iam_member" "gemini_key" {
  count     = var.gemini_api_key_secret == "" ? 0 : 1
  secret_id = var.gemini_api_key_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app.email}"
}

# ------------------------------------------------------------------ Cloud Scheduler (1 of the 3 free jobs)
resource "google_cloud_scheduler_job" "scheduled" {
  name      = "recon-scheduled"
  region    = var.region
  schedule  = var.schedule
  time_zone = "Etc/UTC"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.app.uri}/jobs/scheduled"
    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = google_cloud_run_v2_service.app.uri
    }
  }

  retry_config {
    retry_count = 1
  }
}

output "url" {
  value = google_cloud_run_v2_service.app.uri
}

output "service_account" {
  value = google_service_account.app.email
}

output "bank_lines_topic" {
  value = google_pubsub_topic.lines.name
}
