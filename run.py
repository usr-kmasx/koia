#!/usr/bin/env python3
"""Ponto de entrada do Koia: ``python3 run.py``."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from koia.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
