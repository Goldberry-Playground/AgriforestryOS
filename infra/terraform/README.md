# AgriforestryOS — Deploy-tier infrastructure (Terraform)

Provisions the **preprod environment** (and prod via workspace) for AgriforestryOS on DigitalOcean: a
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
| `digitalocean_droplet` | Ubuntu 24.04 Docker host (default 4GB/2vCPU). cloud-init installs Docker, creates a `deploy` user, clones the repo, **joins the tailnet**, sets `ufw`. Default name: `agriforestryos-preprod`. |
| `digitalocean_reserved_ip` | Stable IP that survives droplet rebuilds — the SSH/CI deploy target. |
| `digitalocean_firewall` | **Private-mesh only:** inbound `22/tcp` (SSH break-glass + CI) + `41641/udp` (Tailscale). **No public 80/443** — farmOS is reachable only over the tailnet. Postgres/PostGIS (5432/5433) never exposed. This cloud firewall is the real control (it isn't bypassed by Docker's published ports, unlike `ufw`). |
| `digitalocean_ssh_key` | Registers your public key for droplet access. |

## Prerequisites

- `terraform` ≥ 1.5, a DigitalOcean account + API token, an SSH keypair.

## Usage

```bash
cd infra/terraform

# 1. Auth + secrets — via env vars, never in files:
export DIGITALOCEAN_TOKEN=dop_v1_xxxxxxxx
export TF_VAR_tailscale_auth_key=tskey-auth-...   # reusable, tagged, ephemeral

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
| `PREPROD_HOST` | `terraform output -raw reserved_ip` |
| `PREPROD_SSH_KEY` | the **private** key matching `ssh_public_key` |

(Doctl note: `doctl` isn't required for provisioning — Terraform talks to the
DO API directly. It's handy for ad-hoc ops: `doctl compute droplet list`,
`doctl compute ssh agriforestryos-preprod`.)

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
