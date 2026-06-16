# AgriforestryOS — Dev infrastructure (Terraform)

Provisions the **dev environment** for AgriforestryOS on DigitalOcean: a
Docker-host droplet with a stable reserved IP and a locked-down firewall.

**Split of responsibility:**
- **Terraform (here)** owns the *infrastructure* — the droplet, reserved IP,
  firewall, SSH key. Runs rarely (provision / resize / replace the box).
- **GitHub Actions** owns the *application deploy* onto that box — SSH in,
  `git pull`, `docker compose up`, `drush updb`. Runs on every merge to `4.x`.

Terraform's `reserved_ip` output is the deploy **target** the workflow points at.

## What it creates

| Resource | Purpose |
|---|---|
| `digitalocean_droplet` | Ubuntu 24.04 Docker host (default 4GB/2vCPU). cloud-init installs Docker, creates a `deploy` user, clones the repo, sets `ufw`. |
| `digitalocean_reserved_ip` | Stable IP that survives droplet rebuilds — the permanent deploy target / future DNS A record. |
| `digitalocean_firewall` | Inbound 22/80/443 only. **Postgres/PostGIS (5432/5433) are NOT exposed** — services use the internal docker network; operators tunnel over SSH. |
| `digitalocean_ssh_key` | Registers your public key for droplet access. |

## Prerequisites

- `terraform` ≥ 1.5, a DigitalOcean account + API token, an SSH keypair.

## Usage

```bash
cd infra/terraform

# 1. Auth — token via env var, never in files:
export DIGITALOCEAN_TOKEN=dop_v1_xxxxxxxx

# 2. Inputs:
cp terraform.tfvars.example terraform.tfvars
#   edit terraform.tfvars → paste your SSH *public* key

# 3. Provision (review the plan before applying — this creates billable infra):
terraform init
terraform plan
terraform apply

# 4. Grab the deploy target:
terraform output -raw reserved_ip      # → set as the DEPLOY_HOST GitHub secret
terraform output ssh_command
```

`terraform apply` creates a **paid droplet (~$24/mo for 4GB)** — run it
yourself when you're ready; it is not run for you.

## Wiring GitHub Actions to this box

After `apply`, set these GitHub repo secrets so the deploy workflow can reach
the droplet:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | `terraform output -raw reserved_ip` |
| `DEPLOY_SSH_KEY` | the **private** key matching `ssh_public_key` |

(Doctl note: `doctl` isn't required for provisioning — Terraform talks to the
DO API directly. It's handy for ad-hoc ops: `doctl compute droplet list`,
`doctl compute ssh agriforestryos-dev`.)

## Tear down

```bash
terraform destroy
```

Destroys the droplet + reserved IP. (No prod data exists yet, so this is safe;
once there is, snapshot/backup the volumes first.)

## Remote state (when more than one person runs this)

Local `terraform.tfstate` is fine for a solo operator and is gitignored
(it can contain sensitive values). For team use, move state to a DigitalOcean
Spaces (S3-compatible) backend — add a `backend "s3"` block to `versions.tf`.
