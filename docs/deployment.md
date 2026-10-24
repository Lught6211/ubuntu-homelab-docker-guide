# Deployment Procedure

This document gives an ordered deployment workflow. It assumes Ubuntu Server is installed and the administrator has sudo access.

## 1. Prepare the host

Update the operating system and install basic tools:

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl
```

Configure a stable LAN address using the router's DHCP reservation or a documented static network configuration. Confirm connectivity before deploying DNS services.

## 2. Install Docker Engine

Follow the current official Docker instructions for Ubuntu: https://docs.docker.com/engine/install/ubuntu/

After installation, verify the service and Compose plugin:

```bash
sudo systemctl enable --now docker
sudo systemctl status docker
sudo docker version
sudo docker compose version
```

Using `sudo docker` avoids changing user group membership. Membership in the `docker` group effectively grants root-level control over the host; only trusted administrators should receive it.

## 3. Review configuration

From the repository root, inspect the Compose files under `compose/`. Replace sample values, host paths, and time-zone settings where necessary. Never commit passwords, tokens, certificates, or other secrets.

Validate each service from its own directory before starting it:

```bash
docker compose config
```

Use `sudo docker compose ...` if the current account is not authorized to access Docker.

## 4. Create the shared proxy network

The Caddy and Vaultwarden examples use a shared external network:

```bash
docker network create homelab_proxy
```

If the network already exists, Docker reports that it exists; inspect it with `docker network inspect homelab_proxy`.

## 5. Deploy services one at a time

Deploy Pi-hole first only after checking that port 53 is available and that the host's existing DNS/network setup will not be disrupted. Then deploy and verify the other services. Deploy Vaultwarden and Caddy after the shared network exists.

Example, from a service directory:

```bash
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail=100
```

The examples use image tags for convenience. For repeatable operation, choose tested versions and update them deliberately.

## 6. Configure DNS and HTTPS

1. Configure a local DNS record for the selected vault hostname, such as `vault.home.arpa`, pointing to the homelab host's LAN address.
2. Configure test clients to use Pi-hole as their DNS resolver.
3. Confirm the hostname resolves to the expected address.
4. Configure Caddy's route and confirm that its upstream is reachable on the shared Docker network.
5. Trust Caddy's internal root CA on each client that will use the HTTPS endpoint. Retrieve and install the certificate using Caddy's documented process; protect the CA private key.

Do not use browser flags that treat HTTP origins as secure as a permanent solution for a password manager.

## 7. Validation checklist

- [ ] Docker and Compose report expected versions.
- [ ] Each Compose file passes `docker compose config`.
- [ ] Expected containers are running.
- [ ] Service logs contain no unresolved startup errors.
- [ ] Host ports are not in conflict.
- [ ] Local DNS resolves the intended hostname.
- [ ] HTTPS works without certificate warnings on configured clients.
- [ ] Vaultwarden registration is disabled after initial setup.
- [ ] Persistent data survives a planned container restart.
- [ ] A backup exists and a restoration test is scheduled.

## 8. Rollback

Before updating a stateful service, make a backup and record the image version in use. If an update fails, review logs and the service's release notes. Restore from a verified backup or return to the previously tested image version when supported. Do not delete volumes as a troubleshooting shortcut.
