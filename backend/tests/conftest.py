# ─── Shared pytest fixtures & path setup ────────────────────
# Make the backend importable as `import main` / `import auth`
# regardless of the directory pytest is invoked from.
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
