import json
import httpx
import urllib.parse
from config import TIMEOUT
from server import mcp
from auth import fetch_with_auth
from parsers import (
    parse_page_fragments,
    format_grades_hierarchy,
    save_resource,
    format_resource,
    format_forum_details,
    format_discussion_details
)

# 4. MCP Tools Registration

@mcp.tool()
async def get_user_profile() -> str:
    """Fetch the authenticated student's profile information and USOS number."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, "/api/me")
        if response.is_success:
            return json.dumps(response.json(), indent=2)
        return f"Error: {response.json().get('msg')}"

@mcp.tool()
async def list_courses() -> str:
    """Get a list of all courses the student is enrolled in."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, "/api/course_list")
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
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, f"/api/course?id={id}")
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
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, f"/api/course_grades?id={id}")
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
    async with httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, target_path)
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
    async with httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, target_path)
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
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, f"/api/forum?id={id}")
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
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await fetch_with_auth(client, f"/api/forum/discussion?id={id}")
        data = response.json()
        if not response.is_success:
            return f"Error: {data.get('msg', 'Failed to fetch discussion')}"
        return format_discussion_details(data.get("discussion", {}))
