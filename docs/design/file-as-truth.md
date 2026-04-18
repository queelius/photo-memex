# File-as-Truth Architecture

> Design doc for shifting photo-memex from DB-as-truth to file-as-truth.
> Photos carry their own metadata via XMP; the SQLite database is a derived cache.

## Motivation

The current architecture treats `photo-memex.db` as the canonical source of all annotations (captions, tags, people, scenes, events). If the DB is lost, all annotations are lost. If photos are moved to another tool (Lightroom, Apple Photos, Google Photos), annotations don't follow.

The file-as-truth model makes photos self-describing: metadata is embedded in the file (or a sidecar), and the DB is a queryable index that can be rebuilt from the files at any time.

This follows the same philosophy as other tools in the ecosystem: jot stores data in plaintext files, Hugo stores content in markdown, arkiv exports to JSONL. The files are the truth; indexes are derived.

## Architecture

```
photo files (with embedded XMP)     <- ground truth
    |
    |-- standard fields (dc:subject, mwg-rs:Regions, xmp:Rating)
    |       -> readable by Lightroom, Apple Photos, digiKam, etc.
    |
    |-- custom namespace (pmx:aiCaption, pmx:scene, pmx:objects)
    |       -> preserved by other tools, read only by photo-memex
    |
    +-- sidecar .xmp files (for read-only formats, RAW, HEIC)
            -> same XML, separate file

photo-memex.db (SQLite + FTS5)      <- derived cache
    |
    +-- photo-memex import --rebuild    <- reconstructable from files
```

## XMP Field Mapping

### Standard fields (interoperable)

| photo-memex concept | XMP property | Type | Notes |
|---------------------|-------------|------|-------|
| Tags/keywords | `dc:subject` | Bag of strings | Read by all major photo tools |
| Caption | `dc:description` | Lang-alt string | The universal caption field |
| Rating/favorite | `xmp:Rating` | Integer (0-5) | 5 = favorite, 0 = unrated |
| People + bboxes | `mwg-rs:Regions` | Struct array | Media Working Group standard, used by Lightroom/Picasa/digiKam |
| Date taken | `exif:DateTimeOriginal` | Date | Already read from EXIF at import |
| GPS | `exif:GPSLatitude`, `exif:GPSLongitude` | Rational | Already read from EXIF at import |

### Custom namespace (`pmx:`)

```xml
xmlns:pmx="http://metafunctor.com/photo-memex/1.0/"
```

| photo-memex concept | XMP property | Type | Notes |
|---------------------|-------------|------|-------|
| AI caption | `pmx:aiCaption` | String | Separate from dc:description so human captions aren't overwritten |
| Scene classification | `pmx:scene` | String | e.g. "indoor", "outdoor", "portrait" |
| AI-detected objects | `pmx:objects` | String (JSON) | Structured list, stored as JSON string |
| AI model provenance | `pmx:aiModel` | String | e.g. "claude-opus-4-6" |
| AI analysis timestamp | `pmx:aiAnalyzedAt` | Date | ISO 8601 |
| Event name | `pmx:eventName` | String | e.g. "Christmas 2004" |
| Album membership | `pmx:albums` | Bag of strings | Album names this photo belongs to |
| Original content hash | `pmx:originalHash` | String | SHA256 of file content before metadata was written |
| Archive URI | `pmx:archiveUri` | String | e.g. "photo-memex://photo/<sha256>" |
| Import source | `pmx:importSource` | String | "filesystem", "google_takeout", "apple_photos" |
| Archived (soft delete) | `pmx:archivedAt` | Date | ISO 8601, null if active |

### What stays DB-only

Some things don't belong in per-photo metadata:

- **FTS5 index**: derived from captions, rebuilt on cache construction.
- **Thumbnails**: generated from pixel data, stored in DB for fast MCP access.
- **Junction table ordering**: album sort_order, event date ranges.
- **Marginalia**: free-form notes are about the photo but not inherently part of it. Could go in sidecar YAML or in XMP `pmx:marginalia`, but worth keeping simple.

## The SHA256 Wrinkle

Writing XMP into a JPEG changes the file bytes, which changes the SHA256 hash. Two approaches:

**Option A: Original-content hash (recommended)**
1. On first import, compute SHA256 of the file as-is. This is the photo's identity.
2. Store this hash as `pmx:originalHash` in the XMP.
3. The DB primary key is this original hash. It never changes, even as metadata is updated.
4. On re-import/rebuild, if a file has `pmx:originalHash`, use that. Otherwise hash the whole file (new import).

**Option B: Pixel-data hash**
1. Hash only the decoded pixel data (via Pillow), not the metadata envelope.
2. Stable across metadata writes, but slower (requires image decode) and format-dependent.

Option A is simpler and handles the 99% case. The only edge case is if someone strips XMP from a file and re-imports it: the hash changes and it appears as a new photo. This is acceptable.

## Write Strategy

### Dual-write (recommended for transition)

During the transition from DB-as-truth to file-as-truth, writes go to both places:

1. MCP `set_caption` writes to DB (immediate, for fast queries) AND writes XMP to the file.
2. The DB remains the query surface. FTS5 stays in the DB.
3. `photo-memex import --rebuild` reconstructs the DB entirely from file XMP.

