"""
File scanner for Mac cleanup operations.
Scans directories for junk files, large files, and duplicates.
"""

import os
import hashlib
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional, Generator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import fnmatch

from .config import (
    CLEANUP_CATEGORIES,
    JUNK_EXTENSIONS,
    SKIP_DIRECTORIES,
    LARGE_FILE_THRESHOLD_MB,
    DOWNLOADS_MIN_AGE_DAYS,
    CleanupCategory,
    HOME
)


@dataclass
class FileInfo:
    """Information about a scanned file."""
    path: Path
    size: int
    modified_time: datetime
    category: str = ""

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)

    @property
    def size_formatted(self) -> str:
        """Return human-readable file size."""
        if self.size < 1024:
            return f"{self.size} B"
        elif self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f} KB"
        elif self.size < 1024 * 1024 * 1024:
            return f"{self.size / (1024 * 1024):.1f} MB"
        else:
            return f"{self.size / (1024 * 1024 * 1024):.2f} GB"


@dataclass
class ScanResult:
    """Results from a cleanup scan."""
    category: str
    files: List[FileInfo] = field(default_factory=list)
    total_size: int = 0
    file_count: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def total_size_formatted(self) -> str:
        """Return human-readable total size."""
        size = self.total_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"


class MacCleanupScanner:
    """Scanner for finding junk files and cleanup opportunities on macOS."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._file_hashes: Dict[str, List[Path]] = defaultdict(list)

    def _log(self, message: str):
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(f"  [SCAN] {message}")

    def _is_safe_to_access(self, path: Path) -> bool:
        """Check if a path is safe to access."""
        try:
            # Check if path exists and is accessible
            return path.exists()
        except (PermissionError, OSError):
            return False

    def _should_skip_dir(self, dir_path: Path) -> bool:
        """Check if a directory should be skipped during scanning."""
        return dir_path.name in SKIP_DIRECTORIES

    def _get_file_info(self, file_path: Path, category: str = "") -> Optional[FileInfo]:
        """Get file information safely."""
        try:
            stat = file_path.stat()
            return FileInfo(
                path=file_path,
                size=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime),
                category=category
            )
        except (PermissionError, OSError, FileNotFoundError):
            return None

    def _scan_directory(
        self,
        directory: Path,
        patterns: List[str] = None,
        recursive: bool = True,
        min_age_days: int = 0
    ) -> Generator[FileInfo, None, None]:
        """Scan a directory for files matching patterns."""
        if not self._is_safe_to_access(directory):
            return

        patterns = patterns or ["*"]
        cutoff_date = datetime.now() - timedelta(days=min_age_days) if min_age_days > 0 else None

        try:
            if recursive:
                for root, dirs, files in os.walk(directory):
                    root_path = Path(root)

                    # Filter out directories to skip
                    dirs[:] = [d for d in dirs if d not in SKIP_DIRECTORIES]

                    for file in files:
                        file_path = root_path / file

                        # Check if file matches any pattern
                        if any(fnmatch.fnmatch(file, pattern) for pattern in patterns):
                            file_info = self._get_file_info(file_path)
                            if file_info:
                                # Check age if required
                                if cutoff_date and file_info.modified_time > cutoff_date:
                                    continue
                                yield file_info
            else:
                for item in directory.iterdir():
                    if item.is_file():
                        if any(fnmatch.fnmatch(item.name, pattern) for pattern in patterns):
                            file_info = self._get_file_info(item)
                            if file_info:
                                if cutoff_date and file_info.modified_time > cutoff_date:
                                    continue
                                yield file_info
        except (PermissionError, OSError) as e:
            self._log(f"Error scanning {directory}: {e}")

    def scan_category(self, category_key: str) -> ScanResult:
        """Scan files for a specific cleanup category."""
        if category_key not in CLEANUP_CATEGORIES:
            return ScanResult(
                category=category_key,
                errors=[f"Unknown category: {category_key}"]
            )

        category = CLEANUP_CATEGORIES[category_key]
        result = ScanResult(category=category.name)

        self._log(f"Scanning category: {category.name}")

        # Special handling for downloads (age-based)
        min_age = DOWNLOADS_MIN_AGE_DAYS if category_key == "downloads" else 0

        for path in category.paths:
            if not path.exists():
                self._log(f"Path does not exist: {path}")
                continue

            self._log(f"Scanning: {path}")

            try:
                for file_info in self._scan_directory(
                    path,
                    patterns=category.patterns,
                    min_age_days=min_age
                ):
                    file_info.category = category.name
                    result.files.append(file_info)
                    result.total_size += file_info.size
                    result.file_count += 1
            except Exception as e:
                result.errors.append(f"Error scanning {path}: {str(e)}")

        return result

    def scan_all_categories(self) -> Dict[str, ScanResult]:
        """Scan all cleanup categories."""
        results = {}
        for category_key in CLEANUP_CATEGORIES:
            results[category_key] = self.scan_category(category_key)
        return results

    def scan_large_files(
        self,
        root_path: Path = None,
        threshold_mb: float = None,
        limit: int = 50
    ) -> ScanResult:
        """Find large files that might be candidates for cleanup."""
        root_path = root_path or HOME
        threshold_mb = threshold_mb or LARGE_FILE_THRESHOLD_MB
        threshold_bytes = int(threshold_mb * 1024 * 1024)

        result = ScanResult(category="Large Files")
        self._log(f"Scanning for files larger than {threshold_mb} MB in {root_path}")

        large_files: List[FileInfo] = []

        try:
            for root, dirs, files in os.walk(root_path):
                root_path_obj = Path(root)

                # Skip system and hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_DIRECTORIES]

                # Skip Library subdirectories that shouldn't be touched
                if "Library" in str(root_path_obj):
                    skip_library = [
                        "Application Support", "Preferences", "Keychains",
                        "Mail", "Messages", "Safari"
                    ]
                    dirs[:] = [d for d in dirs if d not in skip_library]

                for file in files:
                    file_path = root_path_obj / file
                    file_info = self._get_file_info(file_path, "Large Files")

                    if file_info and file_info.size >= threshold_bytes:
                        large_files.append(file_info)
        except (PermissionError, OSError) as e:
            result.errors.append(f"Error scanning: {str(e)}")

        # Sort by size (largest first) and limit results
        large_files.sort(key=lambda f: f.size, reverse=True)
        result.files = large_files[:limit]
        result.total_size = sum(f.size for f in result.files)
        result.file_count = len(result.files)

        return result

    def _compute_file_hash(self, file_path: Path, chunk_size: int = 8192) -> Optional[str]:
        """Compute MD5 hash of a file for duplicate detection."""
        try:
            hasher = hashlib.md5()
            with open(file_path, 'rb') as f:
                # For large files, only hash first and last chunks
                first_chunk = f.read(chunk_size)
                if not first_chunk:
                    return None
                hasher.update(first_chunk)

                # Get file size
                f.seek(0, 2)
                size = f.tell()

                if size > chunk_size * 2:
                    f.seek(-chunk_size, 2)
                    last_chunk = f.read(chunk_size)
                    hasher.update(last_chunk)

                # Include file size in hash for better accuracy
                hasher.update(str(size).encode())

            return hasher.hexdigest()
        except (PermissionError, OSError, IOError):
            return None

    def scan_duplicates(
        self,
        root_path: Path = None,
        min_size_mb: float = 1.0
    ) -> Dict[str, List[FileInfo]]:
        """Find duplicate files based on content hash."""
        root_path = root_path or HOME
        min_size_bytes = int(min_size_mb * 1024 * 1024)

        self._log(f"Scanning for duplicates in {root_path} (min size: {min_size_mb} MB)")

        # Group files by size first (quick pre-filter)
        size_groups: Dict[int, List[Path]] = defaultdict(list)

        try:
            for root, dirs, files in os.walk(root_path):
                root_path_obj = Path(root)

                # Skip system directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_DIRECTORIES]

                for file in files:
                    file_path = root_path_obj / file
                    try:
                        size = file_path.stat().st_size
                        if size >= min_size_bytes:
                            size_groups[size].append(file_path)
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass

        # Now hash files that have matching sizes
        duplicates: Dict[str, List[FileInfo]] = {}

        for size, paths in size_groups.items():
            if len(paths) < 2:
                continue

            # Compute hashes for files with same size
            hash_groups: Dict[str, List[Path]] = defaultdict(list)
            for path in paths:
                file_hash = self._compute_file_hash(path)
                if file_hash:
                    hash_groups[file_hash].append(path)

            # Collect actual duplicates
            for file_hash, dup_paths in hash_groups.items():
                if len(dup_paths) >= 2:
                    dup_files = []
                    for path in dup_paths:
                        file_info = self._get_file_info(path, "Duplicate")
                        if file_info:
                            dup_files.append(file_info)
                    if len(dup_files) >= 2:
                        duplicates[file_hash] = dup_files

        return duplicates

    def scan_junk_files(self, root_path: Path = None) -> ScanResult:
        """Scan for common junk file types."""
        root_path = root_path or HOME
        result = ScanResult(category="Junk Files")

        self._log(f"Scanning for junk files in {root_path}")

        try:
            for root, dirs, files in os.walk(root_path):
                root_path_obj = Path(root)

                # Skip hidden and system directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_DIRECTORIES]

                for file in files:
                    file_path = root_path_obj / file

                    # Check if file matches junk patterns
                    is_junk = False

                    # Check extension
                    if file_path.suffix.lower() in JUNK_EXTENSIONS:
                        is_junk = True

                    # Check exact filename
                    if file in JUNK_EXTENSIONS:
                        is_junk = True

                    # Check common junk patterns
                    junk_patterns = [
                        "Thumbs.db", "desktop.ini", ".DS_Store",
                        "*.pyc", "*.pyo", "*.class",
                        "*~", "*.swp", "*.swo"
                    ]
                    if any(fnmatch.fnmatch(file, pattern) for pattern in junk_patterns):
                        is_junk = True

                    if is_junk:
                        file_info = self._get_file_info(file_path, "Junk Files")
                        if file_info:
                            result.files.append(file_info)
                            result.total_size += file_info.size
                            result.file_count += 1
        except (PermissionError, OSError) as e:
            result.errors.append(f"Error scanning: {str(e)}")

        return result

    def get_disk_usage(self) -> Dict[str, any]:
        """Get current disk usage statistics."""
        import shutil

        try:
            total, used, free = shutil.disk_usage("/")
            return {
                "total": total,
                "used": used,
                "free": free,
                "percent_used": (used / total) * 100,
                "total_formatted": f"{total / (1024**3):.1f} GB",
                "used_formatted": f"{used / (1024**3):.1f} GB",
                "free_formatted": f"{free / (1024**3):.1f} GB",
            }
        except Exception as e:
            return {"error": str(e)}
