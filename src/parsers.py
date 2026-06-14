import os
import re
import io
import urllib.parse
import mimetypes
import httpx
from pypdf import PdfReader
from fastmcp.utilities.types import Image

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

    is_docker = os.environ.get("RUNNING_IN_DOCKER") == "true"
    if is_docker:
        savepath = "/app/downloads"

    try:
        os.makedirs(savepath, exist_ok=True)
    except Exception as e:
        return f"Failed to create directory '{savepath}': {str(e)}"

    filename = determine_filename(response, resourceId, kind, proxyPath)
    filepath = os.path.join(savepath, filename)
    
    try:
        with open(filepath, "wb") as f:
            f.write(response.content)
        if is_docker:
            host_downloads_dir = os.environ.get("HOST_DOWNLOADS_DIR")
            if host_downloads_dir:
                host_filepath = os.path.join(host_downloads_dir, filename)
                if ":" in host_filepath:
                    host_filepath = host_filepath.replace("/", "\\")
                return f"Successfully saved resource to host machine at: {host_filepath} ({len(response.content)} bytes)"
            return f"Successfully saved resource to './downloads/{filename}' on the host machine ({len(response.content)} bytes)"
        return f"Successfully saved resource to {os.path.abspath(filepath)} ({len(response.content)} bytes)"
    except Exception as e:
        return f"Failed to save resource to {filepath}: {str(e)}"
