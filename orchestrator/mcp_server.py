import asyncio
import json
from mcp.server import Server
from mcp.transport.stdio import stdio_transport
from mcp.types import Tool, TextContent


def create_server(bulk_retrieve):
    server = Server("gabesearch-mcp")

    @server.call_tool()
    async def search_and_retrieve(name: str, arguments: dict):
        if name != "search_and_retrieve":
            raise ValueError(f"Unknown tool: {name}")
        prompt = arguments.get("prompt", "")
        result = await bulk_retrieve(prompt)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="search_and_retrieve",
                description="Bulk search and retrieve content with citation metadata. Accepts JSON with 'queries' array or structured text format.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "JSON object with queries array, or structured text with QUERIES: and CLAIM: sections",
                        }
                    },
                    "required": ["prompt"],
                },
            )
        ]

    return server


async def run_server(server: Server):
    async with stdio_transport() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)
