from mcp.server.mcpserver import MCPServer
import sys
server = MCPServer('zauq-test-echo')
@server.tool()
def echo(value: str) -> str:
    return value
if __name__ == '__main__':
    if len(sys.argv)>1:
        server.run(transport='streamable-http',host='127.0.0.1',port=int(sys.argv[1]))
    else:
        server.run(transport='stdio')
