"""Expression evaluator for predicate expressions.

Evaluates predicates against photos and their annotations to determine
if a photo matches the selector criteria.

Supports:
- Field paths: photo.date_taken, view.family.decade, tags, etc.
- Comparisons: eq, ne, gt, gte, lt, lte, in, contains, matches, exists, between
- Logical operators: and, or, not

Example usage:
    evaluator = PredicateEvaluator()
    predicate = Predicate(and_=[
        Predicate(**{"view.family.decade": {"in": ["1980s", "1990s"]}}),
        Predicate(**{"view.family.has_children": True}),
    ])
    if evaluator.evaluate(predicate, photo, annotations):
        # photo matches
"""

import re
from datetime import datetime
from typing import Any, Optional, Union

from ptk.db.models import Photo
from ptk.views.schema import Predicate, ComparisonOp


class PredicateEvaluator:
    """Evaluates predicate expressions against photos.

    The evaluator takes a photo and its annotations (from various views)
    and determines if the photo matches a predicate.
    """

    def evaluate(
        self,
        predicate: Predicate,
        photo: Photo,
        annotations: Optional[dict[str, dict[str, Any]]] = None,
    ) -> bool:
        """Evaluate a predicate against a photo.

        Args:
            predicate: The predicate expression to evaluate
            photo: The photo to test
            annotations: Dict of {view_name: {field_name: value}} annotations

        Returns:
            True if the photo matches the predicate
        """
        if annotations is None:
            annotations = {}

        # Handle logical operators
        if predicate.and_ is not None:
            return all(
                self.evaluate(p, photo, annotations)
                for p in predicate.and_
            )

        if predicate.or_ is not None:
            return any(
                self.evaluate(p, photo, annotations)
                for p in predicate.or_
            )

        if predicate.not_ is not None:
            return not self.evaluate(predicate.not_, photo, annotations)

        # Handle field comparisons
        field_comparisons = predicate.get_field_comparisons()
        for field_path, comparison in field_comparisons.items():
            value = self._get_field_value(field_path, photo, annotations)
            if not self._compare(value, comparison):
                return False

        return True

    def _get_field_value(
        self,
        field_path: str,
        photo: Photo,
        annotations: dict[str, dict[str, Any]],
    ) -> Any:
        """Get a field value from a photo or its annotations.

        Field paths:
        - "photo.date_taken" -> photo.date_taken
        - "view.family.decade" -> annotations["family"]["decade"]
        - "tags" -> photo.tags (list of tag names)
        - "albums" -> photo.albums (list of album names)
        - Simple field names default to photo attributes
        """
        parts = field_path.split(".")

        # Handle view annotations: view.<view_name>.<field_name>
        if parts[0] == "view" and len(parts) >= 3:
            view_name = parts[1]
            field_name = ".".join(parts[2:])
            view_data = annotations.get(view_name, {})
            return view_data.get(field_name)

        # Handle photo.* paths
        if parts[0] == "photo" and len(parts) >= 2:
            attr_name = parts[1]
            return self._get_photo_attr(photo, attr_name, parts[2:] if len(parts) > 2 else [])

        # Handle special computed fields
        if field_path == "tags":
            return [t.name for t in photo.tags]
        if field_path == "albums":
            return [a.name for a in photo.albums]
        if field_path == "path":
            return photo.original_path
        if field_path == "filename":
            return photo.filename

        # Try as a direct photo attribute
        if hasattr(photo, field_path):
            return getattr(photo, field_path)

        # Try looking in all views for the field
        for view_name, view_data in annotations.items():
            if field_path in view_data:
                return view_data[field_path]

        return None

    def _get_photo_attr(
        self,
        photo: Photo,
        attr_name: str,
        sub_parts: list[str],
    ) -> Any:
        """Get an attribute from a photo, handling nested access."""
        value = getattr(photo, attr_name, None)

        if value is None:
            return None

        # Handle nested access for special cases
        if sub_parts:
            if attr_name == "date_taken" and isinstance(value, datetime):
                if sub_parts[0] == "year":
                    return value.year
                elif sub_parts[0] == "month":
                    return value.month
                elif sub_parts[0] == "day":
                    return value.day

            if attr_name == "faces" and sub_parts[0] == "count":
                return len(photo.faces) if photo.faces else 0

            if attr_name == "tags" and sub_parts[0] == "count":
                return len(photo.tags) if photo.tags else 0

        return value

    def _compare(self, value: Any, comparison: Any) -> bool:
        """Compare a value against a comparison specification.

        comparison can be:
        - A simple value (equality check)
        - A dict with operators: {eq: v}, {gt: v}, {in: [...]}, etc.
        """
        # Handle None value
        if value is None:
            if isinstance(comparison, dict):
                # Check for exists operator
                if "exists" in comparison:
                    return not comparison["exists"]
                # Most comparisons fail on None
                return False
            # None != any concrete value
            return comparison is None

        # Simple equality
        if not isinstance(comparison, dict):
            return self._equals(value, comparison)

        # Dict of operators
        for op, operand in comparison.items():
            if not self._apply_operator(op, value, operand):
                return False

        return True

    def _equals(self, value: Any, target: Any) -> bool:
        """Check equality with type coercion."""
        if value == target:
            return True

        # String comparison (case insensitive)
        if isinstance(value, str) and isinstance(target, str):
            return value.lower() == target.lower()

        # Boolean comparison
        if isinstance(target, bool):
            if isinstance(value, bool):
                return value == target
            if isinstance(value, str):
                return (value.lower() in ("yes", "true", "1")) == target

        return False

    def _apply_operator(self, op: str, value: Any, operand: Any) -> bool:
        """Apply a comparison operator."""
        if op in ("eq", "equals"):
            return self._equals(value, operand)

        if op in ("ne", "neq", "not_equals"):
            return not self._equals(value, operand)

        if op == "gt":
            return self._compare_numeric(value, operand, lambda a, b: a > b)

        if op == "gte":
            return self._compare_numeric(value, operand, lambda a, b: a >= b)

        if op == "lt":
            return self._compare_numeric(value, operand, lambda a, b: a < b)

        if op == "lte":
            return self._compare_numeric(value, operand, lambda a, b: a <= b)

        if op == "in":
            if isinstance(operand, list):
                # Check if value is in the list
                return any(self._equals(value, item) for item in operand)
            return False

        if op == "contains":
            if isinstance(value, str):
                return operand.lower() in value.lower()
            if isinstance(value, list):
                return any(self._equals(item, operand) for item in value)
            return False

        if op == "matches":
            if isinstance(value, str):
                try:
                    return bool(re.search(operand, value, re.IGNORECASE))
                except re.error:
                    return False
            return False

        if op == "exists":
            return (value is not None) == operand

        if op == "between":
            if isinstance(operand, list) and len(operand) == 2:
                low, high = operand
                return self._compare_numeric(value, low, lambda a, b: a >= b) and \
                       self._compare_numeric(value, high, lambda a, b: a <= b)
            return False

        # Unknown operator
        return False

    def _compare_numeric(
        self,
        value: Any,
        operand: Any,
        comparator,
    ) -> bool:
        """Compare values numerically."""
        try:
            if isinstance(value, datetime) and isinstance(operand, datetime):
                return comparator(value, operand)
            if isinstance(value, (int, float)) and isinstance(operand, (int, float)):
                return comparator(float(value), float(operand))
            if isinstance(value, str) and isinstance(operand, str):
                return comparator(value, operand)
            # Try numeric conversion
            return comparator(float(value), float(operand))
        except (TypeError, ValueError):
            return False


