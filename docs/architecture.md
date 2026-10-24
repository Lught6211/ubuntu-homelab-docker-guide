# System Architecture

## 1. Purpose

This document describes the intended architecture of the Ubuntu homelab. It separates the logical design from the individual Compose files, which are maintained under `compose/`.

## 2. Design goals

- Run multiple self-hosted services on one Ubuntu Server host.
- Keep application state in persistent volumes or documented host directories.
- Provide local DNS filtering and local hostname resolution.
- Route selected browser-based services through Caddy with internal HTTPS.
- Keep administrative and sensitive services limited to trusted LAN access.
- Make deployment and recovery steps reproducible.

## 3. Logical topology

```text
Client devices
    |
    +---- DNS requests :53 --------------------> Pi-hole
    |
    +---- HTTP :80 / HTTPS :443 ---------------> Caddy
                                                   |
                                                   +--> Vaultwarden :80
    |
    +---- Jellyfin :8096 (LAN access if enabled)
    |
    +---- Portainer :9443 (administrator access only)

Ubuntu Server host
  Docker Engine + Compose
  Persistent volumes / host directories
```

This diagram describes logical flows, not a claim that all services are isolated or exposed identically. Actual reachability is determined by Compose networks, published ports, host firewall rules, and router configuration.

## 4. Addressing and naming

Use a generic `<LAN_IP>` placeholder in public documentation. Set the actual address locally and reserve it in the router's DHCP configuration or configure a suitable static address; avoid committing a private address to a public repository.

Use a consistent private namespace. `home.arpa` is recommended for home-network naming; for example, `vault.home.arpa`. Configure the matching local DNS record in Pi-hole and use the same hostname in the Caddyfile and client bookmarks. A DNS record does not get created automatically by Caddy.

## 5. Service boundaries

| Component | Responsibility | Access policy |
|---|---|---|
| Ubuntu / SSH | Host administration | Trusted admin devices only |
| Docker Engine | Container runtime | Host administrators only |
| Portainer | Container management | Trusted administrators only |
| Pi-hole | DNS filtering and local records | LAN clients; admin UI restricted |
| Caddy | HTTP routing and internal TLS | LAN clients |
| Vaultwarden | Password vault application | Private access through HTTPS |
| Jellyfin | Media streaming | LAN users; publish only if needed |

## 6. Docker network model

The Compose examples use an external Docker network named `homelab_proxy` for Caddy and Vaultwarden. Create it once before deploying those stacks:

```bash
docker network create homelab_proxy
```

Both Compose projects must attach to this same network. The Caddy upstream can then use the Docker service name `vaultwarden:80`. Do not publish Vaultwarden's application port to the host unless direct access is deliberately required.

Other services are not automatically members of this network. Only connect a service when there is a documented reason for it to communicate with the reverse proxy or another container.

## 7. Ports

See the root README for the service inventory. Published ports are potential access paths and must be reviewed against the host firewall and LAN requirements. Do not configure public router port forwarding for these services as part of the baseline design.

## 8. Architecture limitations

This is a single-host design. A host outage can interrupt all services. Docker volumes provide persistence across container replacement, but do not provide backup, replication, or disaster recovery. Monitoring, tested backups, and recovery procedures remain operational responsibilities.
