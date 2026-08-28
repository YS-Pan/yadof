# File blueprint: src/yadof/_component_settings.py

## Intent

- Share only stable standard-library primitive validation across component
  factories without recreating a central component schema.

## Functionalities

- Strictly validate Python bool, int, finite real, and non-empty text values.
- Include the public factory, field, rejected value, and constraint in every error.

## Invariants

- No component field registry, Pydantic, optional backend, coercive string parsing,
  or unrestricted mapping input belongs here.
- Component-specific defaults and cross-field rules stay with their owning module.
