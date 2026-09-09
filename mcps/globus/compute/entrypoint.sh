#!/bin/bash
set -e

ENDPOINT_NAME="${ENDPOINT_NAME:-gateways-ingest-endpoint}"

# Configure the endpoint if it doesn't already exist
if [ ! -d "$HOME/.globus_compute/$ENDPOINT_NAME" ]; then
    echo "Configuring endpoint: $ENDPOINT_NAME"
    globus-compute-endpoint configure "$ENDPOINT_NAME"
fi

echo "Starting endpoint: $ENDPOINT_NAME"
exec globus-compute-endpoint start "$ENDPOINT_NAME"