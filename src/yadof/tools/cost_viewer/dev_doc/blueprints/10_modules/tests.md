# Module Blueprint: Tests

Root pytest coverage verifies frozen snapshot/one-open-segment behavior, frozen task
interpretation, row adaptation, issue isolation, objective-name fallbacks,
average-cost semantics, Pareto/generation/HV calculations, candidate-count CLI
progress with an unknown streaming total and final count, image output,
documentation links, and wheel/sdist inclusion. Tests should target observable
results at the owning module. Exact Matplotlib artists, style constants, pixel
dimensions, label positions, and import-facade identity are deliberately outside
the test contract.
