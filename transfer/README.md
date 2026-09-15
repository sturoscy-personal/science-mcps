# Globus Connect Server v5.4 — Docker Setup

Runs a Globus Connect Server v5.4 endpoint on Ubuntu 22.04 with a POSIX mapped collection for the `sturoscy` user.

## Files

- `Dockerfile.gcs` — builds the image (installs GCS, creates the `sturoscy` local account, exposes ports)
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
  -e GCS_ORGANIZATION="University of Chicago" \
  -e GCS_CONTACT_EMAIL="sturoscy@uchicago.edu" \
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
| `GCS_COLLECTION_NAME` | — | Display name for the mapped collection (default: `sturoscy Home Collection`) |
| `STUROSCY_UID` | — | UID for the local `sturoscy` account (default: `1001`, set at build time via `--build-arg`) |

## Ports

| Port | Purpose |
|---|---|
| `443` | HTTPS — GCS Manager API and HTTPS collections |
| `50000–51000` | GridFTP data channel range |

## What the entrypoint does

1. **`endpoint setup`** — registers the endpoint with Globus using confidential client credentials (no browser interaction needed)
2. **`node setup`** — configures Apache and GridFTP
3. **`storage-gateway create posix`** — creates a POSIX gateway that maps Globus usernames to local accounts
4. **`collection create`** — creates a mapped collection rooted at `/home/sturoscy`

The collection ID is printed to the log and written to `/var/lib/globus-connect-server/.gcs-docker-init-done`. Once setup is complete, GridFTP and Apache start in the foreground.

## References

- [GCS v5.4 Installation Guide](https://docs.globus.org/globus-connect-server/v5.4/index.html)
- [Automated Endpoint Deployment](https://docs.globus.org/globus-connect-server/v5.4/automated-deployment/)
- [Storage Gateway Create POSIX](https://docs.globus.org/globus-connect-server/v5.4/reference/storage-gateway/create/posix/)
- [Collection Create Reference](https://docs.globus.org/globus-connect-server/v5.4/reference/collection/create/)
