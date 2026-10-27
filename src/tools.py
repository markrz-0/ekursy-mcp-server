import json
import httpx
import urllib.parse
from fastmcp.exceptions import ToolError
from config import TIMEOUT
from config import ACCOUNT_SETUP_TOKEN_TTL, MCP_PUBLIC_URL
from server import mcp
from auth import fetch_with_auth
from accounts import get_account_store
from identity import require_current_account
from parsers import (
    parse_page_fragments,
    format_grades_hierarchy,
    save_resource,
    format_resource,
    format_forum_details,
    format_discussion_details
)

# 4. MCP Tools Registration

PROFILE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "id": {"type": "string", "minLength": 1, "pattern": r"\S"},
        "name": {"type": "string"},
        "nickname": {"type": "string"},
    },
    "required": ["id"],
    "additionalProperties": False,
}


def _require_moodle_user_id() -> str:
    account = require_current_account()
    if account.id != "local" and not account.has_credentials:
        raise ToolError(
            "Moodle credentials are not configured. "
            "Call create_account_setup_link and open the returned link."
        )
    return account.id


@mcp.tool(
    title="Current eKursy connection",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
    output_schema=PROFILE_SCHEMA,
    meta={"openai/profile": True},
)
async def get_connection_profile() -> dict[str, str]:
    """Return the stable profile represented by the authenticated connection."""
    account = require_current_account()
    return {
        "id": account.id,
        "name": account.github_login,
        "nickname": f"{account.github_login} — eKursy",
    }


@mcp.tool(
    title="Create Moodle account setup link",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def create_account_setup_link() -> str:
    """Create a short-lived browser link for adding or replacing Moodle credentials."""
    account = require_current_account()
    if account.id == "local":
        raise ToolError("Account setup links are only available in OAuth mode")
    token = get_account_store().create_setup_token(
        account.id, ACCOUNT_SETUP_TOKEN_TTL
    )
    return (
        f"{MCP_PUBLIC_URL}/account/setup?token="
        f"{urllib.parse.quote(token, safe='')}"
    )

@mcp.tool()
async def get_user_profile() -> str:
    """Fetch the authenticated student's profile information and USOS number."""
    user_id = _require_moodle_user_id()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, user_id, "/api/me")
        if response.is_success:
            return json.dumps(response.json(), indent=2)
        return f"Error: {response.json().get('msg')}"

@mcp.tool()
async def list_courses() -> str:
    """Get a list of all courses the student is enrolled in."""
    user_id = _require_moodle_user_id()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, user_id, "/api/course_list")
        if response.is_success:
            return json.dumps(response.json().get("courses", []), indent=2)
        return f"Error: {response.json().get('msg')}"

@mcp.tool()
async def get_course_content(id: str) -> str:
    """
    Get the detailed page fragments and sections for a specific course (including presentations, lecturer names, assignments, and other files).
    
    Args:
        id: The internal unique course identifier string.
    """
    user_id = _require_moodle_user_id()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, user_id, f"/api/course?id={id}")
        data = response.json()
        if not response.is_success:
            return f"Error: {data.get('msg')}"
        return parse_page_fragments(data.get("result", []))

@mcp.tool()
async def get_course_grades(id: str) -> str:
    """
    Fetch the hierarchical gradebook for a specific course.
    
    Args:
        id: The internal unique course identifier string.
    """
    user_id = _require_moodle_user_id()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(
            client, user_id, f"/api/course_grades?id={id}"
        )
        data = response.json()
        
        if not response.is_success:
            return f"Error: {data.get('msg', 'Failed to fetch grades')}"

        formatted_grades = format_grades_hierarchy(data.get("result", []))
        return formatted_grades if formatted_grades else "No grades found for this course."

@mcp.tool()
async def resolve_material_link(resourceId: str, kind: str, savepath: str | None = None):
    """
    Download and parse internal university files (PDFs, Images) - resource.
    
    Args:
        resourceId: Unique id of the resource
        kind: Resource type selections (e.g., 'resource', 'assign')
        savepath: Optional directory path to save the resource instead of parsing it.
    """
    target_path = f"/api/resource?id={resourceId}&kind={kind or 'resource'}"
    user_id = _require_moodle_user_id()
    async with httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, user_id, target_path)
        if savepath:
            return await save_resource(response, savepath, resourceId=resourceId, kind=kind)
        return await format_resource(response)

@mcp.tool()
async def resolve_proxy(proxyPath: str, savepath: str | None = None):
    """
    Download and parse internal university proxies (PDFs, Images, URLs etc).
    
    Args:
        proxyPath: Path of the proxy page fragment
        savepath: Optional directory path to save the resource instead of parsing it.
    """
    target_path = f"/api/proxy?path={urllib.parse.quote(proxyPath)}"
    user_id = _require_moodle_user_id()
    async with httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, user_id, target_path)
        if savepath:
            return await save_resource(response, savepath, proxyPath=proxyPath)
        return await format_resource(response)

@mcp.tool()
async def get_forum(id: str) -> str:
    """
    Get details of a specific forum, including its description and list of discussion threads.
    
    Args:
        id: The unique forum identifier string.
    """
    user_id = _require_moodle_user_id()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, user_id, f"/api/forum?id={id}")
        data = response.json()
        if not response.is_success:
            return f"Error: {data.get('msg', 'Failed to fetch forum')}"
        return format_forum_details(data.get("forum", {}))

@mcp.tool()
async def get_discussion(id: str) -> str:
    """
    Get details of a specific discussion thread, including its title and list of posts.
    
    Args:
        id: The unique discussion/thread identifier string.
    """
    user_id = _require_moodle_user_id()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(
            client, user_id, f"/api/forum/discussion?id={id}"
        )
        data = response.json()
        if not response.is_success:
            return f"Error: {data.get('msg', 'Failed to fetch discussion')}"
        return format_discussion_details(data.get("discussion", {}))
