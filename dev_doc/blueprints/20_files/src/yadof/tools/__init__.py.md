# File blueprint: src/yadof/tools/__init__.py

## Intent

- Define the small public namespace for optional, workspace-aware user tools while
  keeping those tools outside the optimization and evaluation runtime graph.

## Functionalities

- Re-export adapter discovery/copying and confirmed history clearing.
- Re-export their immutable result and confirmation-error types.
- Keep visualization and software-specific tools in explicit submodules so their
  heavier or optional dependencies are not imported with `yadof.tools`.

## I/O Format

- The module itself performs no I/O. Its `__all__` is the supported convenience
  import surface for the re-exported APIs.

## Non-Obvious Techniques

- The deliberately narrow export list prevents importing plotting libraries,
  PyAEDT, or simulator-specific code merely to use a lightweight task tool.

## Mutability Profile

- Add a re-export only for a stable, generally useful tool API. Keep CLI-only,
  plotting-heavy, and software-specific entry points in their owning modules.
