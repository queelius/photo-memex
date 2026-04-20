# Face Recognition Design

> Detect faces in photos, compute embeddings, and support a "tag one face, propagate via confirm-per-match" workflow via MCP.

**Status:** design
**Author:** Alex Towell (via Claude Opus 4.7)
**Date:** 2026-04-19

## Goal

Enable the LLM/user to identify people across the photo library with minimal manual work. The hero workflow is:

1. The library is scanned once to detect face regions and store per-face embeddings.
2. The user manually tags one face as a named person via the existing `tag_person` MCP tool.
3. The LLM calls `propose_person_matches("Alice")` to get the most-similar unnamed faces, reviews thumbnails, and confirms the correct ones via `confirm_person_match`.
4. Each confirmation adds an anchor for that person, so subsequent proposals compare against the full set of confirmed faces. This implicitly handles age progression.

## Non-goals (v1)

- **Cluster discovery** (find groups of similar unnamed faces before anyone has been tagged). Deferred.
- **Face quality scoring** (skip blurry/small/occluded faces). Deferred.
- **Automatic tagging** (apply `person_id` without human confirmation). Rejected: the library spans 14 years with kids growing up, false positives are guaranteed, and propose/confirm is the safe default.
- **Deduplication of manual-placeholder Faces** (where a real detection now covers a prior `tag_person` placeholder). Deferred.

## Constraints

- **Scale:** ~1,135 photos, expected ~3,000 faces. Brute-force cosine similarity over 3,000 128-dim vectors is <10 ms, so no vector index is needed.
- **License:** `face_recognition` wraps dlib (BSD-style). OK to ship as an optional extra.
- **Core stays MIT:** face recognition is a `[faces]` optional extra, not a required dependency. `pip install photo-memex` without extras must still work.
- **No model downloads at install time.** `face_recognition` ships its required dlib models in the wheel. Verify before committing.

## Architecture

### Module layout

```
ptk/faces/
├── __init__.py
├── detector.py    # face_recognition wrapper: photo path → list[(bbox, embedding)]
├── matcher.py     # cosine similarity, top-N candidates
└── service.py     # orchestration: detect-batch, propose-matches, confirm
```

### Schema change

Add one nullable column to `Face` in `ptk/db/models.py`:

```python
embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
```

128 × float32 = 512 bytes per face. Stored as `numpy.ndarray.tobytes()`; read back via `numpy.frombuffer(..., dtype=np.float32)`.

The model handles two Face shapes:
- **Detected faces:** `confidence > 0`, real `bbox`, `embedding` set, `person_id` initially `NULL`.
- **Manual-placeholder faces** (from existing `tag_person`): `confidence = 0.0`, `bbox = (0, 0, 1, 1)`, `embedding = NULL`, `person_id` set. These seed a person in the embedding space only once a detected face with the same `person_id` is confirmed.

No migration system exists; the column is added via `Base.metadata.create_all()` on next init. Existing databases need a manual `ALTER TABLE faces ADD COLUMN embedding BLOB` for v1, documented in the release notes.

### Detection

`ptk/faces/detector.py`:

```python
def detect_faces(image_path: Path) -> list[FaceDetection]:
    """Return all faces in the image as (bbox, embedding) tuples."""
```

Where `FaceDetection` is a dataclass:
```python
@dataclass
class FaceDetection:
    bbox: tuple[float, float, float, float]  # normalized (x, y, w, h) in 0..1
    embedding: np.ndarray                    # shape (128,), dtype float32
    confidence: float                        # face_recognition doesn't return one; use 1.0
```

The detector normalizes dlib's pixel-coordinate bbox into 0..1 bounds for schema consistency with `tag_person`.

### Detection service

`ptk/faces/service.py`:

```python
def detect_all(session: Session, *, force: bool = False) -> DetectRunStats:
    """Detect faces in every non-archived photo that hasn't been processed yet.

    Idempotent by default: photos with at least one Face row where confidence > 0
    are skipped. Pass force=True to re-detect.
    """

def detect_photo(session: Session, photo_id: str) -> list[Face]:
    """Detect faces in a single photo, replacing any prior detections."""
```

The "has been processed" signal is the presence of at least one `Face` row with `confidence > 0` for that photo, so a photo that genuinely has zero faces will be re-scanned on every run. Acceptable for v1 (this affects a minority of photos and re-scanning is cheap). Can be optimized later with a `faces_detected_at` column on Photo.

### Matcher

`ptk/faces/matcher.py`:

