# File blueprint: src/yadof/surrogate/conditional_inr/settings.py

## Intent

- Own the one private immutable conditional-INR mathematical, training, sampling,
  and device settings snapshot.

## Functionalities

- Define and validate the authoritative defaults used by the public conditional-INR
  factories and the internal modeling artifact config.
- Produce the stable JSON-safe semantic payload consumed by strategy identity.

## Invariants

- No Torch/NumPy import, ambient config lookup, public `settings=` entrance, or
  mutable nested reference.
- Core random seed and maximum training lag are passed separately and never copied
  into this snapshot.
