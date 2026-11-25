variable "project_id" {
  type        = string
  description = "Google Cloud project id (deploy/gcp/binding.env)."
}

variable "region" {
  type        = string
  description = "Region: us-central1 keeps the landscape next to the Always Free e2-micro ledger VM."
  default     = "us-central1"
}

variable "image" {
  type        = string
  description = "Container image in the landscape's Artifact Registry, pushed by CI."
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "firestore_database" {
  type        = string
  description = "The landscape's shared Firestore database (one is free per project)."
  default     = "(default)"
}

variable "settlement_api_url" {
  type        = string
  description = "Cloud Run URL of settlement-service (financial-settlement-platform, infra/gcp)."
  default     = "https://settlement-service.placeholder.run.app"
}

variable "tenant" {
  type        = string
  description = "The deployment's tenant (RECON_TENANT)."
  default     = "acme"
}

variable "llm_profile" {
  type        = string
  description = "E2A provider profile of the triage agent: simulated (no key) or gemini_api (free tier)."
  default     = "simulated"

  validation {
    condition     = contains(["simulated", "gemini_api"], var.llm_profile)
    error_message = "Free tier only: simulated or gemini_api."
  }
}

variable "llm_model_id" {
  type        = string
  description = "Gemini model for the gemini_api profile (empty: the profile's default)."
  default     = ""
}

variable "gemini_api_key_secret" {
  type        = string
  description = "Secret Manager secret id holding the Gemini API key (empty with the simulated profile)."
  default     = ""
}

variable "max_instance_count" {
  type        = number
  description = "Cloud Run instances at most (state is in Firestore, so more are safe; 1 keeps it free)."
  default     = 1
}

variable "max_delivery_attempts" {
  type        = number
  description = "Pushes of one bank line before Pub/Sub moves it to the dead-letter topic."
  default     = 5
}

variable "schedule" {
  type        = string
  description = "Cron of the scheduled job (feed poll, ledger retries, dead letters)."
  default     = "*/15 * * * *"
}

variable "invoker_members" {
  type        = list(string)
  description = "Other principals allowed to call the service: the assistant's and O2C's service accounts, allow-listed people."
  default     = []

  validation {
    condition     = !contains(var.invoker_members, "allUsers") && !contains(var.invoker_members, "allAuthenticatedUsers")
    error_message = "reconciliation-service posts ledger adjustments: it is never public."
  }
}
