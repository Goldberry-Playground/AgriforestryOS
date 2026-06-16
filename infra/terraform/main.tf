# AgriforestryOS dev environment: a Docker-host droplet with a stable reserved
# IP and a locked-down firewall. Terraform owns the *infrastructure*; GitHub
# Actions deploys the *application* onto it (SSH → pull → compose up → drush updb).

locals {
  name        = "agriforestryos-${var.environment}"
  common_tags = concat(["agriforestryos", var.environment], var.tags)

  # When a backups volume exists, DO attaches it at a deterministic by-id path
  # derived from the volume name. cloud-init formats + mounts it (nofail).
  backups_volume_name = "${local.name}-backups"
  backups_device = var.backups_volume_size_gb > 0 ? (
    "/dev/disk/by-id/scsi-0DO_Volume_${local.backups_volume_name}"
  ) : ""
}

# Optional block-storage volume for the backups directory — keeps backups when
# the droplet is replaced. Created only when backups_volume_size_gb > 0.
resource "digitalocean_volume" "backups" {
  count                   = var.backups_volume_size_gb > 0 ? 1 : 0
  name                    = local.backups_volume_name
  region                  = var.region
  size                    = var.backups_volume_size_gb
  initial_filesystem_type = "ext4"
  tags                    = local.common_tags
}

resource "digitalocean_volume_attachment" "backups" {
  count      = var.backups_volume_size_gb > 0 ? 1 : 0
  droplet_id = digitalocean_droplet.host.id
  volume_id  = digitalocean_volume.backups[0].id
}

# SSH key registered with DO from your public key; used for droplet access.
resource "digitalocean_ssh_key" "deploy" {
  name       = "${local.name}-deploy"
  public_key = var.ssh_public_key
}

# The Docker host. cloud-init installs Docker, creates the `deploy` user,
# clones the repo, and sets the firewall.
resource "digitalocean_droplet" "host" {
  name     = local.name
  region   = var.region
  size     = var.droplet_size
  image    = var.droplet_image
  ssh_keys = [digitalocean_ssh_key.deploy.fingerprint]
  tags     = local.common_tags

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    ssh_public_key     = var.ssh_public_key
    repo_url           = var.repo_url
    repo_branch        = var.repo_branch
    tailscale_auth_key = var.tailscale_auth_key
    tailscale_hostname = local.name
    backups_device     = local.backups_device
  })

  # Recreate if cloud-init changes meaningfully; keep the reserved IP stable.
  lifecycle {
    create_before_destroy = true
  }
}

# Stable IP that survives droplet rebuilds — this is the deploy *target* GitHub
# Actions and (later) DNS point at, so it never changes when the box is replaced.
resource "digitalocean_reserved_ip" "host" {
  region = var.region
}

resource "digitalocean_reserved_ip_assignment" "host" {
  ip_address = digitalocean_reserved_ip.host.ip_address
  droplet_id = digitalocean_droplet.host.id
}

# Cloud firewall — the REAL public-exposure control (it sits at the NIC, so
# unlike ufw it is NOT bypassed by Docker's published ports). This environment
# is private-mesh-only:
#   - 22/tcp  SSH break-glass (key-only) — kept so a Tailscale failure can't
#             lock us out, and so the GitHub Actions deploy reaches the box.
#   - 41641/udp  Tailscale direct connections (falls back to DERP if blocked).
#   - NO 80/443: farmOS is reachable ONLY over the tailnet (via tailscale0).
#   - DB ports deliberately absent — Postgres/PostGIS never internet-exposed.
resource "digitalocean_firewall" "host" {
  name        = "${local.name}-fw"
  droplet_ids = [digitalocean_droplet.host.id]
  tags        = local.common_tags

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }
  inbound_rule {
    protocol         = "udp"
    port_range       = "41641"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}
