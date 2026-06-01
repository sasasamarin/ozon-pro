"""Pytest config: добавляем backend/ в sys.path, чтобы можно было импортировать
app.services.* без полноценной установки пакета.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
