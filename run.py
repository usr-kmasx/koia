#!/usr/bin/env python3
"""Ponto de entrada do Koia: ``python3 run.py``.

``python3 run.py --tray`` sobe o daemon da bandeja (GTK3): ícone,
menu e slideshow dos wallpapers baixados — independente da janela.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# teto de mmap ANTES de qualquer import do app: os blocos grandes de
# decode precisam nascer fora dos arenas do glibc (ver o módulo)
from koia.malloc_tune import instalar  # noqa: E402

instalar()

if "--tray" in sys.argv[1:]:
    from koia.tray import main as tray_main
    sys.exit(tray_main())

from koia.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
