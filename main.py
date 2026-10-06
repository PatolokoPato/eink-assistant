"""Punto de entrada de E-Ink Assistant.

De momento muestra la pantalla principal (hora, tiempo, PC y calendario);
ver tools/show_home.py para todas las opciones, p. ej. --watch.
La imagen de prueba de la Fase 1 sigue en tools/send_test_image.py.
"""

import sys

from tools.show_home import main

if __name__ == "__main__":
    sys.exit(main())
