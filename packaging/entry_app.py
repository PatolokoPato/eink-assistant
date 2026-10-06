"""Punto de entrada de EInkAssistant.exe (PyInstaller): el programa de escritorio."""

import sys

from ui.app import main

if __name__ == "__main__":
    sys.exit(main())
