# Inputs for the AgriforestryOS deploy tiers (preprod by default; prod via workspace).
# Copy terraform.tfvars.example → terraform.tfvars and adjust. No secrets here:
# the DO API token comes from DIGITALOCEAN_TOKEN; only your SSH *public* key.

variable "environment" {
  description = "Environment name (used in resource names + tags). Default tier is preprod; prod uses a separate workspace with -var environment=prod."
  type        = string
  default     = "preprod"
}

variable "region" {
  description = "DigitalOcean region slug. nyc3 is a sensible East-Coast default for WV."
  type        = string
  default     = "nyc3"
}

variable "droplet_size" {
  description = "Droplet size slug. Default 4GB/2vCPU — enough for farmOS + Postgres + PostGIS + the Python services on a single tier."
  type        = string
  default     = "s-2vcpu-4gb"
}

variable "droplet_image" {
  description = "Base image slug."
  type        = string
  default     = "ubuntu-24-04-x64"
}

variable "ssh_public_key" {
  description = "Your SSH PUBLIC key contents (ssh-ed25519 AAAA... / ssh-rsa ...). The matching PRIVATE key is what GitHub Actions uses to deploy. Never commit the private key."
  type        = string
}

variable "repo_url" {
  description = "Git URL the droplet clones to become deploy-ready."
  type        = string
  default     = "https://github.com/Goldberry-Playground/AgriforestryOS.git"
}

variable "repo_branch" {
  description = "Branch the dev box tracks."
  type        = string
  default     = "4.x"
}

variable "tailscale_auth_key" {
  description = <<-EOT
    Tailscale auth key used by cloud-init to join the droplet to your tailnet.
    Use a PRE-AUTHORIZED, REUSABLE, TAGGED, EPHEMERAL key (e.g. tag:agriforestryos)
    from https://login.tailscale.com/admin/settings/keys. Sourced from 1Password,
    set via `TF_VAR_tailscale_auth_key` or terraform.tfvars (gitignored) — never
    committed. Required: this environment is private-mesh-only (no public web).
  EOT
  type        = string
  sensitive   = true
}

variable "tags" {
  description = "Extra DO tags applied to all resources."
  type        = list(string)
  default     = []
}

variable "backups_volume_size_gb" {
  description = <<-EOT
    Size (GiB) of an attached block-storage volume for the local backups
    directory (/opt/agriforestryos/backups), so backups survive droplet
    replacement. 0 = no volume (backups land on the droplet's own disk — fine
    for dev). Set this for prod (e.g. 10).
  EOT
  type        = number
  default     = 0
}