```python
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two 128-dim embeddings."""

def propose_matches(
    session: Session,
    person_name: str,
    *,
    limit: int = 20,
) -> list[MatchProposal]:
    """Rank untagged faces by max similarity to any face already tagged as person_name.

    "Tagged as person_name" means Face rows where person.name == person_name AND
    embedding IS NOT NULL. This excludes manual-placeholder faces that have no
    embedding (they act as labels only until a detected face is confirmed).

    Returns up to `limit` faces with person_id IS NULL, sorted by descending
    similarity. Returns empty list if no anchors exist yet.
    """
```

Where `MatchProposal` is:
```python
@dataclass
class MatchProposal:
    face_id: int
    photo_id: str
    similarity: float           # 0..1, higher is more similar
    bbox: tuple[float, float, float, float]
```

No fixed threshold. The caller decides what's plausible based on visual review.

### MCP tools

Three new tools in `ptk/mcp/server.py`:

```python
def propose_person_matches(
    self, person_name: str, limit: int = 20
) -> list[dict]:
    """Return top-N untagged detected faces ranked by similarity to confirmed
    faces for person_name. Each entry has face_id, photo_id, similarity, bbox.
    Returns [] if person has no confirmed detected faces yet.
    """

def get_face_thumbnail(self, face_id: int) -> list:
    """Return [Image, metadata_json] cropped to the face's bbox.
    Image is the photo thumbnail cropped to bbox. Lets the LLM see just the
    face without the surrounding photo. Metadata includes photo_id, person_id
    (if tagged), and similarity if this face was part of a recent proposal.
    """

def confirm_person_match(self, face_id: int, person_name: str) -> dict:
    """Assign person_id = <person_name> to the given face. Creates the Person
    if new (resurrects if archived, per the existing _get_or_resurrect pattern).
    This face now acts as an additional anchor for future propose_person_matches
    calls against this person, which is how age progression is handled naturally.
    """
```

Tool annotations:
- `propose_person_matches`: `_read` (readOnlyHint=True)
- `get_face_thumbnail`: `_read`
- `confirm_person_match`: `_write` (idempotent, non-destructive)

The existing `tag_person`, `untag_person`, and `list_people` tools are unchanged.

### CLI surface

```
photo-memex faces detect              # Scan all photos, idempotent
photo-memex faces detect --force      # Re-scan even processed photos
photo-memex faces detect --photo-id X # Re-scan one photo
photo-memex faces stats               # Summary: total faces, tagged, untagged, coverage
```

All live in a new `faces` Typer sub-app registered in `ptk/cli.py`.

### Workflow

```
Initial (one time):
  $ photo-memex faces detect
  → ~3,000 Face rows created with embeddings, all with person_id=NULL

Per-person loop (LLM-driven via MCP):
  1. User: "That's Alice in photo abc123"
  2. LLM: tag_person(photo_id="abc123", person_name="Alice")
     → manual-placeholder Face created (no embedding)
  3. User: "Find more photos of Alice"
  4. LLM: propose_person_matches("Alice")
     → [] because no anchor with embedding exists yet
  5. LLM inspects the photo, finds the detected Face via run_sql or a new
     helper, and calls confirm_person_match to promote that detected face
     → Alice now has one anchor with an embedding
  6. LLM: propose_person_matches("Alice") again
     → returns top-20 similar detected faces
  7. LLM: get_face_thumbnail for each, reviews visually
  8. LLM: confirm_person_match(face_id, "Alice") for each true match
     → each confirmation adds an anchor, widening the search cloud
  9. Repeat 6-8 until proposals drop off in similarity
```

Step 5 is a small UX wart: the LLM needs to find the right detected face in the anchor photo. Options:
- **Option A:** LLM runs `run_sql` to find the Face row for the photo it already tagged, then calls `confirm_person_match`.
- **Option B:** Add a convenience MCP tool `promote_tagged_person_to_detected(photo_id, person_name)` that finds the unambiguous detected face in that photo (if any) and sets `person_id`.

Defer option B. The LLM can do step 5 with run_sql in v1. If it's painful, add B later.

### Threshold strategy

No fixed threshold in the data layer. The matcher returns all candidates sorted by similarity; cutoffs are a UX decision.

**Rationale:**
- A fixed threshold (0.6 cosine distance is the `face_recognition` default) fails on kids who change shape and on lighting variation.
- The LLM has visual judgment via `get_face_thumbnail` and the confirm/reject loop.
- Real calibration data accumulates as the user confirms matches. Future iteration can learn per-person or per-library thresholds from confirmed data.

