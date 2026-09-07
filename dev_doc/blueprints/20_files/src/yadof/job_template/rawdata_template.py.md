# File blueprint: src/yadof/job_template/rawdata_template.py

## Intent

- Give submit-side derived rawData a stable identity and exact schema boundary
  without depending on optional surrogate/model code.

## Functionalities

- Resolve each field as `(direct .npz basename including .npz, values/data main
  key)` through the existing rawData contract, independent of optional metadata or
  mapping traversal order.
- Freeze canonical fields, main shape/dtype representation, axes, units, metadata,
  and every other non-main template value into a deterministic signature.
- Reconstruct complete structured samples from an exact selector-keyed set of main
  arrays, and validate already structured samples against the same template.
- Reject missing/extra selectors, wrong main shape/dtype, nonnumeric/object main
  arrays, and axis/unit/metadata/template drift.

## I/O Format

- `RawDataSchemaTemplate.from_items()` consumes a mapping of direct `.npz`
  basenames to in-memory payloads or named items.
- `reconstruct()` consumes `{(basename, main_key): ndarray}` and returns a
  `StructuredRawDataSample` whose complete payload sequence can be passed to
  current cost code.

## Non-Obvious Techniques

- Canonical ordering and signature exclude main values but include their exact
  shape/dtype plus digests of every non-main array; metadata is compared by parsed
  JSON meaning rather than source whitespace.
- Public construction isolates mutable inputs in immutable byte-backed arrays;
  read-only views of mutable backing storage are still copied. Already owned
  arrays are shared, and `as_mapping()` explicitly exports mutable copies.
- Schema validation returns an already validated sample directly for the same
  template. Otherwise it checks exact descriptors and replaces all non-main
  values with canonical template objects. Samples hold their template alive;
  samples and templates support weak references without a global strong registry.
- Reconstruction copies only new main arrays; static axes and nested metadata
  remain shared. Hashing consumes contiguous buffers directly.

## Mutability Profile

- Extend selectors/schema only through an explicit protocol revision. Do not add
  padding, field-name guesses, optional-metadata identity, or task-specific layout
  rules here.
