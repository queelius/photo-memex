"""View system for ptk - materialized computations over photos.

A View represents:
- A definition (YAML spec of what to compute)
- A materialization (stored annotations per photo)
- Metadata (provenance, status, timestamps)

Multiple views can coexist on the same photos without interference.
Each view is a "layer" of annotations that can be queried independently
or composed together.
"""

from ptk.views.models import View, ViewAnnotation, ViewStatus, create_annotation
from ptk.views.schema import (
    FieldDef,
    FieldType,
    ProfileDef,
    SelectorDef,
    ViewDef,
    PtkDefinitions,
)
from ptk.views.loader import (
    DefinitionLoader,
    get_loader,
    load_definitions,
)
from ptk.views.evaluator import (
    PredicateEvaluator,
    SQLQueryBuilder,
)
from ptk.views.manager import ViewManager

__all__ = [
    # Models
    "View",
    "ViewAnnotation",
    "ViewStatus",
    "create_annotation",
    # Schema
    "FieldDef",
    "FieldType",
    "ProfileDef",
    "SelectorDef",
    "ViewDef",
    "PtkDefinitions",
    # Loader
    "DefinitionLoader",
    "get_loader",
    "load_definitions",
    # Evaluator
    "PredicateEvaluator",
    "SQLQueryBuilder",
    # Manager
    "ViewManager",
]
