#!/usr/bin/env bash
# entrypoint-gcs.sh — Configure and start Globus Connect Server v5.4
# Runs once on first boot; subsequent boots detect an existing deployment
# and skip straight to starting services.
#
# Required environment variables (see Dockerfile.gcs for descriptions):
#   GCS_ENDPOINT_NAME, GCS_ORGANIZATION, GCS_CONTACT_EMAIL
#   GLOBUS_CLIENT_ID, GLOBUS_CLIENT_SECRET
#
# Optional:
#   GCS_OWNER, GCS_COLLECTION_NAME, STUROSCY_UID

set -euo pipefail

# ── helpers ──────────────────────────────────────────────────────────────────
log()  { echo "[GCS-INIT] $*"; }
die()  { echo "[GCS-INIT] ERROR: $*" >&2; exit 1; }

require_env() {
    for var in "$@"; do
        [[ -z "${!var:-}" ]] && die "Required environment variable \$$var is not set."
    done
}

# ── validate required vars ───────────────────────────────────────────────────
require_env GCS_ENDPOINT_NAME GCS_ORGANIZATION GCS_CONTACT_EMAIL \
            GLOBUS_CLIENT_ID GLOBUS_CLIENT_SECRET

COLLECTION_NAME="${GCS_COLLECTION_NAME:-sturoscy Home Collection}"
STATE_FILE="/var/lib/globus-connect-server/.gcs-docker-init-done"

# ── first-boot setup ─────────────────────────────────────────────────────────
if [[ ! -f "$STATE_FILE" ]]; then
    log "First boot — running full GCS setup..."

    # 1. Endpoint setup
    # --client-id / --client-secret authenticate as a confidential client so
    # no browser interaction is required (automated deployment mode).
    log "Setting up endpoint: ${GCS_ENDPOINT_NAME}"
    globus-connect-server endpoint setup \
        --agree-to-letsencrypt-tos \
        --client-id        "${GLOBUS_CLIENT_ID}" \
        --client-secret    "${GLOBUS_CLIENT_SECRET}" \
        --organization     "${GCS_ORGANIZATION}" \
        --contact-email    "${GCS_CONTACT_EMAIL}" \
        ${GCS_OWNER:+--owner "${GCS_OWNER}"} \
        "${GCS_ENDPOINT_NAME}"

    # 2. Node setup — configures Apache, GridFTP, and the Manager API
    log "Running node setup..."
    globus-connect-server node setup \
        --client-id     "${GLOBUS_CLIENT_ID}" \
        --client-secret "${GLOBUS_CLIENT_SECRET}"

    # 3. Create a POSIX storage gateway
    # The gateway maps Globus usernames to local POSIX accounts.
    # Identity mapping is set to "expression" so that the Globus username
    # portion before '@' is used as the local account name (e.g. sturoscy).
    log "Creating POSIX storage gateway..."
    GW_ID=$(globus-connect-server storage-gateway create posix \
        --client-id              "${GLOBUS_CLIENT_ID}" \
        --client-secret          "${GLOBUS_CLIENT_SECRET}" \
        --display-name           "POSIX Gateway" \
        --root                   "/" \
        --domain                 "globusid.org" \
        --identity-provider      "41143743-f3c8-4d60-bbdb-eeecaba85bd9" \
        --restrict-paths         "none" \
        --high-assurance         false \
        --format json \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

    log "Storage gateway created: ${GW_ID}"

    # 4. Create a mapped collection rooted at sturoscy's home directory
    # Using $HOME as path template so each mapped identity sees their home.
    log "Creating mapped collection: ${COLLECTION_NAME}"
    COLL_ID=$(globus-connect-server collection create \
        --client-id     "${GLOBUS_CLIENT_ID}" \
        --client-secret "${GLOBUS_CLIENT_SECRET}" \
        --display-name  "${COLLECTION_NAME}" \
        --root          "/home/sturoscy" \
        --format json \
        "${GW_ID}" \
        "/home/sturoscy" \
        "${COLLECTION_NAME}" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

    log "Mapped collection created: ${COLL_ID}"
    log "Collection visible at: https://app.globus.org/file-manager?origin_id=${COLL_ID}"

    # Persist state so we skip setup on subsequent container restarts
    mkdir -p "$(dirname "$STATE_FILE")"
    echo "endpoint_setup_complete" > "$STATE_FILE"
    echo "gateway_id=${GW_ID}"     >> "$STATE_FILE"
    echo "collection_id=${COLL_ID}" >> "$STATE_FILE"

    log "Setup complete."
else
    log "Existing GCS deployment detected — skipping setup."
    cat "$STATE_FILE"
fi

# ── start GCS services ───────────────────────────────────────────────────────
# GCS uses Apache (HTTPD) for the Manager API / HTTPS collections and
# globus-gridftp-server for data transfer. In a container we start them
# directly rather than via systemd.
log "Starting GridFTP..."
globus-gridftp-server \
    -c /etc/gridftp.conf \
    -pidfile /var/run/globus-gridftp-server.pid \
    &

log "Starting Apache (GCS Manager API)..."
exec apachectl -DFOREGROUND
