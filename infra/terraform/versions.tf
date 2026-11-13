# Provider + Terraform version pins for the AgriforestryOS dev infrastructure.
#
# Auth: the DigitalOcean provider reads the API token from the DIGITALOCEAN_TOKEN
# environment variable — it is NEVER stored in code or tfvars. Set it before
# running terraform:  export DIGITALOCEAN_TOKEN=dop_v1_...

terraform {
  required_version = ">= 1.5"

  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.40"
    }
  }

  # State is local by default (gitignored). For team use, promote to a
  # DigitalOcean Spaces (S3-compatible) backend — see README "Remote state".
}

provider "digitalocean" {
  # token sourced from DIGITALOCEAN_TOKEN env var.
}
