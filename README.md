# Ubuntu Homelab Server Architecture and Deployment Guide

![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Portainer](https://img.shields.io/badge/Portainer-13BEF9?style=for-the-badge&logo=portainer&logoColor=white)
![Pi-hole](https://img.shields.io/badge/Pi--hole-96060C?style=for-the-badge&logo=pihole&logoColor=white)
![Caddy](https://img.shields.io/badge/Caddy-1F88C0?style=for-the-badge&logo=caddy&logoColor=white)

A comprehensive, production-ready guide for deploying a lightweight Linux homelab server running on headless Ubuntu Server infrastructure. Designed specifically for low-power hardware (such as 6th Generation Intel Core i3 systems), this guide covers containerized management, local DNS filtering, reverse proxying, internal TLS termination, self-hosted password management, and media streaming.

---

## Technical Specifications & Topology

| Service | Technology | Port / Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **Operating System** | Ubuntu Server 24.04 LTS | Shell / SSH | Headless Linux host running systemd |
| **Management UI** | Portainer CE | `9000` / `9443` | Web UI for Docker container management |
| **DNS & Ad-Blocking** | Pi-hole v6+ | `8080` | Network-wide DNS resolver & ad filter |
| **Reverse Proxy** | Caddy | `80` / `443` | Internal TLS termination for `.home` domains |
| **Secret Management** | Vaultwarden | `8081` (`vault.home`) | Bitwarden-compatible lightweight vault |
| **Media Streaming** | Jellyfin | `8096` | Hardware-accelerated local media server |

---

## Architectural Workflow

1. **DNS Query Processing:** Client devices query Pi-hole on port 53 for local hostnames (e.g., `vault.home`).
2. **Local Address Resolution:** Pi-hole resolves local `.home` domains to the server IP address (`192.168.0.26`).
3. **Traffic Ingress:** The client connects to Caddy on port 80 or 443.
4. **TLS Termination:** Caddy negotiates internal TLS using self-signed certificates and proxies request payloads to downstream container ports over the Docker internal bridge network.

---

## Prerequisites and Base System Setup

Ensure Docker Engine and the Compose plugin are installed on the host system:

    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

---

## Service Deployments (Docker Compose Configurations)

### 1. Portainer (Infrastructure Management)

Deploy Portainer to manage container lifecycles via web interface.

    version: "3.8"

    services:
      portainer:
        image: portainer/portainer-ce:latest
        container_name: portainer
        restart: unless-stopped
        security_opt:
          - no-new-privileges:true
        volumes:
          - /var/run/docker.sock:/var/run/docker.sock
          - portainer_data:/data
        ports:
          - "9000:9000"
          - "9443:9443"

    volumes:
      portainer_data:

### 2. Pi-hole (Local DNS and Ad Blocking)

Deploy Pi-hole to act as the primary local DNS authority for the network.

    version: "3.8"

    services:
      pihole:
        container_name: pihole
        image: pihole/pihole:latest
        ports:
          - "53:53/tcp"
          - "53:53/udp"
          - "8080:80"
        environment:
          TZ: 'Asia/Kuala_Lumpur'
          FTLCONF_LOCAL_IPV4: '192.168.0.26'
        volumes:
          - './etc-pihole:/etc/pihole'
          - './etc-dnsmasq.d:/etc/dnsmasq.d'
        restart: unless-stopped

### 3. Vaultwarden (Secret Management Backend)

Deploy Vaultwarden to provide a lightweight Bitwarden-compatible vault server.

    version: "3.8"

    services:
      vaultwarden:
        container_name: vaultwarden
        image: vaultwarden/server:latest
        environment:
          WEBSOCKET_ENABLED: "true"
          SIGNUPS_ALLOWED: "true"
        ports:
          - "8081:80"
        volumes:
          - vaultwarden_data:/data
        restart: unless-stopped

    volumes:
      vaultwarden_data:

### 4. Jellyfin (Media Server)

Deploy Jellyfin for hardware-accelerated local media distribution.

    version: "3.8"

    services:
      jellyfin:
        container_name: jellyfin
        image: jellyfin/jellyfin:latest
        user: 1000:1000
        network_mode: "host"
        volumes:
          - jellyfin_config:/config
          - jellyfin_cache:/cache
          - /home/wan/media:/media
        restart: unless-stopped

    volumes:
      jellyfin_config:
      jellyfin_cache:

### 5. Caddy (Reverse Proxy and Automatic Internal TLS)

Deploy Caddy to serve custom `.home` domains with local TLS generation.

    version: "3.7"

    services:
      caddy:
        image: caddy:latest
        container_name: caddy
        restart: unless-stopped
        ports:
          - "80:80"
          - "443:443"
        command: caddy reverse-proxy --from vault.home --to 192.168.0.26:8081 --internal-certs
        volumes:
          - caddy_data:/data
          - caddy_config:/config

    volumes:
      caddy_data:
      caddy_config:

---

## WebCrypto and Insecure Origin Mitigations

Bitwarden Web Client builds strictly enforce secure contexts (`https://` protocols or `localhost`) to enable JavaScript WebCrypto primitives necessary for client-side password hashing.

* **Method A: Native TLS Termination via Reverse Proxy (Recommended)**  
  By utilizing Caddy with the `--internal-certs` flag or Nginx Proxy Manager with custom SSL certificates, all browser traffic to `https://vault.home` is served over HTTPS, fulfilling browser security constraints natively.

* **Method B: Browser Flags for HTTP Local Testing**  
  For environments operating without SSL certificates, Chromium-based browsers (Chrome, Edge, Opera) allow manual overrides for specific HTTP origins:
  1. Navigate to `chrome://flags/#unsafely-treat-insecure-origin-as-secure` in the address bar.
  2. Enable the feature and add targeted endpoints to the configuration box: `http://vault.home, http://192.168.0.26:8081`
  3. Relaunch the browser.

---

## Operations & Maintenance

| Task | Command / Procedure |
| :--- | :--- |
| **Disable Public Signups** | Set `SIGNUPS_ALLOWED: "false"` in Vaultwarden environment variables and update the stack |
| **Reset Pi-hole Admin Password** | `docker exec -it pihole pihole setpassword` |
| **Flush Windows Resolver Cache** | `ipconfig /flushdns` |
| **Inspect Container Logs** | `docker logs --tail 50 -f <container_name>` |
