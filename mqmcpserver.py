#
# Copyright (c) 2025 IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncio
import httpx
import json
import os
import ssl
import sys

from mcp.server.mcpserver import MCPServer

# Initialize MCPServer
mcp = MCPServer("mqmcpserver")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Credentials are read from environment variables so that passwords are never
# stored in source code. Set these before starting the server:
#
#   export MQ_USERNAME=mqreader
#   export MQ_PASSWORD=mqreader
#
# To connect to multiple mqweb servers (e.g. a uniform cluster with Native HA),
# add one entry per server to MQ_SERVERS below.
# Example for a two-QM cluster with 3 HA nodes each:
#   {"url": "https://mqhost1:9443/ibmmq/rest/v3/admin/"},
#   {"url": "https://mqhost2:9443/ibmmq/rest/v3/admin/"},
#
# Per-server credentials can be added by including "username"/"password" keys
# in a specific entry — they override the environment variables for that entry.

MQ_USERNAME = os.environ.get("MQ_USERNAME", "mqreader")
MQ_PASSWORD = os.environ.get("MQ_PASSWORD", "mqreader")

# TLS verification. Internal MQ often uses a self-signed cert — point MQ_CA_BUNDLE at that
# cert or your internal CA (PEM) to validate against it instead of trusting blindly.
# Unset = no verification (zero-config demo default; MITM-vulnerable, do not use in prod).
MQ_CA_BUNDLE = os.environ.get("MQ_CA_BUNDLE")
MQ_VERIFY = ssl.create_default_context(cafile=MQ_CA_BUNDLE) if MQ_CA_BUNDLE else False

# MQ_SERVERS = [
#     {"url": "https://localhost:9443/ibmmq/rest/v3/admin/"},
# ]
MQ_SERVERS = [
    {"url": "https://localhost:9443/ibmmq/rest/v3/admin/"},
    {"url": "https://localhost:9444/ibmmq/rest/v3/admin/"},
    {"url": "https://localhost:9445/ibmmq/rest/v3/admin/"},
    {"url": "https://localhost:9446/ibmmq/rest/v3/admin/"},
    {"url": "https://localhost:9447/ibmmq/rest/v3/admin/"},
    {"url": "https://localhost:9448/ibmmq/rest/v3/admin/"},
]
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _dspmq_one(client: httpx.AsyncClient, server: dict, auth: httpx.BasicAuth) -> str:
    """Query a single mqweb server for its queue managers."""
    headers = {
        "Content-Type": "application/json",
        "ibm-mq-rest-csrf-token": "token",
    }
    url = server["url"] + "qmgr/"
    try:
        response = await client.get(url, headers=headers, auth=auth, timeout=30.0)
        response.raise_for_status()
        return prettify_dspmq(response.content, server["url"])
    except Exception as err:
        print(err, file=sys.stderr)
        return f"[{server['url']}] Error: {err}\n---\n"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def dspmq() -> str:
    """List available queue managers and whether they are running or not.
    Queries all configured MQ servers.
    """
    tasks = []
    async with httpx.AsyncClient(verify=MQ_VERIFY) as client:
        for server in MQ_SERVERS:
            username = server.get("username", MQ_USERNAME)
            password = server.get("password", MQ_PASSWORD)
            auth = httpx.BasicAuth(username=username, password=password)
            tasks.append(_dspmq_one(client, server, auth))
        results = await asyncio.gather(*tasks)
    return "".join(results)


@mcp.tool()
async def runmqsc(qmgr_name: str, mqsc_command: str) -> str:
    """Run an MQSC command against a specific queue manager.
    Tries each configured MQ server in turn until one succeeds.

    Args:
        qmgr_name: A queue manager name
        mqsc_command: An MQSC command to run on the queue manager
    """
    timeout = httpx.Timeout(timeout=30.0, connect=3.0)
    for server in MQ_SERVERS:
        username = server.get("username", MQ_USERNAME)
        password = server.get("password", MQ_PASSWORD)
        auth = httpx.BasicAuth(username=username, password=password)
        async with httpx.AsyncClient(verify=MQ_VERIFY, auth=auth, timeout=timeout) as client:
            headers = {
                "Content-Type": "application/json",
                "ibm-mq-rest-csrf-token": "a",
            }
            data = json.dumps({"type": "runCommand", "parameters": {"command": mqsc_command}})
            url = server["url"] + "action/qmgr/" + qmgr_name + "/mqsc"
            try:
                response = await client.post(url, data=data, headers=headers)
                response.raise_for_status()
                return prettify_runmqsc(response.content)
            except httpx.HTTPStatusError as err:
                # 404 means this server doesn't host the qmgr — try the next one
                if err.response.status_code == 404:
                    continue
                print(err, file=sys.stderr)
                return f"Error from {server['url']}: {err}\n"
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # Server unreachable — try the next one silently
                continue
            except Exception as err:
                print(err, file=sys.stderr)
                return f"Error from {server['url']}: {err}\n"
    return f"Queue manager '{qmgr_name}' not found on any configured MQ server."


# ---------------------------------------------------------------------------
# Pretty-printers
# ---------------------------------------------------------------------------

# Put the output for each queue manager on its own line, separated by ---
def prettify_dspmq(payload: bytes, server_url: str) -> str:
    jsonOutput = json.loads(payload.decode("utf-8"))
    prettifiedOutput = f"\n=== {server_url} ===\n---\n"
    for x in jsonOutput['qmgr']:
        prettifiedOutput += "name = " + x['name'] + ", running = " + x['state'] + "\n---\n"
    return prettifiedOutput


# Put the output of each MQSC command on its own line, separated by ---
# Deals with both z/OS and distributed queue managers
def prettify_runmqsc(payload: bytes) -> str:
    jsonOutput = json.loads(payload.decode("utf-8"))
    # A command-level error (e.g. bad MQSC) returns HTTP 200 with no commandResponse.
    responses = jsonOutput.get('commandResponse')
    if not responses:
        reason = jsonOutput.get('overallReasonCode', 'unknown')
        errs = "; ".join(jsonOutput.get('error', [])) or "no command response"
        return f"\n---\n{errs} (overallReasonCode = {reason})\n---\n"
    prettifiedOutput = "\n---\n"
    for x in responses:
        # z/OS
        if x['text'][0].startswith("CSQN205I"):
            # Remove leading and trailing messages, as they aren't needed.
            x['text'].pop(0)
            x['text'].pop()
            for y in x['text']:
                prettifiedOutput += y[15:] + "\n---\n"
        # Distributed
        else:
            prettifiedOutput += x['text'][0] + "\n---\n"
    return prettifiedOutput


if __name__ == "__main__":
    # Initialize and run the server on http://127.0.0.1:8000/mcp
    mcp.run(transport='streamable-http')
    # If using IBM Bob then use one of these
    #mcp.run(transport='stdio')
    # URL is http://127.0.0.1:8000/sse
    #mcp.run(transport='sse')