### Write-back modes

- **Embedded XMP**: default for JPEG, PNG, TIFF, WebP. Modifies the file in place.
- **Sidecar .xmp**: for RAW formats, HEIC (if embedded write fails), or when the user opts for non-destructive mode. File is `<original_name>.xmp` in the same directory.
- **User preference**: a config flag `metadata_write_mode: embedded | sidecar | both | none`.

## Tooling

### pyexiv2

Primary library for XMP read/write. Pre-compiled wheels on PyPI, no system dependencies.

```python
import pyexiv2

# Register custom namespace (once at module load)
pyexiv2.registerNs("http://metafunctor.com/photo-memex/1.0/", "pmx")

# Write standard + custom fields
with pyexiv2.Image("photo.jpg") as img:
    img.modify_xmp({
        "Xmp.dc.subject": ["vacation", "miami", "family"],
        "Xmp.dc.description": "Parasailing over the ocean near Miami",
        "Xmp.xmp.Rating": "5",
        "Xmp.pmx.aiCaption": "Two people parasailing over the ocean...",
        "Xmp.pmx.aiModel": "claude-opus-4-6",
        "Xmp.pmx.scene": "outdoor",
        "Xmp.pmx.originalHash": "832d3435dccbc17d...",
        "Xmp.pmx.albums": ["Miami Trip"],
        "Xmp.pmx.eventName": "Miami Vacation 2002",
    })

# Read back
with pyexiv2.Image("photo.jpg") as img:
    xmp = img.read_xmp()
    # xmp["Xmp.dc.subject"] -> ["vacation", "miami", "family"]
    # xmp["Xmp.pmx.aiCaption"] -> "Two people parasailing..."
```

### Face regions (mwg-rs:Regions)

The dict API cannot create nested structs. Use `modify_raw_xmp()` with constructed XML:

```python
region_xml = """
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description
      xmlns:mwg-rs="http://www.metadataworkinggroup.com/schemas/regions/"
      xmlns:stDim="http://ns.adobe.com/xap/1.0/sType/Dimensions#"
      xmlns:stArea="http://ns.adobe.com/xmp/sType/Area#">
      <mwg-rs:Regions>
        <mwg-rs:AppliedToDimensions stDim:w="4000" stDim:h="3000" stDim:unit="pixel"/>
        <mwg-rs:RegionList>
          <rdf:Bag>
            <rdf:li>
              <rdf:Description
                mwg-rs:Name="Jane Doe"
                mwg-rs:Type="Face">
                <mwg-rs:Area stArea:x="0.45" stArea:y="0.35"
                             stArea:w="0.12" stArea:h="0.16"
                             stArea:unit="normalized"/>
              </rdf:Description>
            </rdf:li>
          </rdf:Bag>
        </mwg-rs:RegionList>
      </mwg-rs:Regions>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
"""
with pyexiv2.Image("photo.jpg") as img:
    img.modify_raw_xmp(region_xml)
```

Reading back via `read_xmp()` returns flattened paths:
```
Xmp.mwg-rs.Regions/mwg-rs:RegionList[1]/mwg-rs:Name -> "Jane Doe"
Xmp.mwg-rs.Regions/mwg-rs:RegionList[1]/mwg-rs:Area/stArea:x -> "0.45"
```

## Collection-level metadata

Some metadata is about groups of photos, not individual photos:

- **Albums**: ordered collections with name, description, cover photo.
- **Events**: date-ranged groups with location centroid.
- **Marginalia**: free-form notes attachable to any record.

Options for collection metadata:

1. **Per-photo XMP bags** (`pmx:albums`, `pmx:eventName`): each photo carries its memberships. Albums/events are reconstructed from the union of all photos' membership claims. Simple, file-as-truth pure.
2. **Sidecar YAML per directory**: a `.photo-memex.yaml` in each directory with album/event definitions. More efficient for large albums but introduces a non-photo file.
3. **Single library YAML**: one `photo-memex.yaml` at the library root with all collection definitions. Clean but single point of failure.

Recommended: option 1 (per-photo XMP) for album/event membership, option 3 (library YAML) for collection metadata that has no per-photo home (album descriptions, event descriptions, marginalia on deleted photos).

## Migration Path

1. Add `pyexiv2` as an optional dependency (`pip install photo-memex[xmp]`).
2. Add `photo-memex writeback` command: reads DB annotations, writes XMP into files.
3. Add XMP reading to the import pipeline: on import, read XMP and populate DB fields.
4. Add `photo-memex import --rebuild`: reconstruct DB entirely from file XMP.
5. Make MCP write tools dual-write (DB + XMP) when pyexiv2 is available.
6. Eventually: XMP becomes the source of truth, DB is cache. The `--rebuild` command is the proof.

## License Note

pyexiv2 is GPLv3 (wraps libexiv2). photo-memex is currently MIT. If photo-memex ships pyexiv2 as a required dependency, it may need to be GPLv3-compatible. Keeping it as an optional extra (`[xmp]`) avoids this: the core package remains MIT, XMP writeback is an opt-in feature with its own license implications.
