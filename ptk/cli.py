"""Simplified command-line interface for ptk.

Essential commands:
- ptk init          Initialize library
- ptk import        Import photos
- ptk q / query     Query photos (flag-based + SQL)
- ptk show          Show photo details
- ptk set           Modify photo metadata
- ptk stats         Library statistics
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ptk import __version__
from ptk.core.config import PtkConfig, find_library, set_config
from ptk.core.constants import DEFAULT_DATABASE_NAME
from ptk.db.session import init_db, session_scope
from ptk.db.models import Photo, Album, Tag

app = typer.Typer(
    name="ptk",
    help="Photo Toolkit - AI-powered photo library management",
    no_args_is_help=True,
)
console = Console()


# =============================================================================
# Helpers
# =============================================================================

def version_callback(value: bool) -> None:
    if value:
        console.print(f"ptk version {__version__}")
        raise typer.Exit()


def _require_library(path: Optional[Path] = None) -> Path:
    """Find and initialize the library."""
    library_path = find_library(path)
    if library_path is None:
        console.print("[red]No ptk library found.[/red]")
        console.print("Run 'ptk init' to create one.")
        raise typer.Exit(1)

    config = PtkConfig(library_path=library_path)
    set_config(config)
    init_db(config.database_path, create_tables=False)
    return library_path


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", callback=version_callback, is_eager=True,
        help="Show version and exit"
    ),
) -> None:
    """Photo Toolkit - AI-powered photo library management."""
    pass


# =============================================================================
# 1. ptk init
# =============================================================================

@app.command()
def init(
    path: Optional[Path] = typer.Argument(None, help="Library path (default: current directory)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing library"),
) -> None:
    """Initialize a new ptk library."""
    target = (path or Path.cwd()).resolve()
    db_path = target / DEFAULT_DATABASE_NAME

    if db_path.exists() and not force:
        console.print(f"[red]Library exists at {target}[/red]")
        console.print("Use --force to reinitialize")
        raise typer.Exit(1)

    target.mkdir(parents=True, exist_ok=True)
    config = PtkConfig(library_path=target)
    set_config(config)
    init_db(config.database_path, create_tables=True)

    console.print(f"[green]Initialized ptk library at {target}[/green]")


# =============================================================================
# 2. ptk import
# =============================================================================

@app.command("import")
def import_photos(
    path: Path = typer.Argument(None, help="Path to import from"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source type (dir, google, apple)"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r", help="Recursive import"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be imported"),
) -> None:
    """Import photos from a source."""
    if path is None:
        console.print("[red]Error: PATH argument is required[/red]")
        console.print("Usage: ptk import PATH [OPTIONS]")
        raise typer.Exit(1)

    _require_library()

    from ptk.core.config import get_config
    from ptk.importers.filesystem import FilesystemImporter
    from ptk.services.import_service import ImportService

    # Auto-detect source type
    if source is None:
        if path.is_dir():
            source = "dir"
        elif path.suffix.lower() == ".zip":
            source = "google"
        else:
            source = "dir"

    if source == "dir":
        importer = FilesystemImporter(recursive=recursive)
    elif source == "google":
        from ptk.importers.google_takeout import GoogleTakeoutImporter
        importer = GoogleTakeoutImporter()
    elif source == "apple":
        from ptk.importers.apple_photos import ApplePhotosImporter
        importer = ApplePhotosImporter()
    else:
        console.print(f"[red]Unknown source type: {source}[/red]")
        raise typer.Exit(1)

    # Check if path exists
    if not path.exists():
        console.print(f"[red]Path does not exist: {path}[/red]")
        raise typer.Exit(1)

    # Check if importer can handle this path
    if not importer.can_handle(path):
        console.print(f"[red]Not a recognized {importer.name} source: {path}[/red]")
        raise typer.Exit(1)

    config = get_config()
    with session_scope() as session:
        service = ImportService(session, config)

        if dry_run:
            photos = list(importer.scan(path))
            console.print(f"[cyan]Dry run: would import {len(photos)} photos[/cyan]")
            for p in photos[:10]:
                console.print(f"  {p.path}")
            if len(photos) > 10:
                console.print(f"  ... and {len(photos) - 10} more")
            return

        result = service.import_from(importer, path)
        console.print(f"[green]Imported: {result.imported}[/green]")
        if result.duplicates:
            console.print(f"[dim]Duplicates: {result.duplicates}[/dim]")
        if result.errors:
            console.print(f"[yellow]Errors: {result.errors}[/yellow]")


# =============================================================================
# 3. ptk query (ptk q)
# =============================================================================

@app.command("query")
@app.command("q", hidden=True)  # Alias
def query(
    # Filters
    favorite: bool = typer.Option(False, "--favorite", "-f", help="Favorites only"),
    tag: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="Filter by tag (repeatable)"),
    album: Optional[str] = typer.Option(None, "--album", "-a", help="Filter by album"),
    uncaptioned: bool = typer.Option(False, "--uncaptioned", "-u", help="Photos without captions"),
    # SQL mode
    sql: Optional[str] = typer.Option(None, "--sql", help="Raw SQL query"),
    # Output
    format: str = typer.Option("table", "--format", "-o", help="Output: table, json, ids, count, paths"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    offset: int = typer.Option(0, "--offset", help="Skip first N results"),
) -> None:
    """Query photos with filters or SQL.

    Examples:
        ptk q                              # all photos
        ptk q --favorite                   # favorites
        ptk q --tag beach --tag sunset     # photos with both tags
        ptk q --sql "SELECT * FROM photos WHERE caption LIKE '%beach%'"
    """
    _require_library()

    from ptk.query import QueryBuilder, execute_query, execute_sql, OutputFormat

    with session_scope() as session:
        if sql:
            # Raw SQL mode
            result = execute_sql(session, sql, limit=limit)
        else:
            # Flag-based query
            builder = QueryBuilder()

            if favorite:
                builder.favorite()
            if uncaptioned:
                builder.uncaptioned()
            for t in (tag or []):
                builder.tag(t)
            if album:
                builder.album(album)
            builder.limit(limit)
            if offset:
                builder.offset(offset)

            result = execute_query(session, builder)

        # Output
        fmt = OutputFormat(format.lower())
        console.print(result.format(fmt))


# =============================================================================
# 4. ptk show
# =============================================================================

@app.command()
def show(
    photo_id: str = typer.Argument(None, help="Photo ID (can be partial)"),
) -> None:
    """Show photo details and annotations."""
    if photo_id is None:
        console.print("[red]Error: PHOTO_ID argument is required[/red]")
        console.print("Usage: ptk show PHOTO_ID")
        raise typer.Exit(1)

    _require_library()

    with session_scope() as session:
        # Find photo by partial ID
        photo = session.query(Photo).filter(Photo.id.startswith(photo_id)).first()
        if not photo:
            console.print(f"[red]Photo not found: {photo_id}[/red]")
            raise typer.Exit(1)

        # Basic info
        console.print(f"\n[bold]{photo.filename}[/bold]")
        console.print(f"ID: {photo.id}")
        console.print(f"Path: {photo.original_path}")
        if photo.date_taken:
            console.print(f"Date: {photo.date_taken.strftime('%Y-%m-%d %H:%M')}")
        console.print(f"Size: {photo.width}x{photo.height}, {photo.file_size / 1024:.1f} KB")

        # Tags
        if photo.tags:
            tags = ", ".join(t.name for t in photo.tags)
            console.print(f"Tags: {tags}")

        # Albums
        if photo.albums:
            albums = ", ".join(a.name for a in photo.albums)
            console.print(f"Albums: {albums}")

        # Caption
        if photo.caption:
            console.print(f"\n[dim]Caption:[/dim] {photo.caption}")


# =============================================================================
# 5. ptk set
# =============================================================================

@app.command("set")
def set_metadata(
    photo_ids: List[str] = typer.Argument(None, help="Photo ID(s)"),
    # Add operations
    tag: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="Add tag"),
    album: Optional[str] = typer.Option(None, "--album", "-a", help="Add to album"),
    favorite: bool = typer.Option(False, "--favorite", "-f", help="Mark as favorite"),
    caption: Optional[str] = typer.Option(None, "--caption", "-c", help="Set caption"),
    # Remove operations
    untag: Optional[List[str]] = typer.Option(None, "--untag", help="Remove tag"),
    no_favorite: bool = typer.Option(False, "--no-favorite", help="Unmark favorite"),
    no_album: Optional[str] = typer.Option(None, "--no-album", help="Remove from album"),
) -> None:
    """Modify photo metadata.

    Examples:
        ptk set abc123 --tag beach --tag sunset
        ptk set abc123 --favorite
        ptk set abc123 --untag old_tag
        ptk set abc123 --album "Summer 2020"
    """
    if not photo_ids:
        console.print("[red]Error: PHOTO_ID argument is required[/red]")
        console.print("Usage: ptk set PHOTO_ID [OPTIONS]")
        raise typer.Exit(1)

    _require_library()

    with session_scope() as session:
        modified = 0

        for photo_id in photo_ids:
            photo = session.query(Photo).filter(Photo.id.startswith(photo_id)).first()
            if not photo:
                console.print(f"[yellow]Photo not found: {photo_id}[/yellow]")
                continue

            # Add tags
            for t in (tag or []):
                tag_obj = session.query(Tag).filter(Tag.name == t).first()
                if not tag_obj:
                    tag_obj = Tag(name=t)
                    session.add(tag_obj)
                if tag_obj not in photo.tags:
                    photo.tags.append(tag_obj)

            # Remove tags
            for t in (untag or []):
                tag_obj = session.query(Tag).filter(Tag.name == t).first()
                if tag_obj and tag_obj in photo.tags:
                    photo.tags.remove(tag_obj)

            # Add to album
            if album:
                from datetime import datetime, timezone
                album_obj = session.query(Album).filter(Album.name == album).first()
                if not album_obj:
                    now = datetime.now(timezone.utc)
                    album_obj = Album(name=album, created_at=now, updated_at=now)
                    session.add(album_obj)
                if album_obj not in photo.albums:
                    photo.albums.append(album_obj)

            # Remove from album
            if no_album:
                album_obj = session.query(Album).filter(Album.name == no_album).first()
                if album_obj and album_obj in photo.albums:
                    photo.albums.remove(album_obj)

            # Favorite
            if favorite:
                photo.is_favorite = True
            if no_favorite:
                photo.is_favorite = False

            # Caption
            if caption:
                photo.caption = caption

            modified += 1

        console.print(f"[green]Modified {modified} photo(s)[/green]")


# =============================================================================
# 6. ptk stats
# =============================================================================

@app.command()
def stats() -> None:
    """Show library statistics."""
    _require_library()

    with session_scope() as session:
        total = session.query(Photo).count()
        videos = session.query(Photo).filter(Photo.is_video == True).count()
        favorites = session.query(Photo).filter(Photo.is_favorite == True).count()
        with_location = session.query(Photo).filter(Photo.latitude != None).count()
        with_date = session.query(Photo).filter(Photo.date_taken != None).count()

        from sqlalchemy import func
        total_size = session.query(func.sum(Photo.file_size)).scalar() or 0

        table = Table(title="Library Statistics")
        table.add_column("Metric")
        table.add_column("Value", justify="right")

        table.add_row("Total photos", str(total - videos))
        table.add_row("Videos", str(videos))
        table.add_row("Favorites", str(favorites))
        table.add_row("With location", str(with_location))
        table.add_row("With date", str(with_date))
        table.add_row("Total size", f"{total_size / 1024 / 1024:.1f} MB")

        console.print(table)


# =============================================================================
# 7. ptk verify/relocate/rescan (Path management)
# =============================================================================

@app.command()
def verify(
    fix: bool = typer.Option(False, "--fix", help="Tag missing photos as 'missing'"),
) -> None:
    """Verify all photo paths exist on disk."""
    _require_library()

    from pathlib import Path as PathLib

    with session_scope() as session:
        photos = session.query(Photo).all()
        total = len(photos)

        if total == 0:
            console.print("[yellow]No photos in library.[/yellow]")
            return

        missing = []
        found = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Verifying paths...", total=total)

            for photo in photos:
                if PathLib(photo.original_path).exists():
                    found += 1
                else:
                    missing.append(photo)
                progress.advance(task)

        console.print(f"\n[green]Found: {found}[/green]")
        console.print(f"[red]Missing: {len(missing)}[/red]")

        if missing:
            console.print("\n[dim]Missing photos:[/dim]")
            for photo in missing[:20]:
                console.print(f"  {photo.id[:8]}... {photo.original_path}")
            if len(missing) > 20:
                console.print(f"  ... and {len(missing) - 20} more")

            if fix:
                # Tag missing photos
                from ptk.db.models import Tag
                missing_tag = session.query(Tag).filter_by(name="missing").first()
                if not missing_tag:
                    missing_tag = Tag(name="missing")
                    session.add(missing_tag)

                for photo in missing:
                    if missing_tag not in photo.tags:
                        photo.tags.append(missing_tag)

                console.print(f"\n[cyan]Tagged {len(missing)} photos as 'missing'[/cyan]")


@app.command()
def relocate(
    old_prefix: str = typer.Argument(..., help="Old path prefix to replace"),
    new_prefix: str = typer.Argument(..., help="New path prefix"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without changes"),
    verify_paths: bool = typer.Option(False, "--verify", "-v", help="Verify files exist at new paths"),
) -> None:
    """Bulk update path prefixes for moved photo directories."""
    _require_library()

    from pathlib import Path as PathLib

    with session_scope() as session:
        # Find photos with matching prefix
        photos = session.query(Photo).filter(
            Photo.original_path.startswith(old_prefix)
        ).all()

        if not photos:
            console.print(f"[yellow]No photos found with prefix: {old_prefix}[/yellow]")
            return

        console.print(f"Relocating: {old_prefix} -> {new_prefix}")
        console.print(f"Found {len(photos)} photos with matching prefix")

        updated = 0
        verified = 0
        errors = 0

        for photo in photos:
            new_path = photo.original_path.replace(old_prefix, new_prefix, 1)

            if verify_paths:
                if PathLib(new_path).exists():
                    verified += 1
                else:
                    errors += 1
                    console.print(f"[red]Not found: {new_path}[/red]")
                    continue

            if not dry_run:
                photo.original_path = new_path

            updated += 1

        if dry_run:
            console.print(f"\n[cyan]Dry run: would update {updated} paths[/cyan]")
        else:
            console.print(f"\n[green]Updated: {updated}[/green]")

        if verify_paths:
            console.print(f"Verified: {verified}, Errors: {errors}")


@app.command()
def rescan(
    directory: Path = typer.Argument(..., help="Directory to scan for photos"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without changes"),
    missing_only: bool = typer.Option(False, "--missing-only", "-m", help="Only find missing photos"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r", help="Scan subdirectories"),
) -> None:
    """Find moved photos by content hash and update their paths."""
    _require_library()

    from pathlib import Path as PathLib
    from ptk.core.hasher import hash_file
    from ptk.core.constants import SUPPORTED_FORMATS

    if not directory.exists():
        console.print(f"[red]Directory not found: {directory}[/red]")
        raise typer.Exit(1)

    with session_scope() as session:
        # Build lookup of photos we're searching for
        if missing_only:
            # Only look for photos whose paths don't exist
            all_photos = session.query(Photo).all()
            photo_lookup = {
                p.id: p for p in all_photos
                if not PathLib(p.original_path).exists()
            }
            console.print(f"Looking for {len(photo_lookup)} missing photos...")
        else:
            photo_lookup = {p.id: p for p in session.query(Photo).all()}
            console.print(f"Scanning against {len(photo_lookup)} photos in library...")

        if not photo_lookup:
            console.print("[yellow]No photos to search for.[/yellow]")
            return

        # Collect files to scan
        pattern = "**/*" if recursive else "*"
        files_to_scan = [
            f for f in directory.glob(pattern)
            if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS
        ]

        console.print(f"Found {len(files_to_scan)} files to hash...")

        updated = 0
        found_unchanged = 0
        found_hashes = set()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Hashing files...", total=len(files_to_scan))

            for file_path in files_to_scan:
                progress.update(task, description=f"[dim]{file_path.name[:30]}...[/dim]")

                try:
                    file_hash = hash_file(file_path)
                except (IOError, OSError):
                    progress.advance(task)
                    continue

                if file_hash in photo_lookup and file_hash not in found_hashes:
                    found_hashes.add(file_hash)
                    photo = photo_lookup[file_hash]
                    new_path = str(file_path.resolve())

                    if photo.original_path != new_path:
                        if not dry_run:
                            photo.original_path = new_path
                        updated += 1
                        console.print(f"  {file_hash[:8]}... [dim]{photo.original_path}[/dim]")
                        console.print(f"           -> [green]{new_path}[/green]")
                    else:
                        found_unchanged += 1

                progress.advance(task)

        # Summary
        console.print(f"\n[green]Found: {len(found_hashes)} photos[/green]")
        console.print(f"  Updated paths: {updated}")
        console.print(f"  Unchanged: {found_unchanged}")

        still_missing = len(photo_lookup) - len(found_hashes)
        if still_missing > 0:
            console.print(f"[yellow]Still missing: {still_missing}[/yellow]")

        if dry_run and updated > 0:
            console.print(f"\n[cyan]Dry run: no changes made[/cyan]")


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    app()
