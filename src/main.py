import os
import sys
import json
import io
import urllib.parse
import httpx
from pypdf import PdfReader
from fastmcp import FastMCP
from fastmcp.utilities.types import Image

# Environment Configuration
USERNAME = os.environ.get("MOODLE_USERNAME")
PASSWORD = os.environ.get("MOODLE_PASSWORD")
PORT = int(os.environ.get('PORT', '6969'))
API_BASE_URL = os.environ.get("MOODLE_API_BASE", "http://moodle-api:8080")

if not USERNAME or not PASSWORD:
    print("CRITICAL ERROR: MOODLE_USERNAME and MOODLE_PASSWORD are required.", file=sys.stderr)
    sys.exit(1)

# In-Memory Session State
active_session_key: str | None = None

# Initialize FastMCP Server
mcp = FastMCP("ekursy-mcp-server")

# 1. Authentication Engine
async def login_to_moodle(client: httpx.AsyncClient) -> str:
    global active_session_key
    response = await client.post(
        f"{API_BASE_URL}/api/login",
        json={"email": USERNAME, "password": PASSWORD}
    )

    if not response.is_success:
        try:
            err_data = response.json()
            error_code = err_data.get("error", "AUTH_ERR")
            msg = err_data.get("msg", "Unknown authentication error")
        except Exception:
            error_code = "AUTH_ERR"
            msg = "Unknown authentication error"
        raise Exception(f"[{error_code}] {msg}")

    data = response.json()
    active_session_key = data.get("moodleSessionKey")
    return active_session_key

# 2. Authenticated Fetch Helper (Handles 401 Auto-Recovery)
async def fetch_with_auth(client: httpx.AsyncClient, endpoint: str, **kwargs) -> httpx.Response:
    global active_session_key
    if not active_session_key:
        await login_to_moodle(client)

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = active_session_key

    # Manual request helper
    async def make_request():
        return await client.get(f"{API_BASE_URL}{endpoint}", headers=headers, **kwargs)

    response = await make_request()

    # Desync Recovery: Re-login and retry once if the session expired
    if response.status_code == 401:
        await login_to_moodle(client)
        headers["Authorization"] = active_session_key
        response = await make_request()

    return response

# 3. Parser Helpers
def parse_page_fragments(fragments: list) -> str:
    markdown = ""
    for frag in fragments:
        frag_type = frag.get("type")
        text = frag.get("text", "")
        
        if frag_type == "text":
            markdown += f"{text}\n\n"
        elif frag_type == "caption":
            markdown += f"### {text}\n\n"
        elif frag_type == "link":
            markdown += f"[{text}]({frag.get('link')})\n\n"
        elif frag_type == "proxy":
            markdown += f"[Proxy Resource: {text}](proxy:{frag.get('link')})\n\n"
        elif frag_type == "iframe":
            markdown += f"\nEmbedded Frame: {frag.get('src', '')}\n\n\n"
        elif frag_type == "resource":
            kind = frag.get('kind', 'unknown')
            markdown += f"* **Attachment** ({kind}): [{text}](resource?id={frag.get('id')}&kind={kind})\n\n"
            
    return markdown.strip()

def format_grades_hierarchy(nodes: list, indent: str = "") -> str:
    output = ""
    for node in nodes:
        icon = "📁" if node.get("is_category") else "📄"
        output += f"{indent}- {icon} **{node.get('name', '')}**\n"
        
        grade = node.get("grade")
        if grade and grade != "-":
            percentage = node.get("percentage")
            perc_str = f" ({percentage})" if percentage and percentage != "-" else ""
            output += f"{indent}  - Grade: {grade}{perc_str}\n"
            
        weight = node.get("weight")
        if weight and weight != "-":
            output += f"{indent}  - Weight: {weight}\n"
            
        feedback = node.get("feedback")
        if feedback and feedback != "-":
            output += f"{indent}  - Feedback: {feedback}\n"
            
        children = node.get("children", [])
        if children:
            output += format_grades_hierarchy(children, indent + "  ")
            
    return output

async def format_resource(response: httpx.Response):
    if 300 <= response.status_code < 400:
        return f"Resource redirects to: {response.headers.get('location')}"
    if not response.is_success:
        return "Failed to download material"

    content_type = response.headers.get("content-type", "unknown").lower()
    content_bytes = response.content

    if "application/pdf" in content_type:
        try:
            reader = PdfReader(io.BytesIO(content_bytes))
            text = "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
            return text
        except Exception as err:
            return f"PDF Parse Failed: {str(err)}"

    if content_type.startswith("image/"):
        # FastMCP handles images directly via the Image object
        img_format = content_type.split("/")[-1].split(";")[0] # e.g., 'png' or 'jpeg'
        return Image(data=content_bytes, format=img_format)

    if any(fmt in content_type for fmt in ["json", "text", "markdown"]):
        return content_bytes.decode("utf-8", errors="ignore")

    return f"Successfully resolved binary ({content_type})."

# 4. MCP Tools Registration

@mcp.tool()
async def get_user_profile() -> str:
    """Fetch the authenticated student's profile information and USOS number."""
    async with httpx.AsyncClient() as client:
        response = await fetch_with_auth(client, "/api/me")
        if response.is_success:
            return json.dumps(response.json(), indent=2)
        return f"Error: {response.json().get('msg')}"

@mcp.tool()
async def list_courses() -> str:
    """Get a list of all courses the student is enrolled in."""
    async with httpx.AsyncClient() as client:
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
    async with httpx.AsyncClient() as client:
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
    async with httpx.AsyncClient() as client:
        response = await fetch_with_auth(client, f"/api/course_grades?id={id}")
        data = response.json()
        
        if not response.is_success:
            return f"Error: {data.get('msg', 'Failed to fetch grades')}"

        formatted_grades = format_grades_hierarchy(data.get("result", []))
        return formatted_grades if formatted_grades else "No grades found for this course."

@mcp.tool()
async def resolve_material_link(resourceId: str, kind: str):
    """
    Download and parse internal university files (PDFs, Images) - resource.
    
    Args:
        resourceId: Unique id of the resource
        kind: Resource type selections (e.g., 'resource', 'assign')
    """
    target_path = f"/api/resource?id={resourceId}&kind={kind or 'resource'}"
    async with httpx.AsyncClient(follow_redirects=False) as client:
        response = await fetch_with_auth(client, target_path)
        return await format_resource(response)

@mcp.tool()
async def resolve_proxy(proxyPath: str):
    """
    Download and parse internal university proxies (PDFs, Images, URLs etc).
    
    Args:
        proxyPath: Path of the proxy page fragment
    """
    target_path = f"/api/proxy?path={urllib.parse.quote(proxyPath)}"
    async with httpx.AsyncClient(follow_redirects=False) as client:
        response = await fetch_with_auth(client, target_path)
        return await format_resource(response)

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        host = os.environ.get("HOST", "0.0.0.0")
        mcp.run(transport="streamable-http", host=host, port=PORT)
    else:
        mcp.run(transport="stdio")
