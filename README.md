# Sample IBM MQ MCP server

MCP (Model Context Protocol) is an open standard that allows LLMs and AI agents to discover and interact with external services such as databases, REST APIs, files, and other resources.
You can read up on the details of MCP [here](https://modelcontextprotocol.io/introduction).

This repo contains a simple MCP server, written in Python, that exposes a subset of the [MQ Administrative REST API](https://www.ibm.com/docs/en/ibm-mq/9.4.x?topic=administering-administration-using-rest-api) as two MCP tools:

- dsqmq: lists any queue managers that are local to the mqweb server, and whether they are running or not
- runmqsc: runs any MQSC command against a specific queue manager. This makes use of the [plain text MQSC API](https://www.ibm.com/docs/en/ibm-mq/9.4.x?topic=adminactionqmgrqmgrnamemqsc-post-plain-text-mqsc-command) 

You can use this MCP server with any LLM which has an MCP client in it, for example [IBM Bob](https://www.ibm.com/products/bob), to allow that LLM to interact with, and potentially configure, your queue managers. 

## Getting the MQ MCP server running

This example was created based on these [instructions](https://modelcontextprotocol.io/quickstart/server). To get the MQ MCP server running, follow these steps:

- The MQ MCP server uses the MQ Administrative REST API. Ensure that you have the mqweb server running as part of a full MQ for distributed installation with one or more queue managers. This doesn't have to be on your local machine
- Ensure that you have installed Python 3.10 or higher
- Install uv and set up your Python project
    - (MacOS/Linux): **curl -LsSf https://astral.sh/uv/install.sh | sh**
    - (Windows): **powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"**
- Restart your terminal
- Clone this repo into a working directory, e.g. **C:\work**
- Change into the mq-mcp-server directory: **cd mq-mcp-server**
- Install dependencies: **uv add "mcp[cli]" httpx**
- Set environment variables for your mqweb credentials (never stored in source code):
    - (MacOS/Linux): **export MQ_USERNAME=mqreader && export MQ_PASSWORD=mqreader**
    - (Windows): **set MQ_USERNAME=mqreader** and **set MQ_PASSWORD=mqreader**
- Open **mqmcpserver.py** in your editor of choice and update the **MQ_SERVERS** list:
    - Add one entry per mqweb server. For a single server this is just the default `https://localhost:9443/ibmmq/rest/v3/admin/`
    - For a **uniform cluster with Native HA**, add one entry per node (e.g. ports 9443–9448 for two QMs with three HA nodes each). The `dspmq` tool queries all servers in parallel; `runmqsc` tries each in turn and skips unreachable ones automatically
    - Bear in mind that if the user is a member of the MQWebAdmin or MQWebUser roles then requests to the MQ MCP server will be able to change your MQ configuration, so you might only want to use these roles in a test environment
- Save your changes
- Start the MQ MCP server by running: **uv run mqmcpserver.py**

By default the MQ MCP server will be listening on http://127.0.0.1:8000/mcp using the streamable HTTP protocol. You can adjust the host name and port number, or use a different protocol using the information provided [here](https://github.com/jlowin/fastmcp#running-your-server).
Some alternatives are included, with comments, in the code.

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

