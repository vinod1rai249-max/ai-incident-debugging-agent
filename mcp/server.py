from mcp.server.fastmcp import FastMCP

mcp = FastMCP("local-mcp")


@mcp.tool()
def hello(name: str) -> str:
    return f"Hello {name}, MCP is working!"


if __name__ == "__main__":
    mcp.run()
