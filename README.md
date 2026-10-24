# Ubuntu Homelab Server: Architecture, Deployment and Operations Report

![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04_LTS-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Engine-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Portainer](https://img.shields.io/badge/Portainer-Management-13BEF9?style=for-the-badge&logo=portainer&logoColor=white)
![Pi-hole](https://img.shields.io/badge/Pi--hole-DNS%20Filtering-96060C?style=for-the-badge&logo=pihole&logoColor=white)
![Caddy](https://img.shields.io/badge/Caddy-Reverse%20Proxy-1F88C0?style=for-the-badge&logo=caddy&logoColor=white)

> **Project type:** Personal infrastructure / systems administration  
> **Platform:** Headless Ubuntu Server with Docker Compose  
> **Primary focus:** Service isolation, local name resolution, web access, internal HTTPS, media delivery, and maintainable operations

## Abstract

This project documents the design and deployment approach for a lightweight Ubuntu-based homelab. The system uses Docker containers to host infrastructure and application services on a single Linux machine. Portainer provides a graphical management interface, Pi-hole provides DNS filtering and local name resolution, Caddy acts as a reverse proxy for selected web services, Vaultwarden provides a self-hosted password-vault backend, and Jellyfin serves a local media library.

The repository is intended to function as technical documentation rather than a quick-start checklist. It records the proposed service topology, implementation assumptions, deployment examples, operational procedures, and security considerations. Configuration examples must be adapted to the target network and validated before use; this repository does not by itself certify the deployment as production-ready.

## Table of Contents

- [1. Project Overview](#1-project-overview)
- [2. Objectives and Scope](#2-objectives-and-scope)
- [3. System Environment](#3-system-environment)
- [4. Architecture and Network Design](#4-architecture-and-network-design)
- [5. Service Inventory](#5-service-inventory)
- [6. Deployment Methodology](#6-deployment-methodology)
- [7. Service Configuration Examples](#7-service-configuration-examples)
- [8. Security and Reliability Considerations](#8-security-and-reliability-considerations)
- [9. Verification and Operations](#9-verification-and-operations)
- [10. Known Limitations and Future Improvements](#10-known-limitations-and-future-improvements)
- [11. Repository Structure](#11-repository-structure)
- [12. References](#12-references)

---

## 1. Project Overview

The homelab consolidates several self-hosted services onto a low-power computer running Ubuntu Server. The host is administered remotely through SSH, while Docker Compose is used to describe and manage application containers. Services are accessed either through their published host ports or, where configured, through a local reverse proxy.

The design prioritizes:

- **Centralized administration:** use Portainer and Docker tooling to inspect and manage containers.
- **Network-level DNS filtering:** use Pi-hole for DNS resolution and block-list-based filtering.
- **Consistent web access:** use Caddy to route selected hostnames to internal applications and provide HTTPS using an internal certificate authority.
- **Persistent application data:** keep service configuration and state in named volumes or explicit host directories.
- **Operational visibility:** use container status, logs, disk-usage checks, and service-specific health pages to investigate failures.

### Intended users

This documentation is for a homelab administrator who is familiar with basic Linux terminal usage, IP addressing, SSH, and Docker concepts. It can also serve as a project portfolio record of the system's architecture and operational decisions.

## 2. Objectives and Scope

### 2.1 Objectives

1. Establish a remotely manageable Ubuntu Server host.
2. Deploy selected services using Docker Engine and Docker Compose.
3. provide local DNS resolution and filtering through Pi-hole.
4. Route selected browser-based services through Caddy.
5. Preserve service data across container replacement and restart.
6. Document routine maintenance, validation, and security controls.

### 2.2 Scope

This repository documents a single-host homelab design. It includes the base Docker installation procedure, representative Compose definitions, service endpoints, and operational notes.

The examples do **not** constitute a high-availability architecture. They do not automatically provide off-site backups, redundant storage, disaster recovery, centralized monitoring, or a complete security audit. Those capabilities require additional design and testing.

## 3. System Environment

The values below reflect the example environment used throughout this documentation. Replace them with the values applicable to the target host before deployment.

| Parameter | Example value | Notes |
|---|---|---|
| Operating system | Ubuntu Server 24.04 LTS | Headless Linux host |
| Hostname | `ubuntu-homelab` | Example host identity |
| LAN address | `192.168.0.26` | Must be reserved or assigned statically in the local network |
| Time zone | `Asia/Kuala_Lumpur` | Adjust to the deployment location |
| Container runtime | Docker Engine | Installed from Docker's official APT repository |
| Deployment format | Docker Compose | Compose files should be maintained with the project |
| Administration | SSH | Restrict access to trusted users and networks |

### 3.1 Prerequisites

- A supported 64-bit Ubuntu Server installation.
- A reliable LAN connection and a known host IP address.
- Administrative access through `sudo`.
- SSH enabled if the host will be administered remotely.
- Adequate memory and storage for the selected applications and media.
- A backup destination for persistent configuration and important data.

## 4. Architecture and Network Design

### 4.1 Logical request flow

The intended request path for a proxied internal web service is:

1. A client uses the configured DNS resolver to look up a local service hostname.
2. Pi-hole returns the homelab host's LAN address for the configured local record.
3. The client connects to Caddy on HTTP or HTTPS.
4. Caddy selects a configured upstream and forwards the request to the application service.
5. The application responds through Caddy to the client.

Pi-hole does not automatically create DNS records for every `.home` hostname. Local records must be configured explicitly, and the client must use Pi-hole (or another resolver with equivalent records). For a private home network, consider using the reserved `home.arpa` namespace rather than `.home`; configure the same chosen hostname consistently in DNS, Caddy, and clients.

### 4.2 High-level topology

```text
                   Client devices
                         |
                 LAN / trusted network
                         |
              +-----------------------+
              | Ubuntu Server host    |
              | Example: 192.168.0.26 |
              +-----------------------+
                  |       |       |
                  |       |       +----------------------+
                  |       |                              |
             DNS :53   HTTP/S :80/:443              Published ports
                  |       |                              |
             +--------+ +-------+       +----------------+-------------+
             | Pi-hole| | Caddy |       | Portainer / Vaultwarden /     |
             | DNS    | | Proxy |       | Jellyfin and other services   |
             +--------+ +---+---+       +------------------------------+
                             |
                       Configured upstream
                       application endpoint
```

This is a logical diagram, not a guarantee that every service is isolated on a dedicated Docker network. The Compose examples below are independent examples and must be integrated into a deliberate network and port plan.

### 4.3 Port and endpoint inventory

| Service | Host port(s) | Purpose |
|---|---:|---|
| SSH | 22/TCP (typical) | Remote administration |
| Portainer CE | 9443/TCP; optional 9000/TCP | Container management UI; 9443 is the HTTPS UI |
| Pi-hole | 53/TCP and 53/UDP; 8080/TCP | DNS; web interface mapped to host port 8080 |
| Caddy | 80/TCP and 443/TCP | HTTP and HTTPS reverse proxy |
| Vaultwarden | 8081/TCP in the example | Application HTTP endpoint; preferably keep private behind Caddy |
| Jellyfin | 8096/TCP (default) | Media streaming interface |

Port mappings can conflict with other services already using the same host ports. Review the final Compose files before starting the stack. Do not expose administrative or password-vault interfaces directly to the public internet without a separate security design.

## 5. Service Inventory

### 5.1 Ubuntu Server

Provides the operating-system foundation, user management, systemd service control, networking, storage, and SSH administration.

### 5.2 Docker Engine and Compose

Docker runs the applications in containers, while Compose declares their images, ports, environment, mounts, restart policies, and dependencies. Persistent data should be stored outside the disposable container filesystem.

### 5.3 Portainer CE

Provides a browser-based interface for inspecting containers, images, volumes, and application stacks. Access should be limited to trusted administrators. Mounting `/var/run/docker.sock` gives the container powerful control over the Docker host, so it must be treated as a privileged management component.

### 5.4 Pi-hole

Provides DNS resolution and block-list-based filtering for clients configured to use it. Port 53 must be available on the host, and router DHCP/DNS settings or individual clients must be configured appropriately. The web interface is mapped to host port 8080 in the example.

### 5.5 Caddy

Provides reverse-proxy routing and internal HTTPS for selected hostnames. With an internal certificate authority, client devices must trust Caddy's local root certificate to avoid browser certificate warnings. DNS records and proxy routes must be configured separately and kept in sync.

### 5.6 Vaultwarden

Provides a lightweight, Bitwarden-compatible server implementation. It stores highly sensitive data and therefore requires careful access control, secure backups, strong account security, and HTTPS. Public account registration should be disabled after initial setup unless open registration is an intentional requirement.

### 5.7 Jellyfin

Provides a self-hosted media interface for local playback. Media directories must be mounted readably into the container, and hardware acceleration requires compatible hardware, drivers, and explicit configuration; it should not be assumed merely because Jellyfin is running in Docker.

---

## 6. Deployment Methodology

The recommended deployment sequence is:

1. **Prepare the host:** install Ubuntu Server, apply updates, configure a stable LAN address, and create an administrator account.
2. **Enable remote administration:** install and test SSH from a separate client.
3. **Install Docker:** configure Docker's official package repository and install Docker Engine and the Compose plugin.
4. **Prepare persistent storage:** create and permission-check application data directories and media paths.
5. **Deploy one service at a time:** validate each service before moving to the next.
6. **Configure DNS:** create local records and point test clients at the intended DNS resolver.
7. **Configure reverse proxy and TLS:** add Caddy routes, confirm upstream reachability, and trust the internal CA on client devices.
8. **Validate and document:** check service status, logs, access paths, persistence after restart, and recovery steps.
9. **Establish maintenance routines:** back up application data, monitor storage, and apply updates in a controlled manner.

### 6.1 Install Docker Engine on Ubuntu

The following procedure adds Docker's official APT repository and installs Docker Engine with the Compose plugin. Review Docker's current official installation documentation before using it on a new Ubuntu release.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo ${UBUNTU_CODENAME:-$VERSION_CODENAME}) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

For repeatable deployments, store each service's Compose configuration in a named directory, use a `compose.yaml` file, and keep a record of any host-specific values. Do not commit passwords, tokens, private keys, or other secrets to the repository.

## 7. Service Configuration Examples

The snippets in this section are **illustrative starting points**, not a single combined Compose project. Each service can be placed in its own directory or combined after reviewing port conflicts, shared networks, volume paths, and startup requirements.

### 7.1 Portainer CE

```yaml
services:
  portainer:
    image: portainer/portainer-ce:latest
    container_name: portainer
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    ports:
      - "9443:9443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - portainer_data:/data

volumes:
  portainer_data:
```

Port 9000 is omitted here because the HTTPS interface on 9443 is preferred. Pin image versions or digests for more controlled upgrades, and restrict access to the management interface.

### 7.2 Pi-hole

```yaml
services:
  pihole:
    image: pihole/pihole:latest
    container_name: pihole
    hostname: pihole
    restart: unless-stopped
    ports:
      - "53:53/tcp"
      - "53:53/udp"
      - "8080:80/tcp"
    environment:
      TZ: "Asia/Kuala_Lumpur"
      FTLCONF_LOCAL_IPV4: "192.168.0.26"
    volumes:
      - ./etc-pihole:/etc/pihole

```

Check the current Pi-hole container documentation for version-specific environment variables and persistence requirements before deployment. The host address must match the actual server address. Ensure another resolver or service is not already occupying port 53.

### 7.3 Vaultwarden

```yaml
services:
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: vaultwarden
    restart: unless-stopped
    environment:
      SIGNUPS_ALLOWED: "false"
    volumes:
      - vaultwarden_data:/data
    # Publish a host port only if direct LAN access is intentionally required.
    # Prefer routing through a private Caddy endpoint.

volumes:
  vaultwarden_data:
```

The example intentionally does not publish port 8081 to all host interfaces. If direct LAN access is required for testing, add a suitable port mapping and firewall restrictions. Enable registration only for initial account creation when necessary, then disable it. Configure HTTPS at the reverse proxy and back up the vault data securely.

### 7.4 Jellyfin

```yaml
services:
  jellyfin:
    image: jellyfin/jellyfin:latest
    container_name: jellyfin
    restart: unless-stopped
    ports:
      - "8096:8096"
    volumes:
      - jellyfin_config:/config
      - jellyfin_cache:/cache
      - /home/wan/media:/media:ro

volumes:
  jellyfin_config:
  jellyfin_cache:
```

Replace `/home/wan/media` with the actual media directory. The read-only mount is suitable when Jellyfin only needs to read the library; adjust it only if the workflow requires writes. Hardware acceleration is environment-specific and must be configured separately.

### 7.5 Caddy

A Caddyfile is easier to maintain and review than a long command-line invocation. The example below assumes that `vault.home.arpa` resolves to the homelab host and that Vaultwarden is reachable from Caddy at the configured upstream address.

```caddyfile
vault.home.arpa {
    tls internal
    reverse_proxy vaultwarden:80
}
```

This upstream name works only if Caddy and Vaultwarden share a Docker network and the service name is resolvable there. If they run in separate Compose projects, create and attach both services to a shared external network, or use a deliberately configured reachable host address and port. Persist Caddy's `/data` directory so its internal CA and certificates survive container replacement.

### 7.6 Deployment commands

From the directory containing the relevant Compose file:

```bash
docker compose config
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail=100
```

Run `docker compose config` before deployment to catch common YAML and interpolation mistakes. Avoid running all examples together without first reconciling ports, networks, mounts, and service dependencies.

---

## 8. Security and Reliability Considerations

### 8.1 Network exposure

- Keep management interfaces, DNS administration, and Vaultwarden restricted to trusted networks.
- Do not configure router port forwarding to sensitive services unless there is a reviewed need and an appropriate access-control design.
- Use a host firewall and review which interfaces published Docker ports bind to.
- For remote access, consider a private VPN such as Tailscale rather than exposing internal services directly to the internet.

### 8.2 HTTPS and browser security

Modern browser features used by password managers require a secure context. Serve the vault through HTTPS and install/trust the internal CA certificate on each client that needs to use the service. Browser flags that treat HTTP origins as secure are a testing workaround, not a recommended long-term configuration.

### 8.3 Credentials and secrets

- Disable open registration on Vaultwarden after the required initial setup.
- Use strong, unique credentials and enable additional account protections where supported.
- Store secrets in a protected environment file or secret-management mechanism, not in committed Compose files.
- Treat access to the Docker socket as highly privileged.

### 8.4 Updates and image management

The `latest` tag is convenient for examples but does not guarantee repeatable deployments. For a more controlled environment, pin tested versions, review release notes, update deliberately, and retain a rollback plan. Back up persistent data before upgrades that may change application data formats.

### 8.5 Backups and recovery

Named Docker volumes persist across container replacement but are not backups. Establish a separate backup routine for application configuration, vault data, Pi-hole settings, Caddy data, and any other irreplaceable files. Keep at least one backup copy separate from the host and periodically test restoration.

### 8.6 Storage management

Media downloads and container images can consume disk space quickly. Check capacity regularly before cleanup operations. Avoid destructive commands such as `docker system prune --volumes` unless you have verified which resources will be removed and confirmed that required data is backed up.

---

## 9. Verification and Operations

Use the following checks after initial deployment and after significant configuration changes.

| Check | Command or action | Expected result |
|---|---|---|
| Docker service | `sudo systemctl status docker` | Docker service is active |
| Container status | `docker ps` | Expected containers are running |
| Compose syntax | `docker compose config` | Configuration renders without errors |
| Service logs | `docker logs --tail 100 <container_name>` | No unresolved startup or configuration errors |
| Listening ports | `sudo ss -lntup` | Only intended services are listening |
| Disk capacity | `df -h` | Adequate free space remains |
| DNS resolution | `nslookup vault.home.arpa <pihole-ip>` | The expected local record is returned |
| HTTPS | Open the configured hostname in a browser | Certificate is trusted and the application responds |
| Persistence | Restart a test service and inspect its data | Expected settings and data remain available |

### 9.1 Common maintenance tasks

**Reset Pi-hole's web password:** use the command supported by the installed Pi-hole version. For current releases, verify the correct syntax in the official documentation before running administrative commands.

**Flush Windows DNS cache:**

```powershell
ipconfig /flushdns
```

**Follow a container's logs:**

```bash
docker logs --tail 50 -f <container_name>
```

**Inspect storage usage:**

```bash
df -h
du -sh /home/wan/media
docker system df
```

**Restart a Compose-managed service:**

```bash
docker compose restart <service_name>
```

Run Compose commands from the directory containing the correct Compose file. Record any change that resolves an incident so the documentation remains consistent with the actual deployment.

---

## 10. Known Limitations and Future Improvements

The following items are recommended follow-up work; they should not be interpreted as already implemented.

- [ ] Maintain version-pinned Compose files for every deployed service.
- [ ] Add a complete repository directory structure with one maintained Compose file per stack.
- [ ] Define Docker networks explicitly and document which services may communicate.
- [ ] Add automated health checks where supported by the application images.
- [ ] Document host firewall rules and remote-access configuration.
- [ ] Implement scheduled, encrypted backups and test restoration.
- [ ] Add monitoring for disk capacity, container health, and host availability.
- [ ] Document a controlled update and rollback process.
- [ ] Record validation results, including browser trust of the internal certificate authority.
- [ ] Add hardware-acceleration configuration only after confirming the host's supported graphics hardware and drivers.

## 11. Repository Structure

The repository separates the overview from detailed operational documentation and individual service deployments.

```text
ubuntu-homelab-docker-guide/
├── README.md
├── .gitignore
├── docs/
│   ├── architecture.md
│   ├── deployment.md
│   ├── security.md
│   └── operations.md
└── compose/
    ├── portainer/compose.yaml
    ├── pihole/compose.yaml
    ├── vaultwarden/compose.yaml
    ├── jellyfin/compose.yaml
    └── caddy/
        ├── compose.yaml
        └── Caddyfile
```

### Detailed documentation

- [System architecture](docs/architecture.md)
- [Deployment procedure](docs/deployment.md)
- [Security considerations](docs/security.md)
- [Operations runbook](docs/operations.md)

### Compose deployment files

- [Portainer](compose/portainer/compose.yaml)
- [Pi-hole](compose/pihole/compose.yaml)
- [Vaultwarden](compose/vaultwarden/compose.yaml)
- [Jellyfin](compose/jellyfin/compose.yaml)
- [Caddy](compose/caddy/compose.yaml) and [Caddyfile](compose/caddy/Caddyfile)

Before deploying Caddy and Vaultwarden, create their shared Docker network with `docker network create homelab_proxy`. Review each Compose file, replace sample host values where required, and follow the deployment procedure. These files are starting configurations and have not been validated against the user's live host.

## 12. References

Consult the official project documentation for version-specific instructions and security recommendations:

- [Ubuntu Server documentation](https://documentation.ubuntu.com/server/)
- [Docker Engine installation on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Docker Compose documentation](https://docs.docker.com/compose/)
- [Portainer documentation](https://docs.portainer.io/)
- [Pi-hole documentation](https://docs.pi-hole.net/)
- [Caddy documentation](https://caddyserver.com/docs/)
- [Vaultwarden project repository](https://github.com/dani-garcia/vaultwarden)
- [Jellyfin documentation](https://jellyfin.org/docs/)

---

## Project Status

This repository is a living technical record of a personal homelab. Configuration snippets are examples and may require adaptation to the installed software versions, network environment, and host paths. Validate each service and review security implications before exposing it to other devices or networks.
