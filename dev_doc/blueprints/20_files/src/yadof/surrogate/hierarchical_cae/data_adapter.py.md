# File blueprint: src/yadof/surrogate/hierarchical_cae/data_adapter.py

Adapt recorded/session rows into named complete-design training data, deduplicate
designs, freeze schema/scalers, and project reconstructed samples through the
current cost interpreter. It does not own state recovery.
