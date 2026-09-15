# Globus Search MCP Server

Enables Claude to create search indices, ingest documents, and perform searches across [Globus Search](https://docs.globus.org/api/search/) indexes.

## Prerequisites

- Python 3.11
- A [Globus account](https://www.globus.org/)
- Claude Desktop or Claude Code

## Installation

**Using conda:**

```bash
git clone https://github.com/globus-labs/science-mcps
cd science-mcps/mcps/globus
conda create -n science-mcps python=3.11
conda activate science-mcps
pip install -r requirements.txt
```

**Using uv:**

```bash
git clone https://github.com/globus-labs/science-mcps
cd science-mcps/mcps/globus
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
```

If you don't have uv installed: `pip install uv` or see [uv's docs](https://docs.astral.sh/uv/).

## Adding to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`, replacing the paths with your actual paths:

```json
{
  "mcpServers": {
    "globus-search-mcp": {
      "command": "/path/to/your/env/python",
      "args": ["/path/to/science-mcps/mcps/globus/search_server.py"]
    }
  }
}
```

Restart Claude Desktop after saving.

## Adding to Claude Code

Add the server to your project's `.claude/settings.json` or run:

```bash
claude mcp add globus-search-mcp /path/to/your/env/python -- /path/to/science-mcps/mcps/globus/search_server.py
```

Or add it manually to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "globus-search-mcp": {
      "command": "/path/to/your/env/python",
      "args": ["/path/to/science-mcps/mcps/globus/search_server.py"]
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `create_index` | Create a new Globus Search index |
| `list_my_indices` | List search indices you have access to |
| `get_index_info` | Get details about a specific index |
| `ingest_document` | Ingest a single document |
| `ingest_documents` | Ingest multiple documents |
| `get_ingestion_status` | Check the status of an ingestion task |
| `search_index` | Search using a simple query string |
| `advanced_search` | Search with filters, facets, and sorting |
| `get_subject` | Get details about a specific subject |
| `delete_subject` | Delete a subject and all its entries |

## Sample Data

An example EV adoption dataset is available for testing:

```bash
curl -O https://gateways-2026-globus-search-data.s3.us-east-1.amazonaws.com/ev-data.csv
```

OR

```bash
curl -O https://data.wa.gov/api/v3/views/f6w7-q2d2/export.csv
```

## Example Usage

Once configured, you can ask Claude:

```
List the Globus Search indices I am an admin for.
```
