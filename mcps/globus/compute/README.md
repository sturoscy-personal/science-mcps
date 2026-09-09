# Setting Up a Globus Compute Endpoint

This guide walks through setting up a Globus Compute endpoint — either locally or via Docker — and using the MCP tools to register and execute Python functions against a Globus Search index.

---

## Prerequisites

- MCP server (`compute_server.py`) running with `register_endpoint`, `register_python_function`, `submit_task`, and `get_task_status` tools available
- Your Globus `client_id` from `auth.py`
- Docker installed (for the Docker approach), or Python 3.9+ on Linux (for the local approach)

> **Note:** The `register_endpoint` tool must appear **before** `mcp.run(transport="stdio")` in `compute_server.py` or it will not be registered.

> **Platform note:** The Globus Compute endpoint daemon is only supported on **Linux**. The Docker approach is recommended if you are on macOS or Windows, as it provides a clean Linux environment without additional setup.

---

## Approach A: Docker (Recommended)

Docker gives you a clean, reproducible Linux environment with full control over the Python version and dependencies. Auth tokens and endpoint config are persisted in a Docker volume so you only need to authenticate once.

### Step A1: Create the Project Files

Create a directory for your endpoint and add the following two files.

**`Dockerfile`**

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user — Globus Compute should not run as root
RUN useradd -m -s /bin/bash compute_user

WORKDIR /home/compute_user

# Install Globus Compute endpoint, SDK, and globus-sdk
RUN pip install --no-cache-dir \
    globus-compute-endpoint \
    globus-compute-sdk \
    globus-sdk

USER compute_user

# Create the Globus Compute config directory
RUN mkdir -p /home/compute_user/.globus_compute

COPY --chown=compute_user:compute_user entrypoint.sh /home/compute_user/entrypoint.sh
RUN chmod +x /home/compute_user/entrypoint.sh

# Persist auth tokens and endpoint config between container restarts
VOLUME /home/compute_user/.globus_compute

ENTRYPOINT ["/home/compute_user/entrypoint.sh"]
```

**`entrypoint.sh`**

```bash
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
```

### Step A2: Build the Image

```bash
docker build -t globus-compute-ingest .
```

### Step A3: Start the Container

```bash
docker run -it \
    -v globus_compute_data:/home/compute_user/.globus_compute \
    -v ~/.config/globus:/home/compute_user/.config/globus:ro \
    -e ENDPOINT_NAME=gateways-ingest-endpoint \
    globus-compute-ingest
```

The second volume mount shares your host's Globus token cache (read-only) with the container. This is useful for functions that need to authenticate to Globus services as your user. On first run, the container will print a Globus auth URL for the **Compute** endpoint itself. Open it in a browser, authenticate, and paste the code back into the terminal. You will then see:

```
Starting endpoint; registered with UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**Copy that UUID** — you will need it for task submission.

The `-v globus_compute_data:...` volume mount persists the endpoint config and Compute tokens. On subsequent runs the container starts without prompting for auth again.

> **Foreground by default:** `globus-compute-endpoint start` runs in the foreground unless `--detach` is passed. Omitting `--detach` is what keeps the process alive inside the container so Docker can manage its lifecycle.

### Step A4: Verify the Endpoint is Running

In a separate terminal:

```bash
docker exec <container_id> globus-compute-endpoint list
```

You should see `gateways-ingest-endpoint` with status `running`.

---

## Approach B: Local Installation (Linux Only)

If you are already on Linux and prefer not to use Docker.

### Step B1: Install the Compute Endpoint Package

```bash
pip install globus-compute-endpoint globus-compute-sdk globus-sdk
```

### Step B2: Configure the Endpoint

```bash
globus-compute-endpoint configure gateways-ingest-endpoint
```

This creates a config directory at `~/.globus_compute/gateways-ingest-endpoint/config.yaml`. The defaults are fine for local single-user use. To verify:

```bash
cat ~/.globus_compute/gateways-ingest-endpoint/config.yaml
```

You should see something like:

```yaml
engine:
  type: GlobusComputeEngine
  max_workers: 1
```

### Step B3: Start the Endpoint

```bash
globus-compute-endpoint start gateways-ingest-endpoint
```

On first run this will prompt you to authenticate with Globus. Follow the link, log in, and paste the auth code back. Once authenticated you will see:

