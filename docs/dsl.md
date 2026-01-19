# ptk View DSL Reference

This document describes the YAML-based DSL for defining views, profiles, and selectors in ptk.

## Core Concepts

The view system follows SICP principles of abstraction and composition:

| Concept | Purpose | Analogy |
|---------|---------|---------|
| **Field** | Primitive extraction unit | Atom |
| **Profile** | Collection of fields | Molecule |
| **View** | Profile + selector + compute settings | Expression |
| **Predicate** | Query expression | Filter |

## Field Types

Fields define what to extract from each photo.

```yaml
fields:
  - name: caption
    type: text
    prompt: "Describe this photo in one sentence."

  - name: people_count
    type: integer
    prompt: "How many people are visible? Answer with just a number."
    default: 0

  - name: is_outdoor
    type: boolean
    prompt: "Is this photo taken outdoors? Answer yes or no."

  - name: decade
    type: enum
    options: ["1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s"]
    prompt: "What decade does this photo appear to be from?"

  - name: tags
    type: list
    prompt: "List relevant tags for this photo, separated by commas."
```

### Type Reference

| Type | Python Type | Parsing | Example |
|------|-------------|---------|---------|
| `string` | `str` | Direct | "beach sunset" |
| `text` | `str` | Direct (longer) | Multi-sentence description |
| `integer` | `int` | Extract first number | "3 people" → 3 |
| `float` | `float` | Extract first decimal | "0.85 confidence" → 0.85 |
| `boolean` | `bool` | yes/true/1 → True | "yes" → True |
| `enum` | `str` | Match from options | "1980s" |
| `list` | `list[str]` | Split on comma | "beach, sunset, family" → [...] |

## Profiles

Profiles group related fields for a specific annotation task.

```yaml
profiles:
  - name: family
    description: "Family photo analysis"
    fields:
      - name: caption
        type: text
        prompt: "Describe this family photo."

      - name: people_count
        type: integer
        prompt: "How many people are in the photo?"
        default: 0

      - name: has_children
        type: boolean
        prompt: "Are there children (under 18) in this photo?"
        default: false

      - name: decade
        type: enum
        options: ["1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s", "unknown"]
        prompt: "What decade does this photo appear to be from?"
        default: "unknown"
```

### Built-in Profiles

| Profile | Fields | Best For |
|---------|--------|----------|
| `quick` | caption, scene | Fast overview |
| `family` | caption, people_count, has_children, decade, setting, occasion, mood, tags | Family archives |
| `detailed` | All family fields + activities, weather, colors, objects, quality | Comprehensive |
| `minimal` | caption | Just descriptions |
| `portrait` | subject, expression, pose, lighting, style | Portrait photos |

## Views

Views apply a profile to photos and store the results.

```yaml
views:
  - name: family_v1
    version: 1
    description: "Family photo annotations using qwen3-vl"
    profile: family

    compute:
      model: qwen3-vl:8b
      host: localhost:11434

    selector:  # Optional: which photos to process
      and:
        - tags: { contains: "family" }
        - photo.date_taken: { gte: "1970-01-01" }
```

### Compute Settings

```yaml
compute:
  model: qwen3-vl:8b      # Ollama model name
  host: localhost:11434   # Ollama server (host:port)
```

## Predicates (Selectors)

Predicates filter photos for views. They are used in YAML view definitions to select which photos a view should process.

> **Note:** For CLI queries, use `ptk q` with flags (`--tag`, `--view`, `--field`) or raw SQL (`--sql`). See the CLI Quick Reference section below. Predicates here are for view YAML definitions only.

Predicates compose using logical operators.

### Comparison Operators

```yaml
# Equality
field: value
field: { eq: value }

# Inequality
field: { ne: value }

# Numeric comparison
field: { gt: 5 }
field: { gte: 5 }
field: { lt: 10 }
field: { lte: 10 }
field: { between: [5, 10] }

# String/list operations
field: { contains: "beach" }
field: { matches: "^IMG_.*" }  # Regex

# List membership
field: { in: ["1980s", "1990s"] }

# Existence
field: { exists: true }
field: { exists: false }
```

### Logical Operators

```yaml
# AND - all conditions must match
and:
  - field1: value1
  - field2: value2

# OR - any condition can match
or:
  - field1: value1
  - field2: value2

# NOT - negate a condition
not:
  field: value
```

### Field Paths

```yaml
# Photo attributes
photo.filename: { contains: "vacation" }
photo.date_taken: { gte: "2020-01-01" }
photo.is_favorite: true

# View annotations
view.family_v1.decade: "1980s"
view.family_v1.people_count: { gt: 2 }
view.family_v1.has_children: true

# Shorthand (searches all views)
decade: "1980s"
people_count: { gt: 2 }

# Special fields
tags: { contains: "beach" }
albums: { contains: "Vacation" }
filename: { matches: "IMG_.*" }
```

### Complex Examples

```yaml
# Photos from the 80s or 90s with children
selector:
  and:
    - view.family_v1.decade: { in: ["1980s", "1990s"] }
    - view.family_v1.has_children: true

# Outdoor photos with 3+ people, not from vacations
selector:
  and:
    - view.family_v1.setting: "outdoor"
    - view.family_v1.people_count: { gte: 3 }
    - not:
        tags: { contains: "vacation" }

# Either favorites OR photos tagged "important"
selector:
  or:
    - photo.is_favorite: true
    - tags: { contains: "important" }
```

## CLI Quick Reference

```bash
# View management
ptk view list                              # List all views
ptk view create NAME -p PROFILE -m MODEL   # Create view
ptk view run NAME [--limit N]              # Run computation

# Querying with flags
ptk q                                      # All photos
ptk q --favorite                           # Favorites only
ptk q --tag beach                          # Has tag 'beach'
ptk q --tag beach --tag sunset             # Has BOTH tags (AND)
ptk q --album "Summer 2020"                # In album
ptk q --view family_v1                     # Has view annotations
ptk q --field decade=1980s                 # Field equals value
ptk q --field people_count>2               # Numeric comparison
ptk q --view family_v1 --field decade=1980s  # Combine view + field

# Output formats
ptk q --favorite --format table            # Default (human readable)
ptk q --favorite --format json             # JSON for scripts
ptk q --favorite --format ids              # Just IDs (for piping)
ptk q --favorite --format count            # Just count

# Raw SQL for complex queries
ptk q --sql "SELECT * FROM photos WHERE caption LIKE '%beach%'"
ptk q --sql "SELECT p.id FROM photos p JOIN view_annotations va ON p.id = va.photo_id WHERE va.field_name = 'decade' AND va.value_json = '\"1980s\"'"
```

## Custom Profiles

Create `~/.config/ptk/profiles.yaml` or `<library>/profiles.yaml`:

```yaml
profiles:
  - name: my_custom
    description: "My custom analysis"
    fields:
      - name: subject
        type: string
        prompt: "What is the main subject of this photo?"

      - name: quality
        type: enum
        options: ["excellent", "good", "fair", "poor"]
        prompt: "Rate the technical quality of this photo."
        default: "good"
```

Then use: `ptk view create myview --profile my_custom`

## Design Principles

1. **Composability**: Profiles compose fields, views compose profiles with selectors
2. **Independence**: Multiple views on same photos don't interfere
3. **Materialization**: Views pre-compute expensive operations (LLM calls)
4. **Declarative**: YAML describes *what*, not *how*
5. **Extensibility**: Add custom profiles without code changes
