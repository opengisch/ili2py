# Upstream XTF Core Plan (ili2py + ili2django)

## Goal

Build a long-term integration where INTERLIS/XTF semantics live in a shared `ili2py` core,
while `ili2django` remains a thin framework adapter for model discovery and persistence.

## Current State

- `ili2django` already contains working runtime import/export for a tested subset.
- Runtime logic includes:
  - dynamic xsdata schema generation from `@interlis_model` / `ili_field` metadata
  - import upsert flow with deferred reference resolution
  - export basket assembly and transfer serialization
  - IMD translation lookup merge from secondary IMDs
- Coverage is intentionally partial (geometry and some advanced types are skipped).

## Option Review

### 1) Copy existing code to ili2django

- Short-term speed: high
- Long-term maintainability: medium/low
- Upstream reuse: low
- Risk: duplicated semantics drift across projects

### 2) Reuse existing dataclass package code directly

- Short-term speed: medium
- Long-term maintainability: medium
- Upstream reuse: medium
- Risk: older/intermediate XTF reader/generator paths are not aligned with current Django runtime shape

### 3) Shared core extraction (recommended)

- Short-term speed: medium
- Long-term maintainability: high
- Upstream reuse: high
- Risk: requires careful API boundary and staged migration

## Recommended Architecture

### Shared upstream module in `ili2py`

Proposed module path (example):

- `ili2py.runtime.xtf_core`

Responsibilities:

- Build transfer schema from neutral model metadata
- Parse transfer XML into neutral record structures
- Serialize neutral record structures to transfer XML
- Provide scalar type mapping and reference encoding helpers

Must not depend on:

- Django ORM
- framework-specific routing/persistence APIs

### Downstream adapter in `ili2django`

Responsibilities:

- Discover models and field metadata from Django classes
- Convert ORM objects to neutral record payloads
- Persist imported neutral records via router/upsert logic
- Keep Django-specific extension points

## Proposed Core Interfaces

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class CoreField:
    py_name: str
    xml_name: str
    kind: str  # "scalar" | "ref"
    python_type: type[Any]
    related_type: str | None = None

@dataclass(frozen=True)
class CoreModel:
    model_key: str
    model_name: str
    topic_name: str
    class_name: str
    fields: list[CoreField]

@dataclass(frozen=True)
class CoreSchema:
    transfer_type: type[Any]
    datasection_type: type[Any]

class XtfCore:
    def build_schema(self, models: list[CoreModel]) -> CoreSchema: ...
    def parse_transfer(self, xtf_path: str, schema: CoreSchema) -> Any: ...
    def render_transfer(self, transfer_obj: Any) -> str: ...
```

`ili2django` adapter would map Django models/fields into `CoreModel` and map parsed records back.

## Migration Phases

### Phase 0: Baseline and invariants

- Freeze current behavior with tests in `ili2django`:
  - round-trip scalar/ref subset
  - stable topic/basket naming
  - translation merge semantics

### Phase 1: Extract pure helpers locally

- In `ili2django`, separate framework-agnostic schema builder from ORM adapters.
- Keep behavior unchanged.

### Phase 2: Upstream API PR

- Open design issue in `ili2py` with minimal API proposal.
- Contribute core schema builder and parser/serializer wrapper.

### Phase 3: Adapter rebinding

- Replace local schema internals in `ili2django` with upstream core calls.
- Preserve public `Ili2PyBridge` API.

### Phase 4: Feature growth

- Geometry support
- Enum value/tree support
- richer constraint hooks

## Acceptance Criteria

- No behavior regression in existing `ili2django` runtime tests.
- Added cross-repo fixture tests for at least one real-world model.
- No Django imports in upstream core module.
- `ili2django` runtime owns only adapter logic and translation/read-imd orchestration.

## PR Breakdown Suggestion

1. `ili2django`: test hardening + local internal split
2. `ili2py`: introduce `xtf_core` skeleton + schema build for scalar/ref subset
3. `ili2django`: consume upstream core behind compatibility shim
4. `ili2py`: geometry/enum increments
5. `ili2django`: remove deprecated local shim

## Notes

- Keep transition shims for at least one minor release of `ili2django`.
- Prefer explicit semantic version pinning between packages during migration.
