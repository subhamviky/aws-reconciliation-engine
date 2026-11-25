# Plans infra/gcp against a mocked google provider: no project, no credentials (GCP-01).
mock_provider "google" {
  mock_data "google_project" {
    defaults = {
      number = "123456789012"
    }
  }
}

variables {
  project_id      = "demo-project"
  invoker_members = ["serviceAccount:assistant@demo-project.iam.gserviceaccount.com"]
}

run "free_tier_shape" {
  command = plan

  assert {
    condition     = google_cloud_run_v2_service.app.template[0].scaling[0].min_instance_count == 0 && google_cloud_run_v2_service.app.template[0].scaling[0].max_instance_count == 1
    error_message = "Scale to zero, one instance: inside Cloud Run's Always Free allowance."
  }

  assert {
    condition     = google_cloud_run_v2_service.app.template[0].containers[0].resources[0].cpu_idle == true
    error_message = "CPU is billed only while a request is served."
  }

  assert {
    condition     = contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : "${e.name}=${e.value}"], "RECON_STATE_BACKEND=firestore") && contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : "${e.name}=${e.value}"], "FIRESTORE_DATABASE=(default)")
    error_message = "State is in the landscape's shared (default) Firestore database."
  }

  assert {
    condition     = contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : "${e.name}=${e.value}"], "E2A_PROVIDER_PROFILE=simulated") && length([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : e if e.name == "GEMINI_API_KEY"]) == 0
    error_message = "Without a key the triage agent runs on the simulated model."
  }

  assert {
    condition     = google_pubsub_subscription.lines.dead_letter_policy[0].max_delivery_attempts == 5 && length(google_pubsub_subscription.lines.push_config[0].oidc_token) == 1
    error_message = "Bank lines are pushed with an OIDC token and dead-lettered after 5 attempts."
  }

  assert {
    condition     = google_cloud_scheduler_job.scheduled.http_target[0].http_method == "POST" && length(google_cloud_scheduler_job.scheduled.http_target[0].oidc_token) == 1
    error_message = "One scheduler job calls the service with its own identity."
  }

  assert {
    condition     = length(google_cloud_run_v2_service_iam_member.invokers) == 1 && google_project_iam_member.firestore.role == "roles/datastore.user"
    error_message = "Only listed principals invoke it; the runtime reads and writes Firestore documents, nothing more."
  }

  assert {
    condition     = google_cloud_run_v2_service.app.template[0].containers[0].ports[0].container_port == 8000
    error_message = "Cloud Run sends traffic to the port the Dockerfile serves on."
  }
}

run "gemini_api_profile_reads_its_key_from_secret_manager" {
  command = plan

  variables {
    llm_profile           = "gemini_api"
    gemini_api_key_secret = "gemini-api-key"
  }

  assert {
    condition     = length([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : e if e.name == "GEMINI_API_KEY" && e.value_source[0].secret_key_ref[0].secret == "gemini-api-key"]) == 1
    error_message = "The key comes from Secret Manager, never a plain value."
  }

  assert {
    condition     = length(google_secret_manager_secret_iam_member.gemini_key) == 1
    error_message = "The runtime may read the key's secret, and only that one."
  }
}

run "never_public" {
  command = plan

  variables {
    invoker_members = ["allUsers"]
  }

  expect_failures = [var.invoker_members]
}

run "paid_models_refused" {
  command = plan

  variables {
    llm_profile = "google_vertex"
  }

  expect_failures = [var.llm_profile]
}
