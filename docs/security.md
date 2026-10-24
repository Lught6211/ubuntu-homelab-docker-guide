# Security Considerations

## 1. Security baseline

This homelab is intended for private-network use. The examples are not a complete security audit and do not make the host or services automatically secure.

## 2. Network exposure

- Do not forward sensitive service ports from the public internet by default.
- Limit SSH, Portainer, Pi-hole administration, and Vaultwarden access to trusted devices and users.
- Review Docker-published ports as well as host firewall rules. Published container ports can create access paths that should not be assumed blocked by a basic UFW configuration.
- Use a VPN for remote access when appropriate, rather than exposing administrative interfaces directly.
- Keep the Ubuntu host and container images updated using a controlled process.

## 3. Docker privileges

Portainer requires access to the Docker socket for management. Access to `/var/run/docker.sock` can permit powerful operations on the host and should be treated as administrator-level access. Do not expose Portainer to untrusted networks.

## 4. Vaultwarden

- Keep the service on a private network and serve browser traffic over HTTPS.
- Disable open registration after creating the intended account or accounts.
- Use strong, unique credentials and enable available account protections.
- Back up the application data securely and test recovery.
- Do not commit vault data, database files, secrets, or private keys to Git.
- Avoid relying on browser insecure-origin flags outside temporary testing.

## 5. Internal TLS

Caddy's internal CA can issue certificates for private hostnames. Client devices must trust the corresponding root certificate to validate those certificates without warnings. Protect the CA private key and persist Caddy's data directory. A valid internal certificate does not itself authenticate users or control network access.

## 6. Secrets and repository hygiene

Use environment variables or a suitable secrets mechanism for sensitive configuration. Keep local override files out of version control where appropriate. The provided `.gitignore` excludes common local secret and data files, but it is not a substitute for reviewing every file before committing.

## 7. Updates and backups

Back up persistent data before upgrades. Prefer tested image versions over unreviewed automatic updates for sensitive services. Keep at least one backup separate from the homelab host, protect it from unauthorized access, and periodically test restoration.

## 8. Incident response

If a service is unexpectedly exposed or a credential may have leaked, restrict network access first, rotate affected credentials or keys, inspect logs, update the affected service, and restore from a known-good backup if required. Document the incident and corrective actions.
