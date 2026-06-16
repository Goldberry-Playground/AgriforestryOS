# The deploy target + connection details. `terraform output -raw reserved_ip`
# feeds the GitHub Actions deploy workflow (as the DEPLOY_HOST secret/var).

output "reserved_ip" {
  description = "Stable public IP of the dev host — the deploy target (use this, not droplet_ip)."
  value       = digitalocean_reserved_ip.host.ip_address
}

output "droplet_ip" {
  description = "Current droplet public IPv4 (changes on rebuild; prefer reserved_ip)."
  value       = digitalocean_droplet.host.ipv4_address
}

output "ssh_command" {
  description = "Convenience SSH command for the deploy user."
  value       = "ssh deploy@${digitalocean_reserved_ip.host.ip_address}"
}

output "app_dir" {
  description = "Where the repo is cloned / the stack runs on the host."
  value       = "/opt/agriforestryos/repo"
}
