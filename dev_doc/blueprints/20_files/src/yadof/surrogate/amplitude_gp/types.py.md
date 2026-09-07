# Blueprint: surrogate/amplitude_gp/types.py

## Contract

Define the frozen `AmplitudeGPState` container without loading a numerical backend.
Retain generation/sample counts, exact state/content/provenance digests, canonical
mathematical identity, all ordered training row IDs, their exact fitted normalized
inputs and bounded training provenance. Keep the fitted raw model, root convenience manifest, namespace
manifest, unique artifact directory and diagnostic training history. Runtime
constructs this state only after fitting or validated checkpoint recovery.
It is not an optimizer state, posterior sampler, observation or portable pickle.
