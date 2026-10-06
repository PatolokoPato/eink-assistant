# PyInstaller: dos ejecutables (programa y servidor MCP) en una sola carpeta,
# compartiendo las librerías. Se usa desde packaging/build_release.ps1:
#   .venv\Scripts\python.exe -m PyInstaller packaging\eink_assistant.spec
# -*- mode: python -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
ICON = str(ROOT / "out" / "build" / "eink-assistant.ico")  # lo genera build_release.ps1

app = Analysis(
    [str(ROOT / "packaging" / "entry_app.py")],
    pathex=[str(ROOT)],
    hiddenimports=["pystray._win32"],
    excludes=["pytest"],
)
mcp = Analysis(
    [str(ROOT / "packaging" / "entry_mcp.py")],
    pathex=[str(ROOT)],
    # mcp.cli es la herramienta de línea de comandos del SDK (necesita typer): no hace falta.
    hiddenimports=collect_submodules("mcp", filter=lambda name: not name.startswith("mcp.cli")),
    excludes=["pytest", "tkinter"],
)

app_exe = EXE(
    PYZ(app.pure), app.scripts, [], exclude_binaries=True,
    name="EInkAssistant", console=False, icon=ICON,
)
mcp_exe = EXE(
    PYZ(mcp.pure), mcp.scripts, [], exclude_binaries=True,
    name="EInkMCP", console=True, icon=ICON,
)

COLLECT(
    app_exe, app.binaries, app.datas,
    mcp_exe, mcp.binaries, mcp.datas,
    name="EInkAssistant",
)
