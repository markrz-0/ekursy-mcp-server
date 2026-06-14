import os
import sys
import json
import io
import urllib.parse
import re
import httpx
from pypdf import PdfReader
from fastmcp import FastMCP
from fastmcp.utilities.types import Image
import mimetypes

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
        elif frag_type == "forum":
            markdown += f"* **Forum**: [{text}](forum?id={frag.get('id')})\n\n"
            
    return markdown.strip()

def clean_html(html_text: str) -> str:
    if not html_text:
        return ""
    text = html_text
    # Replace common block elements with newlines
    text = re.sub(r'</?(?:p|div|br|tr|dd|dt)[^>]*>', '\n', text)
    # Replace links with markdown links
    text = re.sub(r'<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text)
    # Strip all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Unescape common html entities
    text = text.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"').replace("&#039;", "'")
    # Clean up consecutive newlines
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()

def format_forum_details(forum: dict) -> str:
    title = forum.get("title", "Forum")
    description = forum.get("description", "")
    threads = forum.get("threads", [])
    
    output = f"# Forum: {title}\n"
    if description:
        output += f"{description}\n\n"
    else:
        output += "\n"
        
    output += "## Discussion Threads\n"
    if not threads:
        output += "No threads found in this forum.\n"
    for thread in threads:
        output += f"- **{thread.get('title', '')}** (ID: {thread.get('id', '')})\n"
        
    return output.strip()

def format_discussion_details(discussion: dict) -> str:
    title = discussion.get("title", "Discussion")
    posts = discussion.get("posts", [])
    
    output = f"# Discussion: {title}\n\n"
    
    if not posts:
        output += "No posts found in this discussion thread.\n"
        return output.strip()
        
    for post in posts:
        subject = post.get("subject", "No Subject")
        author = post.get("author", "Unknown Author")
        time = post.get("time", "Unknown Time")
        content = clean_html(post.get("content", ""))
        
        output += f"---\n### {subject}\n"
        output += f"**Author**: {author} | **Date**: {time}\n\n"
        output += f"{content}\n\n"
        
    output += "---"
    return output.strip()

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

def determine_filename(response: httpx.Response, resourceId: str | None = None, kind: str | None = None, proxyPath: str | None = None) -> str:
    content_disposition = response.headers.get("content-disposition", "")
    filename = None
    if content_disposition:
        match = re.search(r"filename\*=UTF-8''([^;\n]+)", content_disposition, re.IGNORECASE)
        if match:
            filename = urllib.parse.unquote(match.group(1))
        else:
            match = re.search(r'filename="?([^";\n]+)"?', content_disposition, re.IGNORECASE)
            if match:
                filename = match.group(1)
                
    if filename:
        filename = os.path.basename(filename)
        if filename:
            return filename

    content_type = response.headers.get("content-type", "").lower()
    mime = content_type.split(";")[0].strip()
    extension = mimetypes.guess_extension(mime) or ""
    
    if mime == "application/pdf":
        extension = ".pdf"
    elif mime == "text/html":
        extension = ".html"
        
    if resourceId:
        filename = f"{kind or 'resource'}_{resourceId}{extension}"
    elif proxyPath:
        parsed = urllib.parse.urlparse(proxyPath)
        path_filename = os.path.basename(parsed.path)
        if path_filename:
            name_without_ext, ext = os.path.splitext(path_filename)
            if ext.lower() == ".php" or (extension and ext.lower() != extension.lower() and ext.lower() in [".php", ".html", ""]):
                filename = f"{name_without_ext}{extension}"
            else:
                filename = path_filename
        else:
            sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', proxyPath.strip("/").replace("/", "_"))
            if not sanitized:
                sanitized = "proxy_resource"
            filename = f"{sanitized}{extension}"
    else:
        filename = f"downloaded_resource{extension}"
        
    return filename

async def save_resource(response: httpx.Response, savepath: str, resourceId: str | None = None, kind: str | None = None, proxyPath: str | None = None) -> str:
    if 300 <= response.status_code < 400:
        return f"Resource redirects to: {response.headers.get('location')}"
    if not response.is_success:
        return f"Failed to download material: HTTP {response.status_code}"

    try:
        os.makedirs(savepath, exist_ok=True)
    except Exception as e:
        return f"Failed to create directory '{savepath}': {str(e)}"

    filename = determine_filename(response, resourceId, kind, proxyPath)
    filepath = os.path.join(savepath, filename)
    
    try:
        with open(filepath, "wb") as f:
            f.write(response.content)
        return f"Successfully saved resource to {os.path.abspath(filepath)} ({len(response.content)} bytes)"
    except Exception as e:
        return f"Failed to save resource to {filepath}: {str(e)}"

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
async def resolve_material_link(resourceId: str, kind: str, savepath: str | None = None):
    """
    Download and parse internal university files (PDFs, Images) - resource.
    
    Args:
        resourceId: Unique id of the resource
        kind: Resource type selections (e.g., 'resource', 'assign')
        savepath: Optional directory path to save the resource instead of parsing it.
    """
    target_path = f"/api/resource?id={resourceId}&kind={kind or 'resource'}"
    async with httpx.AsyncClient(follow_redirects=False) as client:
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
    async with httpx.AsyncClient(follow_redirects=False) as client:
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
    async with httpx.AsyncClient() as client:
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
    async with httpx.AsyncClient() as client:
        response = await fetch_with_auth(client, f"/api/forum/discussion?id={id}")
        data = response.json()
        if not response.is_success:
            return f"Error: {data.get('msg', 'Failed to fetch discussion')}"
        return format_discussion_details(data.get("discussion", {}))

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        host = os.environ.get("HOST", "0.0.0.0")
        mcp.run(transport="streamable-http", host=host, port=PORT)
    else:
        mcp.run(transport="stdio")
