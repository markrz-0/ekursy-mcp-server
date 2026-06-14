# eKursy Python MCP Server (`ekursy-mcp-py`)

A Model Context Protocol (MCP) server written in Python using FastMCP, which integrates with the `ekursy-zero` Rust scraper to expose student profile information, course lists, course grades, page contents, and course materials (PDF/images) from the eKursy platform to AI tools.

---

## Prerequisites

Before running the server, ensure you have:
1. **Git** installed on your system.
2. **Docker** installed on your system
3. **Python** installed on your system

---

## Installation & Setup

### Method 1: Automatic Setup Script for Antigravity (Recommended)

> If you dont use antigravity this won't work for you. See manual methods below or ask your AI agent

This repository includes a cross-platform setup script that automatically initializes git submodules, prompts you for credentials to create the `.env` file, and configures the Gemini / Antigravity integration file for you.

- **Windows**: Run `scripts\setup.bat` (Double-click or run in terminal: `.\scripts\setup.bat`)
- **macOS / Linux**: Run `./scripts/setup.sh` (or `bash scripts/setup.sh`)

The script will configure MCP in Antigravity and start the server in docker. You only need to restart Antigravity and this MCP server should work

---

## Alternative/Manual Methods

### 1. Initialize Submodule & Credentials Manually
If you prefer not to use the setup script:
```bash
git submodule update --init --recursive
```
And manually create a `.env` file in the root directory:
```env
MOODLE_USERNAME="your.email@student.put.poznan.pl"
MOODLE_PASSWORD="your_moodle_password"
MCP_TRANSPORT="streamable-http" # optional: defaults to streamable-http when running using docker compose, set to stdio to run locally
```

---

## How to Run

### Option A: Run via Docker Compose
This runs both the `ekursy-zero` scraper backend and `ekursy-mcp-py` server together. The scraper remains private and isolated inside the container network (ports are not exposed to the host).

By default, Docker Compose runs the MCP server in `streamable-http` mode. If you need to configure the transport type, you can set `MCP_TRANSPORT` in your `.env` file (e.g., `MCP_TRANSPORT=stdio` or `MCP_TRANSPORT=streamable-http`).

#### File Downloads & Shared Volumes
When running via Docker Compose, the host's `./downloads` directory is mounted to `/app/downloads` in the container.
- The environment variable `HOST_DOWNLOADS_DIR` is set in `docker-compose.yml` as `${PWD}/downloads`. 
- When an MCP tool calls `save_resource` (e.g. download PDF or images), the file is saved inside this volume. The server uses `HOST_DOWNLOADS_DIR` to report the exact absolute host path back to the MCP caller so you know exactly where to locate the file on your machine.

Run the following command:
```bash
docker compose up --build
```

The MCP server will start on HTTP port `6969` (if using `streamable-http` mode). You can verify it by reaching the MCP endpoint:
`http://localhost:6969/mcp`

### Option B: Run Locally
To run the server locally using the standard `stdio` transport:
```bash
uv run src/main.py
```

*Note: By default, running the script directly uses `stdio` transport. You can force it to run as a local HTTP server by setting the `MCP_TRANSPORT` environment variable: `MCP_TRANSPORT=streamable-http uv run src/main.py` (which runs on port `6969` or the port specified in `PORT`).*

---

## Manual Integration with Antigravity / Gemini MCP

To manually connect this Python MCP server to your Antigravity environment:

1. Locate the configuration file on your system (e.g., `C:\Users\Marcin\.gemini\config\mcp_config.json` or `config.json`).
2. Add a new server entry inside the `mcpServers` object.

### Recommended Config (Docker / Streamable HTTP Server)
Add the following snippet to your configuration block:

```json
{
  "mcpServers": {
    "ekursy-mcp-py": {
      "serverUrl": "http://localhost:6969/mcp"
    }
  }
}
```

*Note: Ensure the `MOODLE_API_BASE` env variable points to the scraper service instance (e.g. `http://localhost:8080` if running `ekursy-zero` locally/standalone).*

### Alternative Config (Local stdio Server)
If you prefer to run the server locally using the standard input/output (`stdio`) transport:

Add the following snippet to your configuration block (make sure to replace `C:\\path\\to\\ekursy-mcp-py` with the absolute path to your cloned repository, and update the environment variables):

```json
{
  "mcpServers": {
    "ekursy-mcp-py-stdio": {
      "command": "uv",
      "args": [
        "run",
        "src/main.py"
      ],
      "cwd": "C:\\path\\to\\ekursy-mcp-py",
      "env": {
        "MOODLE_USERNAME": "your.email@student.put.poznan.pl",
        "MOODLE_PASSWORD": "your_moodle_password",
        "MOODLE_API_BASE": "http://localhost:8080",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

*Note: Ensure the `MOODLE_API_BASE` env variable points to the scraper service instance (e.g., `http://localhost:8080` if running `ekursy-zero` locally/standalone). The `MCP_TRANSPORT` is optional and defaults to `stdio` when running locally.*
