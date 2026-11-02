# CISCO private homelab connector

The CISCO agent gives the CiscoAI dashboard a private, authenticated connection to this Docker host. It uses Tailscale Serve for HTTPS inside the tailnet; the Compose stack publishes no host ports and explicitly disables Tailscale Funnel.

## Capabilities

- Read CPU, memory, uptime, Docker container state, configured website checks, and optional qBittorrent download progress.
- Start, stop, or restart only containers named in CISCO_MANAGED_SERVICES.
- Pause or resume an individual qBittorrent download.
- Report the server as unreachable when the private connection is unavailable.
- Check the public guide's `main` branch for CISCO agent updates and, after explicit confirmation, update only the CISCO agent and Docker guard.

The agent has no shell, command execution, container creation, container deletion, Docker logs, or volume deletion endpoint. A small Docker guard sits between the agent and the Docker socket. It permits container listing and start/stop/restart requests only, and independently checks the container allowlist for every operation. The guard still uses the Docker socket, which has administrator-level host privileges; keep this stack and its Tailscale identity under your control.

The optional fixed deploy service is separate from the agent and listens only on host loopback. It uses the Docker socket to rebuild the two named CISCO services, so it has host administrator-equivalent power if compromised. Its API is reachable only through the authenticated agent, and it accepts no shell commands, repository URLs, paths, Compose files, or service names from the browser. It is limited to this public repository's `main` branch and the `cisco-docker-guard` / `cisco-homelab-agent` services. It checks for updates every ten minutes while the CiscoAI server panel is open, uses a five-minute remote revision cache, refuses a dirty checkout or non-`main` branch, requires an explicit user confirmation to deploy, validates Compose first, and attempts to restore the previous commit and services if deployment fails. It does not update other homelab applications.

The storage percentage is the agent container's root filesystem view. It is not a per-mount inventory of every host disk or media volume.

## Deploy beside an existing Tailscale host

If Tailscale is already installed and connected on the Docker host, use `compose/cisco-agent/compose.host-network.yaml`. This reuses that host's existing tailnet identity; it does not need a new auth key or sidecar device. The agent and Docker guard bind only to `127.0.0.1`, and Tailscale Serve provides HTTPS privately to tailnet devices. You can set `CISCO_TAILSCALE_ALLOWED_USERS` to the comma-separated Tailscale login names allowed to use the dashboard; Serve adds the trusted `Tailscale-User-Login` header to requests. Because this deployment uses identity headers, keep the app bound to localhost and never enable Funnel.

1. Create a private environment file. Set `CISCO_TAILSCALE_ALLOWED_USERS` to the account permitted to connect, a random `CISCO_API_TOKEN` of at least 32 characters for fallback token access, the exact Vercel origin, optional website checks, and qBittorrent API credentials if you want download monitoring. For the fixed update service, also set `CISCO_DEPLOY_REPO_HOST_DIR` to the absolute path of this clean Git clone on the server and `CISCO_DEPLOY_ENV_FILE_HOST` to the absolute path of the private environment file. Keep both values local to the server.
2. Start or update the stack with `docker compose --env-file <private-env-file> -f compose/cisco-agent/compose.host-network.yaml up -d --build`. The first run builds the restricted agent, Docker guard, and loopback-only deploy service.
3. Run `tailscale serve --bg --https=8443 http://127.0.0.1:8001` on the host, or choose another unused HTTPS port if 8443 is occupied. Funnel stays disabled; the endpoint is visible only to your tailnet.
4. In CiscoAI, open the server icon and enter `https://<host-tailnet-dns-name>:8443/`; leave the token blank to use the allowed Tailscale login, or provide the configured fallback token. Keep the browser device connected to Tailscale.

Use the dashboard's server icon after connecting to see live host, container, website, and optional download status. The dashboard polls while it is open; it does not send background alerts while closed.

## Deploy with Portainer and a dedicated Tailscale device

Use the Portainer endpoint connected to the same local Docker Engine as the homelab. Portainer does not support Compose image builds for remote Agent endpoints, so the connector stack's build entries require the local Docker socket endpoint.

1. In the Tailscale admin console, enable HTTPS certificates for the tailnet and create a non-ephemeral auth key. Keep the key private. Do not enable Funnel for this service.
2. In Portainer, open **Stacks → Add stack → Repository**.
3. Set the repository to https://github.com/Lught6211/ubuntu-homelab-docker-guide, branch main, and Compose path compose/cisco-agent/compose.yaml.
4. Add the environment values below in the stack's environment-variable section. Portainer stores these outside Git; never put real values in this repository.

