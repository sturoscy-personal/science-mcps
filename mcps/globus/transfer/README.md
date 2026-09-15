# Globus Connect Server v5.4 — Docker Setup

Runs a Globus Connect Server v5.4 endpoint on Ubuntu 22.04 with a POSIX mapped collection. No user is pre-baked into the image — identity mapping is handled dynamically at runtime by GCS.

## Files

- `Dockerfile.gcs` — builds the image (installs GCS, exposes ports)
- `entrypoint-gcs.sh` — runtime script that registers the endpoint, creates the storage gateway and mapped collection, then starts GCS services

## Prerequisites

Register a Globus confidential client at [app.globus.org](https://app.globus.org) under **Settings → Developers**. The client needs the "Manage Endpoints" scope.

## Build

```bash
docker build -f Dockerfile.gcs -t gcs54 .
```

## Run

```bash
docker run -d \
  -e GCS_ENDPOINT_NAME="My GCS Endpoint" \
  -e GCS_ORGANIZATION="My Organization" \
  -e GCS_CONTACT_EMAIL="admin@example.org" \
  -e GLOBUS_CLIENT_ID="<your-client-uuid>" \
  -e GLOBUS_CLIENT_SECRET="<your-client-secret>" \
  -p 443:443 \
  -p 50000-51000:50000-51000 \
  -v gcs-data:/var/lib/globus-connect-server \
  gcs54
```

Mount `/var/lib/globus-connect-server` as a volume so endpoint credentials and state survive restarts. On first boot the entrypoint runs the full setup; subsequent starts detect the state file and skip straight to launching services.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GCS_ENDPOINT_NAME` | ✓ | Human-readable endpoint name shown in Globus Web App |
| `GCS_ORGANIZATION` | ✓ | Organization name |
| `GCS_CONTACT_EMAIL` | ✓ | Admin contact email |
| `GLOBUS_CLIENT_ID` | ✓ | UUID of your confidential client |
| `GLOBUS_CLIENT_SECRET` | ✓ | Secret for the above client |
| `GCS_OWNER` | — | Globus identity URN of the endpoint owner (defaults to the client identity) |
| `GCS_GATEWAY_NAME` | — | Display name for the POSIX storage gateway (default: `POSIX Gateway`) |
| `GCS_GATEWAY_ROOT` | — | Filesystem root exposed by the gateway (default: `/`) |
| `GCS_COLLECTION_NAME` | — | Display name for the mapped collection (default: `Home Collection`) |
| `GCS_COLLECTION_ROOT` | — | Filesystem root for the mapped collection (default: `/home`) |

## Ports

| Port | Purpose |
|---|---|
| `443` | HTTPS — GCS Manager API and HTTPS collections |
| `50000–51000` | GridFTP data channel range |

## What the entrypoint does

1. **`endpoint setup`** — registers the endpoint with Globus using confidential client credentials (no browser interaction needed)
2. **`node setup`** — configures Apache and GridFTP
3. **`storage-gateway create posix`** — creates a POSIX gateway rooted at `GCS_GATEWAY_ROOT`; Globus usernames are mapped to local POSIX accounts dynamically at access time
4. **`collection create`** — creates a mapped collection rooted at `GCS_COLLECTION_ROOT` (default `/home`)

The collection ID is printed to the log and written to `/var/lib/globus-connect-server/.gcs-docker-init-done`. Once setup is complete, GridFTP and Apache start in the foreground.

## Dynamic identity mapping

The GCS POSIX connector maps each incoming Globus identity to a local POSIX account. The local username is derived from the Globus identity — typically the portion before `@` in the Globus username (e.g. `alice@globusid.org` → local account `alice`). That account must exist inside the container before a transfer is attempted.

### Option 1 — `docker exec` (simplest, one-off)

Add a user to a running container:

```bash
docker exec -it <container_name> \
  useradd --create-home --shell /bin/bash alice
```

The account disappears when the container is replaced. Combine with a named volume on `/home` to persist the home directories across restarts:

```bash
docker run -d \
  ...
  -v gcs-home:/home \
  gcs54
```

### Option 2 — users file at startup (recommended for small, static sets)

Mount a plain-text file listing users to create, one per line, and extend `entrypoint-gcs.sh` to read it before GCS starts:

```
# users.txt
alice
bob
carol
```

```bash
docker run -d \
  ...
  -v ./users.txt:/etc/gcs-users.txt:ro \
  -v gcs-home:/home \
  gcs54
```

Add the following block to `entrypoint-gcs.sh` before the `globus-connect-server endpoint setup` call:

```bash
if [[ -f /etc/gcs-users.txt ]]; then
    while IFS= read -r username || [[ -n "$username" ]]; do
        [[ -z "$username" || "$username" == \#* ]] && continue
        if ! id "$username" &>/dev/null; then
            useradd --create-home --shell /bin/bash "$username"
            log "Created local account: $username"
        fi
    done < /etc/gcs-users.txt
fi
```

### Option 3 — bind-mount host `/etc/passwd` and `/home` (shares host accounts)

Map the host's user database and home directories directly into the container so every host account is instantly available without any extra setup:

```bash
docker run -d \
  ...
  -v /etc/passwd:/etc/passwd:ro \
  -v /etc/shadow:/etc/shadow:ro \
  -v /etc/group:/etc/group:ro \
  -v /home:/home \
  gcs54
```

New host accounts become visible immediately without restarting the container. Note that the container runs as root, so bind-mounting `/etc/shadow` grants it read access to hashed passwords — only do this on trusted hosts.

### Option 4 — LDAP / NSS (production, large or dynamic user populations)

Install an NSS module such as `libnss-ldapd` or `sssd` into the image and point it at your directory service. GCS will resolve usernames through the system NSS stack, so any account in the directory is automatically available without managing a local user database. This is the recommended approach when users are managed centrally (e.g. university LDAP or Active Directory).

Refer to your distribution's documentation for SSSD or nslcd configuration.

## References

- [GCS v5.4 Installation Guide](https://docs.globus.org/globus-connect-server/v5.4/index.html)
- [Automated Endpoint Deployment](https://docs.globus.org/globus-connect-server/v5.4/automated-deployment/)
- [Storage Gateway Create POSIX](https://docs.globus.org/globus-connect-server/v5.4/reference/storage-gateway/create/posix/)
- [Collection Create Reference](https://docs.globus.org/globus-connect-server/v5.4/reference/collection/create/)
