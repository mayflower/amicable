import sys
from pathlib import Path

# Ensure the repo root is on sys.path so tests can import the local `src/` package.
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

