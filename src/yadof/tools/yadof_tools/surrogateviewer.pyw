"""Double-click to inspect surrogate checkpoints."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    entry = Path(__file__).resolve()
    launch = runpy.run_path(str(entry.parent / "_shared/launcher.py"))["launch"]
    raise SystemExit(launch(entry, "surrogateviewer"))
