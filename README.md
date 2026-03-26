# ITMS21+ MCP Server — Slovak EU Funds Intelligence Layer

A production-ready MCP (Model Context Protocol) server that exposes the Slovak government's ITMS21+ Open Data API as structured tools for AI assistants running inside [Intric](https://www.intric.ai). ITMS21+ is the official Slovak information system for managing EU Structural Funds for the 2021-2027 programming period. All data is official, open, and requires no authentication.

## Prerequisites

- Python 3.11+
- Network access to `api.itms21.sk`

## Setup

```bash
# Clone / copy this directory
cd itms21-mcp

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Generate .env with a random secret
python3 -c "import secrets; print('MCP_SERVER_JWT_SECRET=' + secrets.token_hex(32))" > .env
echo "MCP_SERVER_JWT_ISSUER=itms21-mcp" >> .env
echo "MCP_SERVER_JWT_AUDIENCE=intric" >> .env

# Verify all tools work
python3 test_tools.py
```

## Running the Server

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

The server will be available at `http://localhost:8000/mcp`.
Health check: `http://localhost:8000/health`

## Connecting to Intric

1. Generate a JWT token: `python3 generate_token.py`
2. In Intric, go to **Admin → MCP Servers → Add Server**
3. **Server URL:** `http://YOUR_SERVER_IP:8000/sse`
4. **API Key:** paste the generated JWT token
5. Save and test the connection
6. All 8 tools will appear automatically in your Intric assistant

**Tip:** Use ngrok to expose an HTTPS URL: `ngrok http 8000`

## Available Tools

| Tool | Description |
|------|-------------|
| `search_open_calls` | Find currently open EU funding calls (výzvy) |
| `get_call_detail` | Get full detail of a specific call including conditions and indicators |
| `search_planned_calls` | Find upcoming calls not yet open for preparation |
| `search_approved_applications` | Find approved grant applications as reference examples |
| `get_application_detail` | Read the full text of an approved application (descriptions, budget, indicators) |
| `search_projects` | Find funded projects currently in realisation |
| `get_project_detail` | Get full project detail with activities, indicators, and budget |
| `get_programme_structure` | Get the EU programme hierarchy (Programme → Priorities → Specific Objectives) |

## Project Structure

```
itms21-mcp/
├── server.py           # FastMCP server — Intric boilerplate + tool registration
├── tools_itms.py       # All 8 ITMS21+ tool implementations
├── itms_client.py      # HTTP client for api.itms21.sk
├── test_tools.py       # Verification runner — must exit 0
├── generate_token.py   # JWT token generator for Intric
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
└── README.md           # This file
```

## API Documentation

- ITMS21+ API: https://api.itms21.sk/public/v1/
- Official docs: https://eurofondy.gov.sk/dokumenty-a-publikacie/metodicke-dokumenty/dokumenty-itms21/
