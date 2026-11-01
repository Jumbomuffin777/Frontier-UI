#!/bin/bash
# Rebuild intelligent_ui.py from its parts: Python helpers (p1, p2), then the HTML/CSS/JS template (p3-p5).
set -e
cd "$(dirname "$0")"
cat p1.py p2.py p3.py p4.py p4b.py p5.py > ../intelligent_ui.py
python3 -m py_compile ../intelligent_ui.py && echo "built ../intelligent_ui.py"
