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
```

---

## How to Run

### Option A: Run via Docker Compose
This runs both the `ekursy-zero` scraper backend and `ekursy-mcp-py` server together. The scraper remains private and isolated inside the container network (ports are not exposed to the host).

Run the following command:
```bash
docker compose up --build
```

The MCP server will start on HTTP port `6969`. You can verify it by reaching the MCP endpoint:
`http://localhost:6969/mcp`

### Option B: Run Locally
To run the server locally (using stdio transport, which is standard for MCP desktop clients):
```bash
uv run src/main.py
```

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
