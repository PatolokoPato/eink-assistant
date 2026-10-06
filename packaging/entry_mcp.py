"""Punto de entrada de EInkMCP.exe (PyInstaller): servidor MCP para Claude Desktop.

Es un ejecutable de consola aparte porque MCP habla por stdin/stdout, que un
ejecutable de ventana no tiene. Claude Desktop lo lanza sin mostrar la consola.
"""

import sys

from mcp_server.eink_mcp import main

if __name__ == "__main__":
    sys.exit(main())
