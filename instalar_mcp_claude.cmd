@echo off
rem Registra el servidor MCP "eink" en Claude Desktop (ver tools\install_claude_mcp.py).
rem Doble clic aqui y despues cierra Claude Desktop desde su icono de la bandeja > Quit.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m tools.install_claude_mcp
