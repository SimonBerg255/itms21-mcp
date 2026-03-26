# server.py
"""ITMS21+ MCP Server for Intric — Slovak EU Funds Intelligence Layer."""

import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from mcp.server.fastmcp import Icon
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

load_dotenv()

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

####### AUTH #######
verifier = JWTVerifier(
    public_key=os.getenv("MCP_SERVER_JWT_SECRET"),
    issuer=os.getenv("MCP_SERVER_JWT_ISSUER", ""),
    audience=os.getenv("MCP_SERVER_JWT_AUDIENCE", ""),
    algorithm="HS256",
)


####### IP ALLOWLIST MIDDLEWARE #######
class IPAllowlistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_ips: list[str]):
        super().__init__(app)
        self.allowed_ips = set(allowed_ips)
        self.allow_all = "*" in self.allowed_ips

    async def dispatch(self, request: Request, call_next):
        if self.allow_all:
            return await call_next(request)
        client_ip = request.client.host if request.client else None
        if client_ip not in self.allowed_ips:
            return JSONResponse(
                status_code=403,
                content={"error": "Forbidden", "your_ip": client_ip},
            )
        return await call_next(request)


ALLOWED_IPS = ["*"]  # Restrict in production
middleware = [Middleware(IPAllowlistMiddleware, allowed_ips=ALLOWED_IPS)]


####### SERVER METADATA #######
icon = Icon(src="https://www.eurofondy.gov.sk/favicon.ico")

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


####### MCP SERVER #######
mcp = FastMCP(
    name="ITMS21+ Slovak EU Funds Server",
    instructions=INSTRUCTION_STRING,
    version="1.0.0",
    website_url="https://eurofondy.gov.sk",
    icons=[icon],
    auth=verifier,
)

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


####### ENTRY POINT #######
app = mcp.http_app(middleware=middleware)
