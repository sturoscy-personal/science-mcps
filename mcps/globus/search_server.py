import json
import logging
from typing import Annotated, Any, Callable, Dict

import globus_sdk
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from auth import get_globus_app
from schemas import (
    SearchCreateIndexResponse,
    SearchIndex,
    SearchIngestResponse,
    SearchIngestTask,
    SearchResult,
    SearchRole,
    SearchRoleList,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("Globus Search MCP Server")


def get_search_client():
    app = get_globus_app()
    scopes = globus_sdk.scopes.SearchScopes
    return globus_sdk.SearchClient(app=app, app_scopes=scopes.all)


def _format_search_response(res: globus_sdk.GlobusHTTPResponse) -> SearchResult:
    data = res.data
    return SearchResult(
        gmeta=data.get("gmeta", []),
        total=data.get("total", 0),
        offset=data.get("offset", 0),
        limit=data.get("limit", 10),
    )


def _format_index_list_response(
    res: globus_sdk.GlobusHTTPResponse,
) -> list[SearchIndex]:
    indices = []
    for idx_data in res.data.get("index_list", []):
        index = SearchIndex(
            index_id=idx_data["id"],
            display_name=idx_data["display_name"],
            description=idx_data.get("description"),
            status=idx_data["status"],
            size=idx_data.get("size"),
            num_subjects=idx_data.get("num_subjects"),
            owner=idx_data.get("owner") or idx_data.get("owner_id"),
        )
        indices.append(index)
    return indices


@mcp.tool
def create_index(
    display_name: Annotated[
        str, Field(description="Display name for the search index")
    ],
    description: Annotated[
        str, Field(description="Description of the search index", default="")
    ],
) -> SearchCreateIndexResponse:
    """Create a new Globus Search index."""
    sc = get_search_client()

    data = {"display_name": display_name}
    if description:
        data["description"] = description

    try:
        r = sc.create_index(**data)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to create index: {e}")

    return SearchCreateIndexResponse(index_id=r.data["id"])


@mcp.tool
def list_my_indices() -> list[SearchIndex]:
    """List Globus Search indices that the user has access to."""
    sc = get_search_client()

    try:
        r = sc.index_list()
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to list indices: {e}")

    return _format_index_list_response(r)


@mcp.tool
def get_index_info(
    index_id: Annotated[str, Field(description="ID of the search index")],
) -> SearchIndex:
    """Get detailed information about a specific Globus Search index."""
    sc = get_search_client()

    try:
        r = sc.get_index(index_id)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to get index info: {e}")

    idx_data = r.data
    return SearchIndex(
        index_id=idx_data["id"],
        display_name=idx_data["display_name"],
        description=idx_data.get("description"),
        status=idx_data["status"],
        size=idx_data.get("size"),
        num_subjects=idx_data.get("num_subjects"),
        owner=idx_data.get("owner") or idx_data.get("owner_id"),
    )


@mcp.tool
def delete_index(
    index_id: Annotated[str, Field(description="ID of the search index to delete")],
) -> Dict[str, str]:
    """Delete a Globus Search index. Only the index owner can delete an index."""
    sc = get_search_client()

    try:
        sc.delete_index(index_id)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to delete index: {e}")

    return {"message": f"Index {index_id} deleted successfully"}


@mcp.tool
def ingest_document(
    index_id: Annotated[str, Field(description="ID of the search index")],
    subject: Annotated[
        str, Field(description="Unique subject identifier for the document")
    ],
    content: Annotated[
        Dict[str, Any], Field(description="Document content as a JSON object")
    ],
    visible_to: Annotated[
        list[str],
        Field(
            description="List of principals who can see this document",
            default=["public"],
        ),
    ],
) -> SearchIngestResponse:
    """Ingest a single document into a Globus Search index."""
    sc = get_search_client()

    gmeta_doc = {
        "ingest_type": "GMetaEntry",
        "ingest_data": {
            "subject": subject,
            "visible_to": visible_to,
            "content": content,
        },
    }

    try:
        r = sc.ingest(index_id, gmeta_doc)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to ingest document: {e}")

    return SearchIngestResponse(task_id=r.data["task_id"])


@mcp.tool
def ingest_documents(
    index_id: Annotated[str, Field(description="ID of the search index")],
    documents: Annotated[
        list[Dict[str, Any]],
        Field(
            description="List of documents to ingest. Each document must have "
                        "'subject', 'content', and optionally 'visible_to' fields."
        ),
    ],
    max_batch_bytes: Annotated[
        int,
        Field(
            description="Max request payload size in bytes per batch. "
                        "Defaults to 8MB (safe margin under the 10MB Globus limit).",
            default=8_000_000,
        ),
    ],
    wait_for_completion: Annotated[
        bool,
        Field(
            description="If True, block until all ingest tasks reach a terminal state.",
            default=True,
        ),
    ],
) -> list[SearchIngestResponse]:
    """Ingest multiple documents into a Globus Search index, auto-batching by byte size."""
    import time

    sc = get_search_client()

    # --- 1. make_batches: split docs into byte-bounded batches ---
    def make_batches(docs, max_bytes):
        batch, batch_size = [], 0
        for doc in docs:
            if "subject" not in doc or "content" not in doc:
                raise ToolError("Each document must have 'subject' and 'content' fields")
            entry = {
                "subject": doc["subject"],
                "visible_to": doc.get("visible_to", ["public"]),
                "content": doc["content"],
            }
            entry_bytes = len(json.dumps(entry).encode("utf-8"))
            if batch and batch_size + entry_bytes > max_bytes:
                yield batch
                batch, batch_size = [], 0
            batch.append(entry)
            batch_size += entry_bytes
        if batch:
            yield batch

    # --- 2. ingest_all: fire each batch and collect task IDs ---
    responses = []
    interval = 1.0 / 10  # respect 10 req/s rate limit

    for batch in make_batches(documents, max_batch_bytes):
        gmeta_list = {
            "ingest_type": "GMetaList",
            "ingest_data": {"gmeta": batch},
        }
        try:
            r = sc.ingest(index_id, gmeta_list)
        except globus_sdk.GlobusAPIError as e:
            raise ToolError(f"Failed to ingest documents: {e}")
        responses.append(SearchIngestResponse(task_id=r.data["task_id"]))
        time.sleep(interval)

    # --- 3. poll_tasks: wait for all tasks to reach a terminal state ---
    if wait_for_completion:
        pending = {r.task_id for r in responses}
        while pending:
            done = set()
            for task_id in list(pending):
                try:
                    result = sc.get_task(task_id)
                    if result.data["state"] in ("SUCCESS", "FAILED"):
                        done.add(task_id)
                except globus_sdk.GlobusAPIError as e:
                    raise ToolError(f"Failed to poll task {task_id}: {e}")
            pending -= done
            if pending:
                time.sleep(2.0)

    return responses


@mcp.tool
def ingest_from_file(
    index_id: Annotated[str, Field(description="ID of the search index")],
    file_path: Annotated[
        str,
        Field(
            description="Absolute path to a JSON file containing a list of documents. "
                        "Each document must have 'subject', 'content', and optionally 'visible_to' fields."
        ),
    ],
    max_batch_bytes: Annotated[
        int,
        Field(
            description="Max request payload size in bytes per batch. Defaults to 8MB.",
            default=8_000_000,
        ),
    ] = 8_000_000,
    wait_for_completion: Annotated[
        bool,
        Field(
            description="If True, block until all ingest tasks reach a terminal state.",
            default=True,
        ),
    ] = True,
) -> list[SearchIngestResponse]:
    """Ingest documents from a local JSON file into a Globus Search index."""
    import os

    if not os.path.isfile(file_path):
        raise ToolError(f"File not found: {file_path}")
    with open(file_path, encoding="utf-8") as f:
        documents = json.load(f)
    if not isinstance(documents, list):
        raise ToolError("File must contain a JSON array of documents")
    return ingest_documents(index_id, documents, max_batch_bytes, wait_for_completion)


@mcp.tool
def get_ingestion_status(
    task_id: Annotated[str, Field(description="ID of the ingestion task")],
) -> SearchIngestTask:
    """Get the status of a document ingestion task."""
    sc = get_search_client()

    try:
        r = sc.get_task(task_id)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to get task status: {e}")

    task_data = r.data
    return SearchIngestTask(
        task_id=task_data["task_id"],
        status=task_data["state"],
        message=task_data.get("message"),
    )


@mcp.tool
def delete_subject(
    index_id: Annotated[str, Field(description="ID of the search index")],
    subject: Annotated[str, Field(description="Subject identifier to delete")],
) -> Dict[str, str]:
    """Delete a subject and all its entries from a Globus Search index."""
    sc = get_search_client()

    try:
        sc.delete_subject(index_id, subject)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to delete subject: {e}")

    return {"message": f"Subject '{subject}' deleted from index {index_id}"}


@mcp.tool
def delete_by_query(
    index_id: Annotated[str, Field(description="ID of the search index")],
    query: Annotated[
        str,
        Field(
            description=(
                "Search query string. Use '*' to delete all documents in the index."
            )
        ),
    ],
) -> SearchIngestResponse:
    """Delete all documents in a Globus Search index that match a query string."""
    sc = get_search_client()

    try:
        r = sc.delete_by_query(index_id, {"q": query})
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to delete by query: {e}")

    return SearchIngestResponse(task_id=r.data["task_id"])


@mcp.tool
def search_index(
    index_id: Annotated[str, Field(description="ID of the search index")],
    query: Annotated[str, Field(description="Search query string")],
    limit: Annotated[
        int, Field(description="Maximum number of results to return", default=10)
    ],
    offset: Annotated[
        int, Field(description="Number of results to skip for pagination", default=0)
    ],
) -> SearchResult:
    """Search for documents in a Globus Search index using a simple query string."""
    sc = get_search_client()

    try:
        r = sc.search(index_id, q=query, limit=limit, offset=offset)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Search failed: {e}")

    return _format_search_response(r)


@mcp.tool
def advanced_search(
    index_id: Annotated[str, Field(description="ID of the search index")],
    search_params: Annotated[
        Dict[str, Any],
        Field(
            description="Advanced search parameters including query, filters, facets, sorting"
        ),
    ],
) -> SearchResult:
    """Perform an advanced search with complex filters, facets, and sorting."""
    sc = get_search_client()

    try:
        r = sc.post_search(index_id, search_params)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Advanced search failed: {e}")

    return _format_search_response(r)


@mcp.tool
def get_subject(
    index_id: Annotated[str, Field(description="ID of the search index")],
    subject: Annotated[str, Field(description="Subject identifier to retrieve")],
) -> Dict[str, Any]:
    """Get detailed information about a specific subject in a Globus Search index."""
    sc = get_search_client()

    try:
        r = sc.get_subject(index_id, subject)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to get subject: {e}")

    return r.data


@mcp.tool
def get_index_roles(
    index_id: Annotated[str, Field(description="ID of the search index")],
) -> SearchRoleList:
    """Get all role assignments on a Globus Search index."""
    sc = get_search_client()

    try:
        r = sc.get_role_list(index_id)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to get roles: {e}")

    roles = [
        SearchRole(
            role_id=entry["id"],
            principal=entry["principal"],
            role=entry["role_name"],
        )
        for entry in r.data.get("role_list", [])
    ]
    return SearchRoleList(roles=roles)


@mcp.tool
def create_role(
    index_id: Annotated[str, Field(description="ID of the search index")],
    principal: Annotated[
        str,
        Field(
            description=(
                "Principal URN to assign the role to. "
                "Use 'urn:globus:auth:identity:<uuid>' for a user or "
                "'urn:globus:groups:id:<uuid>' for a group."
            )
        ),
    ],
    role: Annotated[
        str,
        Field(
            description="Role to assign: 'owner', 'admin', 'writer', or 'reader'"
        ),
    ],
) -> SearchRole:
    """Create a role assignment on a Globus Search index."""
    sc = get_search_client()

    try:
        r = sc.create_role(index_id, {"principal": principal, "role_name": role})
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to create role: {e}")

    data = r.data
    return SearchRole(
        role_id=data["id"],
        principal=data["principal"],
        role=data["role"],
    )


@mcp.tool
def delete_role(
    index_id: Annotated[str, Field(description="ID of the search index")],
    role_id: Annotated[str, Field(description="ID of the role assignment to delete")],
) -> Dict[str, str]:
    """Delete a role assignment from a Globus Search index."""
    sc = get_search_client()

    try:
        sc.delete_role(index_id, role_id)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to delete role: {e}")

    return {"message": f"Role {role_id} deleted from index {index_id}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
