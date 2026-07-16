# ili2django

`ili2django` generates Django model code from INTERLIS IMD files using `ili2py` as the parser and semantic backbone.

## Scope of this initial version

- Reads IMD through `ili2py`
- Generates Django model modules (one app-like package per INTERLIS model)
- Annotates generated classes and fields with decorators carrying INTERLIS metadata
- Provides a runtime bridge for XTF import/export with a tested subset:
  - Scalar fields (strings, numbers, booleans, dates/times)
  - Foreign-key style references via INTERLIS `REF`
  - Dynamic schema generation from `@interlis_model` and `ili_field` metadata
  - Translation-label extraction from secondary IMD files (lookup usage)

Geometry and other unsupported field types are currently skipped by the runtime bridge.

## Install

```bash
pip install -e .
```

## Generate Django models

```bash
ili2django generate-models \
  -i /path/to/model.imd \
  -o ./generated \
  -l interface \
  -a ilidata
```

## Runtime bridge idea

Generated code can be paired with the runtime bridge:

```python
from ili2django.runtime import Ili2PyBridge

bridge = Ili2PyBridge()
model_data = bridge.read_imd("/path/to/model.imd")
```

The runtime bridge can already be used for practical XTF import/export in constrained domains.

## Long-term upstream strategy

The preferred long-term solution is a shared core in `ili2py` and thin framework adapters
in downstream packages like `ili2django`.

### Why this direction

- Avoids duplicated XTF schema logic across projects
- Keeps INTERLIS semantics in one place
- Allows reuse by Django, non-Django ETL, and CLI tooling
- Reduces divergence risk when model coverage grows (geometry, enumerations, baskets, etc.)

### Proposed phases

1. Stabilize the abstraction boundary in `ili2django`
  - Keep framework-agnostic schema construction and field mapping isolated from ORM adapters.
  - Expand tests around round-trip behavior, references, nullability, and basket partitioning.

2. Extract a shared core module upstream in `ili2py`
  - Move pure XTF dataclass schema builders and scalar/ref mapping helpers.
  - Keep no Django dependency in upstream core.

3. Rebind `ili2django` to upstream core
  - Replace local schema internals with the upstream API.
  - Keep only router/queryset adapters and Django-specific model discovery locally.

4. Grow feature coverage in shared core
  - Geometry handling
  - Enum handling and value trees
  - Model/topic-level constraints and richer validation hooks

5. Versioning and compatibility
  - Pin to stable `ili2py` core API versions.
  - Maintain fixture-based cross-repo compatibility tests.

### Contribution model

- Open an upstream design issue first (scope, API boundary, invariants, non-goals).
- Contribute in small PRs:
  1) core interfaces,
  2) schema builder extraction,
  3) adapter migration,
  4) feature increments.
- Keep backward-compatible adapter shims in `ili2django` during transition.