# ============================================================================
# Query Builder for SQL
# ============================================================================

class SQLQueryBuilder:
    """Builds SQL WHERE clauses from predicates.

    For efficient database querying, predicates can be translated to SQL.
    This handles the common cases; complex predicates may require
    post-filtering in Python.
    """

    def __init__(self):
        self.params = {}
        self.param_count = 0

    def build_where(self, predicate: Predicate) -> tuple[str, dict]:
        """Build a SQL WHERE clause from a predicate.

        Returns:
            Tuple of (SQL string, parameters dict)
        """
        self.params = {}
        self.param_count = 0

        sql = self._build_clause(predicate)
        return sql, self.params

    def _build_clause(self, predicate: Predicate) -> str:
        """Build a clause for a predicate."""
        # Logical operators
        if predicate.and_ is not None:
            clauses = [self._build_clause(p) for p in predicate.and_]
            clauses = [c for c in clauses if c]
            if not clauses:
                return ""
            return "(" + " AND ".join(clauses) + ")"

        if predicate.or_ is not None:
            clauses = [self._build_clause(p) for p in predicate.or_]
            clauses = [c for c in clauses if c]
            if not clauses:
                return ""
            return "(" + " OR ".join(clauses) + ")"

        if predicate.not_ is not None:
            clause = self._build_clause(predicate.not_)
            if clause:
                return f"NOT ({clause})"
            return ""

        # Field comparisons
        field_comparisons = predicate.get_field_comparisons()
        clauses = []

        for field_path, comparison in field_comparisons.items():
            clause = self._build_comparison(field_path, comparison)
            if clause:
                clauses.append(clause)

        if not clauses:
            return ""
        return " AND ".join(clauses)

    def _build_comparison(self, field_path: str, comparison: Any) -> str:
        """Build a comparison clause."""
        # Map field paths to SQL columns
        column = self._map_field_to_column(field_path)
        if column is None:
            return ""  # Can't translate to SQL

        # Simple equality
        if not isinstance(comparison, dict):
            param_name = self._add_param(comparison)
            return f"{column} = :{param_name}"

        # Dict of operators
        clauses = []
        for op, operand in comparison.items():
            clause = self._build_operator(column, op, operand)
            if clause:
                clauses.append(clause)

        return " AND ".join(clauses) if clauses else ""

    def _map_field_to_column(self, field_path: str) -> Optional[str]:
        """Map a field path to a SQL column name."""
        # Direct photo fields
        photo_fields = {
            "filename": "photos.filename",
            "caption": "photos.caption",
            "scene": "photos.scene",
            "date_taken": "photos.date_taken",
            "is_favorite": "photos.is_favorite",
            "is_video": "photos.is_video",
            "camera_make": "photos.camera_make",
            "camera_model": "photos.camera_model",
            "latitude": "photos.latitude",
            "longitude": "photos.longitude",
            "photo.filename": "photos.filename",
            "photo.caption": "photos.caption",
            "photo.date_taken": "photos.date_taken",
            "photo.is_favorite": "photos.is_favorite",
        }

        if field_path in photo_fields:
            return photo_fields[field_path]

        # View annotations require a join
        if field_path.startswith("view."):
            # This is complex - return None for now, handle in Python
            return None

        return None

    def _build_operator(self, column: str, op: str, operand: Any) -> str:
        """Build an operator clause."""
        param_name = self._add_param(operand)

        if op in ("eq", "equals"):
            return f"{column} = :{param_name}"
        if op in ("ne", "neq"):
            return f"{column} != :{param_name}"
        if op == "gt":
            return f"{column} > :{param_name}"
        if op == "gte":
            return f"{column} >= :{param_name}"
        if op == "lt":
            return f"{column} < :{param_name}"
        if op == "lte":
            return f"{column} <= :{param_name}"
        if op == "in" and isinstance(operand, list):
            # Need special handling for IN clause
            param_names = []
            for i, item in enumerate(operand):
                pn = self._add_param(item)
                param_names.append(f":{pn}")
            return f"{column} IN ({', '.join(param_names)})"
        if op == "contains":
            self.params[param_name] = f"%{operand}%"
            return f"{column} LIKE :{param_name}"
        if op == "matches":
            # SQLite uses GLOB or LIKE, not REGEX by default
            # Use LIKE with wildcards for basic pattern matching
            return ""  # Complex patterns handled in Python
        if op == "exists":
            if operand:
                return f"{column} IS NOT NULL"
            else:
                return f"{column} IS NULL"

        return ""

    def _add_param(self, value: Any) -> str:
        """Add a parameter and return its name."""
        self.param_count += 1
        param_name = f"p{self.param_count}"
        self.params[param_name] = value
        return param_name
