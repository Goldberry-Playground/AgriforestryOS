# Inputs for the AgriforestryOS dev environment.
# Copy terraform.tfvars.example → terraform.tfvars and adjust. No secrets here:
# the DO API token comes from DIGITALOCEAN_TOKEN; only your SSH *public* key.

variable "environment" {
  description = "Environment name (used in resource names + tags)."
  type        = string
  default     = "dev"
}

variable "region" {
  description = "DigitalOcean region slug. nyc3 is a sensible East-Coast default for WV."
  type        = string
  default     = "nyc3"
}

variable "droplet_size" {
  description = "Droplet size slug. Default 4GB/2vCPU — enough for farmOS + Postgres + PostGIS + the two Python services for dev."
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

variable "tags" {
  description = "Extra DO tags applied to all resources."
  type        = list(string)
  default     = []
}
