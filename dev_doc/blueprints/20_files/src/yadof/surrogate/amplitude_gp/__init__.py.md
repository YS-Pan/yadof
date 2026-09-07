# Blueprint: surrogate/amplitude_gp/__init__.py

## Contract

Private package marker for the public factory of the same name. Import this
package before the parent surrogate module rebinds `amplitude_gp` to the factory;
subsequent private imports must not turn that public callable into a module.
Do not import SciPy, scikit-learn, Torch, checkpoints or a workspace at import time.
The settings/component/state modules own the actual public values.
