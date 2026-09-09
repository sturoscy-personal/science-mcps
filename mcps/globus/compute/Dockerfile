FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user — Globus Compute endpoint should not run as root
RUN useradd -m -s /bin/bash compute_user

WORKDIR /home/compute_user

# Install Globus Compute endpoint and SDK, plus globus-sdk for the ingest function
RUN pip install --no-cache-dir \
    globus-compute-endpoint \
    globus-compute-sdk \
    globus-sdk

# Switch to non-root user
USER compute_user

# Create the Globus Compute config directory
RUN mkdir -p /home/compute_user/.globus_compute

# Copy the endpoint entrypoint script
COPY --chown=compute_user:compute_user entrypoint.sh /home/compute_user/entrypoint.sh
RUN chmod +x /home/compute_user/entrypoint.sh

# Mount point for persisting auth tokens and endpoint config between container restarts
VOLUME /home/compute_user/.globus_compute

ENTRYPOINT ["/home/compute_user/entrypoint.sh"]