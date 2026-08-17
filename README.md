# Sample IBM MQ MCP server

MCP (Model Context Protocol) is an open standard that allows LLMs and AI agents to discover and interact with external services such as databases, REST APIs, files, and other resources.
You can read up on the details of MCP [here](https://modelcontextprotocol.io/introduction).

This repo contains a simple MCP server, written in Python, that exposes a subset of the [MQ Administrative REST API](https://www.ibm.com/docs/en/ibm-mq/9.4.x?topic=administering-administration-using-rest-api) as two MCP tools:

- dsqmq: lists any queue managers that are local to the mqweb server, and whether they are running or not
- runmqsc: runs any MQSC command against a specific queue manager. This makes use of the [plain text MQSC API](https://www.ibm.com/docs/en/ibm-mq/9.4.x?topic=adminactionqmgrqmgrnamemqsc-post-plain-text-mqsc-command) 

You can use this MCP server with any LLM which has an MCP client in it, for example [IBM Bob](https://www.ibm.com/products/bob), to allow that LLM to interact with, and potentially configure, your queue managers. 

## Prerequisites

Before running the MQ MCP server, ensure you have the following:

| Prerequisite | Details |
|---|---|
| **IBM MQ** | A full IBM MQ for distributed installation with one or more queue managers running. The mqweb server (`strmqweb`) must be started. This does not have to be on your local machine. |
| **mqweb user** | A user configured in the mqweb server with at least the `MQWebUser` role (read-only) or `MQWebAdmin` role (read-write). Note: `MQWebAdmin` allows full MQ configuration changes — use with care in production. |
| **Python 3.10+** | Install from [python.org](https://www.python.org/downloads/) or via your OS package manager. |
| **uv** | Python package manager used to run the server. |

Install `uv`:
- (macOS/Linux): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- (Windows): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

## Getting the MQ MCP server running

This example was created based on these [instructions](https://modelcontextprotocol.io/quickstart/server). To get the MQ MCP server running, follow these steps:

1. **Restart your terminal** after installing `uv` to ensure it is on your PATH.

2. **Clone this repo** into a working directory:
   ```bash
   git clone https://github.com/ibm-messaging/mq-mcp-server.git
   cd mq-mcp-server
   ```

3. **Install dependencies:**
   ```bash
   uv sync
   ```

4. **Set credentials** via environment variables (passwords are never stored in source code):
   - macOS/Linux:
     ```bash
     export MQ_USERNAME=mqreader
     export MQ_PASSWORD=mqreader
     ```
   - Windows:
     ```cmd
     set MQ_USERNAME=mqreader
     set MQ_PASSWORD=mqreader
     ```

5. **Configure mqweb servers** — open `mqmcpserver.py` and update the `MQ_SERVERS` list:
   - **Single server:** just update the default URL to point to your mqweb host:
     ```python
     MQ_SERVERS = [
         {"url": "https://mqhost:9443/ibmmq/rest/v3/admin/"},
     ]
     ```
   - **Uniform cluster with Native HA:** add one entry per node. The `dspmq` tool queries all servers in parallel; `runmqsc` automatically skips unreachable nodes and tries the next one:
     ```python
     MQ_SERVERS = [
         {"url": "https://mqnode01:9443/ibmmq/rest/v3/admin/"},
         {"url": "https://mqnode02:9443/ibmmq/rest/v3/admin/"},
         {"url": "https://mqnode03:9443/ibmmq/rest/v3/admin/"},
         {"url": "https://mqnode04:9443/ibmmq/rest/v3/admin/"},
         {"url": "https://mqnode05:9443/ibmmq/rest/v3/admin/"},
         {"url": "https://mqnode06:9443/ibmmq/rest/v3/admin/"},
     ]
     ```
   - Per-server credentials can be added by including `"username"` and `"password"` keys in an entry — they override the environment variables for that entry only.

6. **Start the MQ MCP server:**
   ```bash
   uv run mqmcpserver.py
   ```

By default the MQ MCP server listens on `http://127.0.0.1:8000/mcp` using the streamable HTTP protocol.
Transport alternatives (SSE, stdio) are described in the [Transport options](#transport-options) section below.

## Connecting the MCP server to an LLM

Follow the instructions provided by your LLM for connecting to your new MCP server. For example you could connect to it using [IBM Bob](https://www.ibm.com/products/bob) or [IBM Watsonx Orchestrate](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=servers-importing-tools-from-mcp-server).
Alternatively, a [wide range](https://modelcontextprotocol.io/clients) of other LLMs support MCP.

### Connecting with IBM Bob

1. Start the MQ MCP server (see above). It will listen on `http://127.0.0.1:8000/mcp` by default.

2. Create a `.bob/mcp.json` file in your project root (or edit it via **Bob Settings → MCP → Edit Project MCP**):

```json
{
  "mcpServers": {
    "mqmcpserver": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

3. Bob will automatically discover the `dspmq` and `runmqsc` tools. You can then ask Bob natural-language questions about your MQ environment, for example:
   - *"List my queue managers"*
   - *"Show all queues on QM1"*
   - *"Check the Native HA status of QM1"*
   - *"Check the uniform cluster balance — how many app connections are on each queue manager?"*

### Transport options

The server supports three transports. Edit the `mcp.run()` call at the bottom of `mqmcpserver.py` to switch:

| Transport | `mcp.run()` call | URL | Notes |
|---|---|---|---|
| Streamable HTTP (default) | `mcp.run(transport='streamable-http')` | `http://127.0.0.1:8000/mcp` | Recommended for IBM Bob and modern clients |
| SSE | `mcp.run(transport='sse')` | `http://127.0.0.1:8000/sse` | For clients that speak Server-Sent Events |
| stdio | `mcp.run(transport='stdio')` | n/a | Client spawns the process directly |

For **stdio** transport, use this `mcp.json` instead (the MCP client starts the Python process itself):

```json
{
  "mcpServers": {
    "mqmcpserver": {
      "type": "stdio",
      "command": "/absolute/path/to/mq-mcp-server/.venv/bin/python",
      "args": ["/absolute/path/to/mq-mcp-server/mqmcpserver.py"],
      "env": {
        "MQ_USERNAME": "mqreader",
        "MQ_PASSWORD": "mqreader"
      }
    }
  }
}
```

