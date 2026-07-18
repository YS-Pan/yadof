"""Allow ``python -m yadof`` to use the installed console interface."""

from .cli import main

raise SystemExit(main())
