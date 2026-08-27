# Add modular Pydantic configuration TODO

## Summary

Added a standalone manual TODO for the proposed combination of declarative core
configuration, component-owned typed settings, and Pydantic v2 validation.

The handoff records the current configuration pressure created by algorithm
modularization, preserves the established workspace precedence/provenance/path and
generation-reload contracts, and separates Pydantic's declaration/validation role
from yadof-owned loading, source tracking, workspace resolution, snapshots, and
semantic identity.

## Documentation decision

The new TODO fixes the intended ownership boundary, phased conditional-INR spike,
compatibility policy, verification matrix, costs, non-goals, open decisions, and
completion rule. It also links the active hierarchical-CAE, posterior-calibration,
qNEHVI, and reliable-recording handoffs so implementation does not overwrite their
independent gates or authorize simulator execution.

No current architecture, blueprint, terminology, user contract, source code, test,
dependency, or workspace template changed. Those documents continue to describe
the implemented system; each future implementation gate must update them when its
behavior becomes current.

## Validation

- Read the root development/documentation contracts, every current architecture
  view, every active TODO, and the directly affected project/config/optimize/
  surrogate/package-workspace/test blueprints before authoring the handoff.
- Kept this documentation-only change separate from unrelated in-progress module
  work already present in the shared checkout.
