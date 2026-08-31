# File blueprint: backend/pca_svd_checkpoints.py

## Intent

Provide the read-only deterministic viewer boundary for explicit PCA/SVD
checkpoints without changing checkpoint, evidence, or current task state.

## Contract

Discovery accepts only current manifests below a declared `pca-svd` strategy
namespace, verifies parameter identity, namespace/artifact containment, and artifact
SHA-256, and reports exactly one member. Loading rebuilds the exact named rawData
template from manifest selectors plus the current recorded template, validates
schema/runtime/state signatures, and loads the no-pickle ridge/basis artifact.

Prediction validates normalized parameters, reconstructs complete rawData, and
recalculates current workspace costs. Plot output is a stored-grid deterministic
slice; it does not claim INR-style off-grid decoding. Audit batches predictions,
reduces absolute/relative errors per rawData item, cooperates with cancellation,
and retains no predicted history.
