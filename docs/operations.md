# Operations Runbook

## 1. Routine checks

Run these commands from the host:

```bash
sudo systemctl status docker
sudo docker ps
sudo docker system df
df -h
free -h
sudo ss -lntup
```

Review unexpected listening ports, low disk space, stopped containers, and abnormal resource use.

## 2. Inspect a service

From the directory containing its Compose file:

```bash
docker compose ps
docker compose logs --tail=100
docker compose logs -f <service_name>
docker compose restart <service_name>
```

Use `sudo` before Docker commands if the current account lacks Docker socket permissions.

## 3. DNS checks

From a client with `nslookup` installed:

```text
nslookup vault.home.arpa <pihole-ip>
```

Replace the hostname and Pi-hole address with the values configured in the environment. Confirm that the response matches the expected homelab address. If it does not, check the local record, client DNS settings, and port 53 availability.

On Windows, clear the local resolver cache after DNS changes:

```powershell
ipconfig /flushdns
```

## 4. HTTPS and reverse-proxy checks

- Confirm the hostname resolves to the host running Caddy.
- Confirm Caddy and the upstream container share the configured Docker network.
- Inspect Caddy logs for upstream connection or certificate errors.
- Confirm that the client trusts the internal CA.
- Confirm that the upstream service is healthy before investigating proxy routing.

## 5. Pi-hole administration

Use the administration commands supported by the installed Pi-hole version. Consult the official documentation for password reset syntax because commands can differ between releases: https://docs.pi-hole.net/

## 6. Backups

Back up important application data and configuration using a method appropriate to each service. For database-backed or actively changing data, use a consistent application-aware backup procedure. Copy backups to separate storage, protect them with appropriate permissions or encryption, and periodically perform a restoration test.

A Docker named volume is persistent storage, not a backup.

## 7. Safe maintenance

Before upgrades:
1. Review release notes and compatibility changes.
2. Record current image versions.
3. Back up application data.
4. Update one service at a time where practical.
5. Verify service functionality and logs.
6. Document the outcome and any rollback.

Avoid destructive cleanup commands unless their effects are understood and the data is backed up.
