"""Registra el servidor MCP «eink» en Claude Desktop (versión de consola).

Claude Desktop reescribe su configuración al cerrarse, así que este script
espera a que se cierre del todo, añade la entrada y lo vuelve a abrir.

Lánzalo con doble clic en instalar_mcp_claude.cmd (no desde una terminal de
Claude: al cerrar Claude se cerraría también el script) y después cierra
Claude Desktop desde su icono de la bandeja > Quit. En la versión instalada
se hace desde el propio programa (Opciones > Conectar con Claude Desktop).
"""

from __future__ import annotations

import sys
import time

from ui import claude_desktop as cd


def main() -> int:
    print("Instalador del servidor MCP «eink» para Claude Desktop\n")
    if cd.claude_running():
        print("Cierra Claude Desktop del todo: icono de Claude en la bandeja > Quit.")
        print("Esperando a que se cierre... (Ctrl+C para cancelar)")
        while cd.claude_running():
            time.sleep(1)
        time.sleep(2)  # que termine de escribir su configuración

    print(f"  añadido «eink» a {cd.register()}")
    print("\nAbriendo Claude Desktop...")
    cd.reopen_claude()
    print("Listo. En Claude: Ajustes > Desarrollador debería mostrar «eink».")
    print("Recuerda tener abierto E-Ink Assistant (basta en la bandeja).")
    input("\nPulsa Intro para cerrar esta ventana.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
