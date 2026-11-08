# File blueprint: src/yadof/tools/user_tools/aedt_parameters/__init__.py

## Intent

- Expose the supported HFSS task-tool API without leaking internal parser helpers.

## Functionalities

- Re-export `extract_parameters`, its immutable result type, and the explicit
  confirmation error from `parameter_extraction`.
- Re-export `read_aedt_parameters`, `export_aedt_parameters`, and their immutable
  `OptParam` preview values for project-based, text-only export.

## I/O Format

- The module performs no I/O; `__all__` defines the public HFSS tool surface used
  by CLI routing and Python callers.

## Non-Obvious Techniques

- PyAEDT remains an optional fallback dependency because
  `parameter_extraction.py` imports it only inside the fallback opener.

## Mutability Profile

- Export only stable, user-invokable HFSS tools and their result values. Parsing
  helpers and desktop UI imports stay in their owning modules.
