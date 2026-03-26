# server.py
"""ITMS21+ MCP Server for Intric — Slovak EU Funds Intelligence Layer.

Deployment: Railway + Intric AI
- No authentication (Intric handles auth)
- All tools have requires_permission: False
- Binds to $PORT via uvicorn CLI
"""

import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse, FileResponse

from tools_itms import (
    search_open_calls,
    get_call_detail,
    search_planned_calls,
    search_approved_applications,
    get_application_detail,
    search_projects,
    get_project_detail,
    get_programme_structure,
)


####### SERVER METADATA #######

INSTRUCTION_STRING = """You are connected to the ITMS21+ Open Data API — Slovakia's official
information system for managing EU Structural and Investment Funds for the
2021-2027 programming period.

You can help applicants (municipalities, NGOs, businesses) with:
- Finding open calls (výzvy) relevant to their needs
- Understanding eligibility conditions and requirements
- Exploring upcoming planned calls to prepare in advance
- Finding approved reference applications to learn from
- Understanding what funded projects committed to

Key tools and when to use them:
- search_open_calls: first step when someone asks "what funding is available"
- get_call_detail: get full requirements once you know which call is relevant
- search_planned_calls: help applicants prepare for future opportunities
- search_approved_applications: find real examples of successful applications
- get_application_detail: read the actual text of approved applications
- search_projects: find what has been funded in a region or sector
- get_project_detail: understand a project's activities and indicators
- get_programme_structure: understand the EU policy context

All data is official Slovak government open data from the Ministry of
Investment, Regional Development and Informatisation of the Slovak Republic.
Source: eurofondy.gov.sk / itms21.sk"""


####### MCP SERVER — NO AUTH #######
mcp = FastMCP(
    name="ITMS21+ Slovak EU Funds Server",
    instructions=INSTRUCTION_STRING,
    version="1.0.0",
    website_url="https://eurofondy.gov.sk",
)

# Register all tools with automatic execution (no user confirmation)
mcp.tool(meta={"requires_permission": False})(search_open_calls)
mcp.tool(meta={"requires_permission": False})(get_call_detail)
mcp.tool(meta={"requires_permission": False})(search_planned_calls)
mcp.tool(meta={"requires_permission": False})(search_approved_applications)
mcp.tool(meta={"requires_permission": False})(get_application_detail)
mcp.tool(meta={"requires_permission": False})(search_projects)
mcp.tool(meta={"requires_permission": False})(get_project_detail)
mcp.tool(meta={"requires_permission": False})(get_programme_structure)


####### HEALTH CHECK #######
@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


####### ICON ROUTE #######
@mcp.custom_route("/icon.png", methods=["GET"])
async def serve_icon(request: Request) -> FileResponse:
    return FileResponse("icon.png", media_type="image/png")


####### ENTRY POINT — NO MIDDLEWARE #######
app = mcp.http_app()
