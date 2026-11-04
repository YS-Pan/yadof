"""Double-clickable administrator entry point (separate from the yadof wheel)."""
from admin_tool.cluster_config.app import main

if __name__ == "__main__":
    raise SystemExit(main())