```
Starting endpoint; registered with UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**Copy that UUID** — you will need it for task submission.

Verify the endpoint is running:

```bash
globus-compute-endpoint list
```

---

## Step 1: Register the Endpoint via the MCP Tool

> This step applies to both Docker and local approaches.

Use the `register_endpoint` MCP tool to make the endpoint known to your server:

```
register_endpoint(
    display_name="gateways-ingest-endpoint",
    public=False
)
```

This should return the same UUID you saw during startup, confirming the API-side registration is in sync.

---

## Step 2: Register and Run a Function

See the **Example: EV Adoption Heatmap** section below for a complete walkthrough of registering a function with `register_python_function` and submitting it with `submit_task`.

**Rules for functions that run on a Compute endpoint:**

- All imports must be **inside the function body**
- The function must be **fully self-contained**
- Auth credentials must be accessible inside the container or on the local machine if the function calls authenticated Globus services

---

## Summary of IDs to Track

| ID | What it is |
|---|---|
| Endpoint UUID | Your Globus Compute worker (Docker container or local) |
| Function UUID | A registered Python function |
| Compute Task ID | A single execution of that function on your endpoint |

---

## Troubleshooting

**Docker: container exits immediately after starting:** Make sure `--detach` is **not** passed in `entrypoint.sh`. The endpoint runs in the foreground by default, which is what keeps the container alive. Passing `--detach` causes it to daemonize and the container exits immediately.

**Docker: re-authenticating after token expiry:** There are two separate token caches to consider:

- **Compute tokens** (stored in the `globus_compute_data` volume): If these expire, exec into the running container and re-login:
  ```bash
  docker exec -it <container_id> globus-compute-endpoint login
  ```
  If that fails, remove the volume and re-run the container interactively to go through the full auth flow again:
  ```bash
  docker volume rm globus_compute_data
  docker run -it \
      -v globus_compute_data:/home/compute_user/.globus_compute \
      -v ~/.config/globus:/home/compute_user/.config/globus:ro \
      -e ENDPOINT_NAME=gateways-ingest-endpoint \
      globus-compute-ingest
  ```

**Function not found / serialization error:** If `register_python_function` succeeds but `submit_task` fails with a deserialization error, confirm that all packages the function imports are installed in the endpoint environment. For Docker this is handled by the Dockerfile. For local installs, e.g.:

```bash
pip install globus-sdk
```

**Python version mismatch:** The Dockerfile uses Python 3.11. If your MCP server is running a different Python version, function serialization may fail. Make sure both environments use the same Python version.

**Endpoint not accepting tasks:** Check the endpoint status:

```bash
# Docker
docker exec <container_id> globus-compute-endpoint list

# Local
globus-compute-endpoint list
```

If the status is `stopped`, restart it:

```bash
# Docker — restart the container
docker start <container_id>

# Local
globus-compute-endpoint start gateways-ingest-endpoint
```

**`register_endpoint` tool not found:** Check that it appears before `mcp.run(transport="stdio")` in `compute_server.py`.

---

## Example: EV Adoption Heatmap

This example demonstrates a more analytical Compute function — one that **reads** from a Globus Search index rather than writing to it. It queries the EV registration index, aggregates vehicle counts by county and model year, and returns heatmap-ready data.

### The Function

The full source lives in [`ev_adoption_heatmap.py`](ev_adoption_heatmap.py). Because the EV data was ingested with `visible_to: ["public"]`, this function uses an unauthenticated `SearchClient` and requires no token setup on the endpoint.

```python
def ev_adoption_heatmap(index_id: str, min_year: int = 2010, max_year: int = 2027):
    import globus_sdk
    from collections import defaultdict

    client = globus_sdk.SearchClient()

    county_year_counts = defaultdict(lambda: defaultdict(int))
    offset = 0
    limit = 100

    while True:
        response = client.post_search(
            index_id,
            {"q": "*", "limit": limit, "offset": offset},
        )
        hits = response.get("gmeta", [])
        if not hits:
            break

        for hit in hits:
            content = hit["entries"][0]["content"]
            county = content.get("county", "Unknown")
            year = content.get("model_year")
            if year and min_year <= year <= max_year:
                county_year_counts[county][year] += 1

        offset += limit
        if offset >= response.get("total", 0):
            break

    rows = [
        {"county": county, "model_year": year, "count": count}
        for county, years in sorted(county_year_counts.items())
        for year, count in sorted(years.items())
    ]

    return {
        "index_id": index_id,
        "min_year": min_year,
        "max_year": max_year,
        "total_records": sum(r["count"] for r in rows),
        "counties": sorted(county_year_counts.keys()),
        "rows": rows,
    }
```

### Step H1: Register the Function

```
register_python_function(
    function_name="ev_adoption_heatmap",
    function_code="<paste the function above>",
    description="Aggregate WA EV registrations by county and model year for heatmap visualization"
)
```

Copy the returned `function_id`. The current registered function ID is `c76de125-80f2-4eb8-9375-ecacce43add8`.

### Step H2: Submit the Task

```
submit_task(
    endpoint_id="<UUID from startup>",
    function_id="<function_id from Step H1>",
    function_args=[],
    function_kwargs={
        "index_id": "d695fa67-64cb-486c-aa45-e39fb54225eb",
        "min_year": 2015,
        "max_year": 2024
    }
)
```

### Step H3: Poll for Completion

```
get_task_status(task_id="<task_id from Step H2>")
```

When `status` is `"success"`, `result` will contain the aggregated rows:

```json
{
  "index_id": "d695fa67-64cb-486c-aa45-e39fb54225eb",
  "min_year": 2015,
  "max_year": 2024,
  "total_records": 4821,
  "counties": ["King", "Kitsap", "Snohomish", "Thurston", "Yakima"],
  "rows": [
    {"county": "King", "model_year": 2015, "count": 312},
    {"county": "King", "model_year": 2016, "count": 489},
    ...
  ]
}
```

The `rows` list is ready to pivot into a county × year matrix for any heatmap library (matplotlib `imshow`, seaborn `heatmap`, Plotly, etc.).

---

## Teardown

Run these steps in order when you are done experimenting.

### 1. Clear and delete the Search index

```
delete_by_query(index_id="<your-index-id>", query="*")
```

Then delete the index itself:

```
delete_index(index_id="<your-index-id>")
```

### 2. Stop and remove the Compute endpoint

Stop the Docker container:

```bash
docker stop <container_id>
```

Delete the endpoint registration via the MCP tool:

```
delete_endpoint(endpoint_id="<your-endpoint-id>")
```

Optionally remove the Docker volume to clear stored tokens and endpoint config:

```bash
docker volume rm globus_compute_data
```

### 3. Delete the registered function (optional)

```
delete_function(function_id="<your-function-id>")
```

### 4. Remove local files (optional)

```bash
rm mcps/globus/compute/ev-data-ingest.json
```