| Name | Required | Example / purpose |
|---|---|---|
| TS_AUTHKEY | Yes | The non-ephemeral Tailscale auth key |
| CISCO_API_TOKEN | Yes | Generate a 64-character token from CISCO's Homelab panel and paste the same token here; it must be at least 32 characters |
| CISCO_ALLOWED_ORIGINS | Yes | Comma-separated exact browser origins, e.g. https://project-cisco.vercel.app,http://localhost:3000; add your actual Vercel custom domain if you use one |
| CISCO_SERVER_LABEL | No | Friendly label shown in the dashboard, e.g. HOME SERVER |
| CISCO_MANAGED_SERVICES | No | JSON object from CISCO action name to exact Docker container_name, e.g. {"jellyfin":"jellyfin","caddy":"caddy"} |
| CISCO_MONITORED_SITES | No | JSON array such as [{"id":"jellyfin","name":"Jellyfin","url":"http://<LAN_IP>:8096/"}] |
| QBITTORRENT_URL | No | qBittorrent Web API base URL reachable from the Docker host, e.g. http://<LAN_IP>:8080 |
| QBITTORRENT_USERNAME | No | qBittorrent Web UI username |
| QBITTORRENT_PASSWORD | No | qBittorrent Web UI password |

Use the actual container_name from each service's Compose file. The defaults allow controls for containers named jellyfin and caddy; the agent only offers start/stop/restart buttons for containers in that allowlist. Add qBittorrent's container to the JSON map if you want to control it from CISCO.

Website monitors are checked from the server every 15 seconds with a 5-second timeout. Keep each URL specific to a service health page when that service provides one. A 4xx response is treated as reachable; a 5xx, timeout, or connection failure is reported as degraded/offline.

5. Deploy the stack and wait for the cisco-homelab machine to appear in Tailscale. Its HTTPS address is based on your tailnet domain; the Compose Tailscale Serve configuration discovers that domain automatically.
6. Confirm the machine is visible only to your tailnet. The Compose file has no ports mappings and AllowFunnel is false.
7. In CiscoAI, open the server icon, generate a token, then copy that token to CISCO_API_TOKEN in Portainer and redeploy the stack. Return to CiscoAI, enter the device's Tailscale HTTPS address and the same token, then connect.

Keep the requesting device connected to Tailscale while using the private server panel. The Vercel site cannot reach a private homelab from Vercel's cloud runtime; the browser talks directly to the Tailscale HTTPS endpoint.

## Use the dashboard or chat

- Open the server icon to view live host, container, site, and download status.
- The update area checks the approved guide repository when the panel opens and every ten minutes while it remains open. Use **DEPLOY UPDATE** only after reviewing the target commit and confirming the restart; progress appears in the same panel. The deployment rebuilds only the agent and Docker guard.
- Select START, STOP, or RESTART on an allowlisted container. CISCO asks for confirmation before each action.
- Pause/resume downloads from the qBittorrent list.
- Chat requests such as check my server, what is running, what websites are down, start/stop/restart Jellyfin, or pause a download name use the private server connector directly. CISCO asks before changing a container. Download controls are individual pause/resume actions.
- A server status indicator changes to offline if polling fails. The last received metrics may remain visible as stale context.

The chat actions are deterministic and bounded. They do not send a raw terminal command or shell prompt to the cloud AI backend.

## Troubleshooting

- **Connection failed / CORS:** add the exact browser origin (scheme and hostname, without a trailing slash) to CISCO_ALLOWED_ORIGINS, then redeploy.
- **Browser can't open the Tailscale address:** install and connect Tailscale on that device, confirm tailnet HTTPS is enabled, and verify the connector machine is online in the Tailscale admin console.
- **Docker status unavailable:** confirm Portainer deployed the stack to the local Docker socket endpoint and inspect the agent/guard container state in Portainer.
- **No websites listed:** add valid JSON to CISCO_MONITORED_SITES in Portainer and redeploy.
- **qBittorrent is not configured:** set all three qBittorrent variables in Portainer; ensure its Web API address is reachable from the host and its Web UI is allowed from the connector.
- **A restart button is missing:** verify the exact container name is present in CISCO_MANAGED_SERVICES.
- **Update check or deployment is unavailable:** confirm the host-network stack includes `cisco-deployer`, both `CISCO_DEPLOY_REPO_HOST_DIR` and `CISCO_DEPLOY_ENV_FILE_HOST` point to the correct server-side paths, the checkout is clean on `main`, and the deploy service can reach GitHub. The deploy service does not accept or execute arbitrary commands.

Do not copy tokens, passwords, local addresses, download names, or Tailscale keys into GitHub issues, the README, or browser screenshots.
