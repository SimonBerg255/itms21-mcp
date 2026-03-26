# generate_token.py
"""Generate a JWT token for connecting this server to Intric."""

import os
import time

import jwt
from dotenv import load_dotenv

load_dotenv()

secret = os.getenv("MCP_SERVER_JWT_SECRET")
issuer = os.getenv("MCP_SERVER_JWT_ISSUER", "itms21-mcp")
audience = os.getenv("MCP_SERVER_JWT_AUDIENCE", "intric")

if not secret:
    print("Error: MCP_SERVER_JWT_SECRET not set in .env")
    print("Copy .env.example to .env and configure it first.")
    exit(1)

payload = {
    "sub": "itms21-user",
    "iss": issuer,
    "aud": audience,
    "iat": int(time.time()),
    "exp": int(time.time()) + 365 * 24 * 3600,  # 1 year
}

token = jwt.encode(payload, secret, algorithm="HS256")

print("\n=== JWT Token for Intric ===")
print(token)
print("\nServer URL for Intric: http://YOUR_SERVER_IP:8000/sse")
print("Paste this token into the Intric MCP server configuration.\n")
