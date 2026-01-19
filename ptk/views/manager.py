"""View manager - orchestrates view creation, computation, and querying.

The ViewManager is the central coordinator for the view system:
- Creates views from definitions
- Executes view computations (annotates photos using profiles)
- Queries annotations across views
- Tracks view status and statistics

Example usage:
    manager = ViewManager(session)

    # Create a view from a definition
    view = manager.create_view(view_def)

    # Run the view (compute annotations)
    manager.run_view("family_v1", ollama_service)

    # Query annotations
    photos = manager.query_photos(selector)
    annotations = manager.get_annotations("family_v1", photo_id)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Iterator, Callable

from sqlalchemy.orm import Session

from ptk.db.models import Photo
from ptk.views.models import View, ViewAnnotation, ViewStatus, create_annotation
from ptk.views.schema import ViewDef, ProfileDef, Predicate
from ptk.views.loader import DefinitionLoader, get_loader
from ptk.views.evaluator import PredicateEvaluator


class ViewManager:
    """Manages views and annotations.

    Provides high-level operations for:
    - Creating and updating views
    - Running view computations
    - Querying photos by annotations
    - Managing view lifecycle
    """

    def __init__(self, session: Session, loader: Optional[DefinitionLoader] = None):
        """Initialize the view manager.

        Args:
            session: SQLAlchemy session
            loader: Definition loader (uses default if not provided)
        """
        self.session = session
        self.loader = loader or get_loader()
        self.evaluator = PredicateEvaluator()

    # ========================================================================
    # View CRUD
    # ========================================================================

    def create_view(
        self,
        view_def: ViewDef,
        *,
        force: bool = False,
    ) -> View:
        """Create a new view from a definition.

        Args:
            view_def: The view definition
            force: If True, overwrite existing view with same name

        Returns:
            The created View record

        Raises:
            ValueError: If view already exists and force=False
        """
        # Check for existing
        existing = self.get_view(view_def.name)
        if existing:
            if not force:
                raise ValueError(f"View '{view_def.name}' already exists. Use force=True to overwrite.")
            self.delete_view(view_def.name)

        # Get the profile
        profile = self.loader.get_profile(view_def.profile)
        if not profile:
            raise ValueError(f"Unknown profile: {view_def.profile}")

        now = datetime.now(timezone.utc)

        view = View(
            name=view_def.name,
            version=view_def.version,
            description=view_def.description,
            definition_yaml=self._serialize_view_def(view_def),
            profile_name=view_def.profile,
            selector_yaml=self._serialize_predicate(view_def.selector) if view_def.selector else None,
            model=view_def.compute.model,
            model_host=view_def.compute.host,
            status=ViewStatus.DRAFT.value,
            photo_count=0,
            annotation_count=0,
            created_at=now,
            updated_at=now,
        )

        self.session.add(view)
        self.session.commit()

        return view

    def get_view(self, name: str) -> Optional[View]:
        """Get a view by name."""
        return self.session.query(View).filter(View.name == name).first()

    def list_views(self) -> list[View]:
        """List all views."""
        return self.session.query(View).order_by(View.created_at.desc()).all()

    def delete_view(self, name: str) -> bool:
        """Delete a view and its annotations.

        Returns:
            True if view was deleted, False if not found
        """
        view = self.get_view(name)
        if not view:
            return False

        # Annotations are cascade-deleted via relationship
        self.session.delete(view)
        self.session.commit()
        return True

    def update_view_status(
        self,
        name: str,
        status: ViewStatus,
        error_message: Optional[str] = None,
    ) -> None:
        """Update a view's status."""
        view = self.get_view(name)
        if view:
            view.status = status.value
            view.error_message = error_message
            view.updated_at = datetime.now(timezone.utc)
            if status == ViewStatus.COMPLETE:
                view.computed_at = datetime.now(timezone.utc)
            self.session.commit()

    # ========================================================================
    # View Execution
    # ========================================================================

    def run_view(
        self,
        view_name: str,
        annotator: Any,  # OllamaVisionService or similar
        *,
        batch_size: int = 10,
        skip_existing: bool = True,
        limit: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict[str, int]:
        """Run a view computation (annotate photos).

        Args:
            view_name: Name of the view to run
            annotator: The annotation service (e.g., OllamaVisionService)
            batch_size: Number of photos to process before committing
            skip_existing: Skip photos that already have annotations
            limit: Maximum number of photos to process (None = all)
            progress_callback: Called with (current, total, photo_filename)

        Returns:
            Dict with statistics: {success, errors, skipped}
        """
        view = self.get_view(view_name)
        if not view:
            raise ValueError(f"View not found: {view_name}")

        # Get the profile
        profile_def = self.loader.get_profile(view.profile_name)
        if not profile_def:
            raise ValueError(f"Profile not found: {view.profile_name}")

        # Get view definition for selector
        view_def = self._deserialize_view_def(view.definition_yaml)

        # Select photos
        photos = self._select_photos(view_def.selector)
        if limit:
            photos = photos[:limit]
        total = len(photos)

        if progress_callback:
            progress_callback(0, total, "Starting...")

        self.update_view_status(view_name, ViewStatus.COMPUTING)

        stats = {"success": 0, "errors": 0, "skipped": 0}

        try:
            for i, photo in enumerate(photos):
                if progress_callback:
                    progress_callback(i, total, photo.filename)

                # Skip if already annotated
                if skip_existing and self._has_annotations(view_name, photo.id):
                    stats["skipped"] += 1
                    continue

                # Check photo exists
                if not Path(photo.original_path).exists():
                    stats["errors"] += 1
                    continue

                try:
                    # Run annotation
                    self._annotate_photo(
                        view_name=view_name,
                        photo=photo,
                        profile=profile_def,
                        annotator=annotator,
                    )
                    stats["success"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    # Continue processing other photos

                # Commit periodically
                if (i + 1) % batch_size == 0:
                    self.session.commit()

            # Final commit
            self.session.commit()

            # Update view stats
            self._update_view_stats(view_name)
            self.update_view_status(view_name, ViewStatus.COMPLETE)

        except Exception as e:
            self.session.rollback()
            self.update_view_status(view_name, ViewStatus.ERROR, str(e))
            raise

        return stats

    def _annotate_photo(
        self,
        view_name: str,
        photo: Photo,
        profile: ProfileDef,
        annotator: Any,
    ) -> None:
        """Annotate a single photo with a profile."""
        image_path = Path(photo.original_path)

        for field in profile.fields:
            try:
                # Build prompt and get response
                prompt = field.build_prompt()
                response = annotator._generate(prompt, image_path)

                # Parse response
                from ptk.views.schema import FieldType
                value = self._parse_field_response(response, field)

                # Store annotation
                annotation = create_annotation(
                    photo_id=photo.id,
                    view_name=view_name,
                    field_name=field.name,
                    field_type=field.type.value,
                    value=value,
                    raw_response=response.strip(),
                )
                self.session.add(annotation)

            except Exception as e:
                # Store error or default value
                if field.default is not None:
                    annotation = create_annotation(
                        photo_id=photo.id,
                        view_name=view_name,
                        field_name=field.name,
                        field_type=field.type.value,
                        value=field.default,
                        raw_response=f"Error: {e}",
                    )
                    self.session.add(annotation)

    def _parse_field_response(self, response: str, field) -> Any:
        """Parse an LLM response according to field type."""
        import re
        from ptk.views.schema import FieldType

        response = response.strip()

        if field.type == FieldType.INTEGER:
            match = re.search(r'-?\d+', response)
            return int(match.group()) if match else field.default

        elif field.type == FieldType.FLOAT:
            match = re.search(r'-?\d+\.?\d*', response)
            return float(match.group()) if match else field.default

        elif field.type == FieldType.BOOLEAN:
            lower = response.lower()
            if any(x in lower for x in ['yes', 'true', 'correct', 'affirmative']):
                return True
            elif any(x in lower for x in ['no', 'false', 'negative']):
                return False
            return field.default

        elif field.type == FieldType.ENUM:
            lower = response.lower()
            for opt in (field.options or []):
                if opt.lower() in lower:
                    return opt
            return field.default

        elif field.type == FieldType.LIST:
            items = []
            for item in response.split(','):
                item = item.strip().lower()
                item = re.sub(r'^[\d\.\-\*\•]+\s*', '', item)
                item = re.sub(r'[^\w\s\-]', '', item)
                if item and len(item) > 1:
                    items.append(item)
            return items if items else field.default

        else:  # STRING or TEXT
            return response if response else field.default

    def _select_photos(self, selector: Optional[Predicate]) -> list[Photo]:
        """Select photos matching a selector."""
        query = self.session.query(Photo).filter(Photo.is_video == False)

        if selector is None:
            return query.all()

        # For complex selectors, we fetch all and filter in Python
        # In the future, we could optimize with SQL for simple cases
        all_photos = query.all()

        # Get all annotations for filtering
        annotations = self._load_all_annotations()

        return [
            photo for photo in all_photos
            if self.evaluator.evaluate(selector, photo, annotations.get(photo.id, {}))
        ]

    def _load_all_annotations(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Load all annotations indexed by photo_id -> view_name -> field_name -> value."""
        result = {}
        all_annotations = self.session.query(ViewAnnotation).all()

        for ann in all_annotations:
            if ann.photo_id not in result:
                result[ann.photo_id] = {}
            if ann.view_name not in result[ann.photo_id]:
                result[ann.photo_id][ann.view_name] = {}
            result[ann.photo_id][ann.view_name][ann.field_name] = ann.value

        return result

    def _has_annotations(self, view_name: str, photo_id: str) -> bool:
        """Check if a photo has any annotations for a view."""
        count = self.session.query(ViewAnnotation).filter(
            ViewAnnotation.view_name == view_name,
            ViewAnnotation.photo_id == photo_id,
        ).count()
        return count > 0

    def _update_view_stats(self, view_name: str) -> None:
        """Update view statistics."""
        view = self.get_view(view_name)
        if not view:
            return

        # Count unique photos and total annotations
        photo_count = self.session.query(ViewAnnotation.photo_id).filter(
            ViewAnnotation.view_name == view_name
        ).distinct().count()

        annotation_count = self.session.query(ViewAnnotation).filter(
            ViewAnnotation.view_name == view_name
        ).count()

        view.photo_count = photo_count
        view.annotation_count = annotation_count
        view.updated_at = datetime.now(timezone.utc)

    # ========================================================================
    # Querying
    # ========================================================================

    def get_annotations(
        self,
        view_name: str,
        photo_id: str,
    ) -> dict[str, Any]:
        """Get all annotations for a photo in a view.

        Returns:
            Dict of {field_name: value}
        """
        annotations = self.session.query(ViewAnnotation).filter(
            ViewAnnotation.view_name == view_name,
            ViewAnnotation.photo_id == photo_id,
        ).all()

        return {ann.field_name: ann.value for ann in annotations}

    def get_all_annotations(
        self,
        photo_id: str,
    ) -> dict[str, dict[str, Any]]:
        """Get all annotations for a photo across all views.

        Returns:
            Dict of {view_name: {field_name: value}}
        """
        annotations = self.session.query(ViewAnnotation).filter(
            ViewAnnotation.photo_id == photo_id,
        ).all()

        result = {}
        for ann in annotations:
            if ann.view_name not in result:
                result[ann.view_name] = {}
            result[ann.view_name][ann.field_name] = ann.value

        return result

    def query_photos(
        self,
        selector: Predicate,
        limit: Optional[int] = None,
    ) -> list[Photo]:
        """Query photos matching a selector.

        This evaluates the selector against all photos and their annotations.

        Args:
            selector: The predicate to match
            limit: Maximum number of results

        Returns:
            List of matching photos
        """
        # Load all photos and annotations
        photos = self.session.query(Photo).filter(Photo.is_video == False).all()
        annotations = self._load_all_annotations()

        # Filter
        matching = [
            photo for photo in photos
            if self.evaluator.evaluate(selector, photo, annotations.get(photo.id, {}))
        ]

        if limit:
            matching = matching[:limit]

        return matching

    def search_by_view_field(
        self,
        view_name: str,
        field_name: str,
        value: Any,
        *,
        operator: str = "eq",
        limit: Optional[int] = None,
    ) -> list[Photo]:
        """Search photos by a specific view field value.

        This is an optimized query path for simple field lookups.

        Args:
            view_name: Name of the view
            field_name: Name of the field
            value: Value to match
            operator: Comparison operator (eq, ne, gt, lt, in, contains)
            limit: Maximum results

        Returns:
            List of matching photos
        """
        query = self.session.query(Photo).join(
            ViewAnnotation,
            Photo.id == ViewAnnotation.photo_id
        ).filter(
            ViewAnnotation.view_name == view_name,
            ViewAnnotation.field_name == field_name,
        )

        # Apply operator
        if operator == "eq":
            query = query.filter(ViewAnnotation.value_json == json.dumps(value))
        elif operator == "contains":
            # For JSON arrays, use LIKE
            query = query.filter(ViewAnnotation.value_json.contains(json.dumps(value)))
        # For other operators, we'd need to cast the JSON value
        # which is database-specific. Fall back to Python filtering.

        if limit:
            query = query.limit(limit)

        return query.all()

    # ========================================================================
    # Serialization
    # ========================================================================

    def _serialize_view_def(self, view_def: ViewDef) -> str:
        """Serialize a ViewDef to YAML string."""
        import yaml
        data = view_def.model_dump(exclude_none=True)
        return yaml.dump(data, default_flow_style=False)

    def _deserialize_view_def(self, yaml_str: str) -> ViewDef:
        """Deserialize a ViewDef from YAML string."""
        import yaml
        data = yaml.safe_load(yaml_str)

        # Handle nested objects
        if 'selector' in data and data['selector']:
            data['selector'] = Predicate(**data['selector'])
        if 'compute' in data:
            from ptk.views.schema import ComputeSettings
            data['compute'] = ComputeSettings(**data['compute'])
        if 'policy' in data:
            from ptk.views.schema import UpdatePolicy
            data['policy'] = UpdatePolicy(**data['policy'])

        return ViewDef(**data)

    def _serialize_predicate(self, predicate: Predicate) -> str:
        """Serialize a predicate to YAML."""
        import yaml
        return yaml.dump(predicate.model_dump(exclude_none=True), default_flow_style=False)