The user's MCP client (LLM) can apply its own cutoff when asking the user; the data layer stays policy-free.

### Age progression

Implicit via multi-anchor matching. Once the toddler, school-age, and teen faces of Alice are all confirmed, `propose_person_matches("Alice")` computes similarity against each anchor and takes the max. A new teen-era face of Alice ranks highly because of the teen anchor, not the toddler anchor.

No need for `Alice_young` / `Alice_teen` splits. If similarity stays low across all anchors (face is profile, partial, bad lighting), it won't be proposed, and the user handles those manually via `tag_person`.

## Data flow

```
photo.jpg ──► face_recognition.face_locations()
                    │
                    ▼
            (top, right, bottom, left) per face
                    │
                    ▼
          face_recognition.face_encodings()
                    │
                    ▼
            128-dim np.float32 per face
                    │
                    ▼
      Face(photo_id, bbox normalized, embedding=tobytes(), confidence=1.0)

propose_person_matches("Alice"):
  anchors = Face rows where person.name == "Alice" AND embedding IS NOT NULL
  if not anchors: return []
  candidates = Face rows where person_id IS NULL AND embedding IS NOT NULL
  for candidate:
    sim = max(cosine_similarity(candidate.embedding, a.embedding) for a in anchors)
  return top-N by sim
```

## Testing

Unit tests:
- `test_detector.py`: detector produces expected bbox shape (0..1 normalized), embedding shape (128,), dtype float32. Use a fixture image with a synthetic face or a known test photo.
- `test_matcher.py`: cosine_similarity identity (sim(v, v) == 1.0), orthogonality (sim(v, -v) < 0), propose_matches ranking order, empty-anchor case.
- `test_faces_service.py`: idempotency of detect_all (second run is a no-op), force flag re-runs, detect_photo replaces prior detections.

MCP tests:
- `TestProposePersonMatches`: returns empty when no anchor, returns candidates sorted by descending similarity, limit respected, archived people excluded.
- `TestGetFaceThumbnail`: returns Image + metadata, crops to bbox, raises on nonexistent face_id.
- `TestConfirmPersonMatch`: assigns person_id, resurrects archived Person, idempotent.

Integration tests:
- `test_faces_workflow.py`: end-to-end. Detect faces in populated_library → tag one face via tag_person → manually promote to detected via confirm_person_match on the detected face → propose finds zero matches in the single-photo library. Extend to multi-photo once fixture supports it.

## Install / release

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
faces = [
    "face-recognition>=1.3.0",
    "numpy>=1.24.0",
]
```

`numpy` is already implied by Pillow/face_recognition but declare explicitly since we use it directly in matcher.py.

`face-recognition` on PyPI is a distinct package from `face_recognition` on GitHub (same library, different name on PyPI depending on version). Verify the exact PyPI name during implementation.

Migration note for release notes: existing databases need `ALTER TABLE faces ADD COLUMN embedding BLOB;` run manually. Document this. No automated migration in v1.

## Open questions

1. **Face thumbnail source.** `get_face_thumbnail` should crop the face bbox from which image source? The stored `photo.thumbnail_data` (fast, 256px, may be too small for small faces) or the original file at `photo.original_path` (slower, always available, handles missing thumbnails)? Decision: use `original_path`. Thumbnail cropping happens per-request, not stored.

2. **Where in Face.bbox does the cropped thumbnail come from.** Face bboxes are normalized to the original photo dimensions. When cropping from the thumbnail_data (if we use it), we'd scale. Using original_path avoids scaling but requires the file to exist at the path stored in the DB. `photo-memex verify` already exists for this; document that `get_face_thumbnail` requires intact original files.

3. **Numpy dependency weight.** numpy is ~50 MB installed. That's a lot for an optional extra on a tool whose core is metadata-only. Acceptable given the [faces] extra is explicitly opt-in.

## Build order

Suggested implementation sequence for the plan:
1. Add `Face.embedding` column to the model + test
2. Write `ptk/faces/detector.py` with a unit test using a known face image
3. Write `ptk/faces/matcher.py` with unit tests (no DB yet)
4. Write `ptk/faces/service.py` orchestrating detect_all / detect_photo
5. Add the `photo-memex faces` CLI sub-app + integration tests
6. Add the 3 MCP tools + unit tests
7. End-to-end workflow test
8. Update CLAUDE.md, README, and release notes for v0.2.0
