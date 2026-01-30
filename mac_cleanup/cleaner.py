"""
File cleaner for Mac cleanup operations.
Handles safe deletion of files with various safety mechanisms.
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import subprocess

from .scanner import FileInfo, ScanResult


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""
    success: bool
    files_deleted: int = 0
    bytes_freed: int = 0
    errors: List[str] = field(default_factory=list)
    skipped_files: List[Path] = field(default_factory=list)

    @property
    def bytes_freed_formatted(self) -> str:
        """Return human-readable freed space."""
        size = self.bytes_freed
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"


class MacCleaner:
    """Cleaner for removing junk files from macOS."""

    def __init__(
        self,
        dry_run: bool = False,
        verbose: bool = False,
        move_to_trash: bool = True
    ):
        """
        Initialize the cleaner.

        Args:
            dry_run: If True, don't actually delete files
            verbose: If True, print detailed progress
            move_to_trash: If True, move files to Trash instead of permanent delete
        """
        self.dry_run = dry_run
        self.verbose = verbose
        self.move_to_trash = move_to_trash

    def _log(self, message: str):
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(f"  [CLEAN] {message}")

    def _move_to_trash_macos(self, file_path: Path) -> bool:
        """Move a file to Trash on macOS using AppleScript."""
        try:
            # Use AppleScript to move to trash (macOS native way)
            script = f'''
            tell application "Finder"
                delete POSIX file "{file_path}"
            end tell
            '''
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            # Fallback: move to user's Trash folder manually
            try:
                trash_path = Path.home() / ".Trash" / file_path.name
                # Handle name conflicts
                counter = 1
                while trash_path.exists():
                    stem = file_path.stem
                    suffix = file_path.suffix
                    trash_path = Path.home() / ".Trash" / f"{stem}_{counter}{suffix}"
                    counter += 1
                shutil.move(str(file_path), str(trash_path))
                return True
            except Exception:
                return False
        except Exception:
            return False

    def _delete_file(self, file_path: Path) -> bool:
        """Delete a single file safely."""
        try:
            if not file_path.exists():
                return True  # Already gone

            if file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
            return True
        except (PermissionError, OSError) as e:
            self._log(f"Error deleting {file_path}: {e}")
            return False

    def delete_file(self, file_path: Path) -> bool:
        """Delete or move a file to trash."""
        if self.dry_run:
            self._log(f"[DRY RUN] Would delete: {file_path}")
            return True

        if self.move_to_trash:
            success = self._move_to_trash_macos(file_path)
            if success:
                self._log(f"Moved to Trash: {file_path}")
            return success
        else:
            success = self._delete_file(file_path)
            if success:
                self._log(f"Deleted: {file_path}")
            return success

    def clean_files(
        self,
        files: List[FileInfo],
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> CleanupResult:
        """
        Clean a list of files.

        Args:
            files: List of FileInfo objects to clean
            progress_callback: Optional callback(current, total, filename)
        """
        result = CleanupResult(success=True)
        total = len(files)

        for i, file_info in enumerate(files):
            if progress_callback:
                progress_callback(i + 1, total, str(file_info.path))

            try:
                if self.delete_file(file_info.path):
                    result.files_deleted += 1
                    result.bytes_freed += file_info.size
                else:
                    result.errors.append(f"Failed to delete: {file_info.path}")
                    result.skipped_files.append(file_info.path)
            except Exception as e:
                result.errors.append(f"Error with {file_info.path}: {str(e)}")
                result.skipped_files.append(file_info.path)

        if result.errors:
            result.success = len(result.errors) < len(files)

        return result

    def clean_scan_result(
        self,
        scan_result: ScanResult,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> CleanupResult:
        """Clean all files from a scan result."""
        return self.clean_files(scan_result.files, progress_callback)

    def empty_trash(self) -> CleanupResult:
        """Empty the system Trash."""
        result = CleanupResult(success=True)

        if self.dry_run:
            self._log("[DRY RUN] Would empty Trash")
            return result

        try:
            # Use AppleScript to empty trash (safest method)
            script = '''
            tell application "Finder"
                empty trash
            end tell
            '''
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                check=True
            )
            self._log("Trash emptied successfully")
        except subprocess.CalledProcessError as e:
            result.success = False
            result.errors.append(f"Failed to empty trash: {e}")
        except Exception as e:
            result.success = False
            result.errors.append(f"Error emptying trash: {str(e)}")

        return result

    def clean_directory(
        self,
        directory: Path,
        patterns: List[str] = None,
        recursive: bool = True
    ) -> CleanupResult:
        """Clean files matching patterns in a directory."""
        import fnmatch

        result = CleanupResult(success=True)
        patterns = patterns or ["*"]

        if not directory.exists():
            result.errors.append(f"Directory does not exist: {directory}")
            result.success = False
            return result

        try:
            if recursive:
                for root, dirs, files in os.walk(directory):
                    for file in files:
                        if any(fnmatch.fnmatch(file, p) for p in patterns):
                            file_path = Path(root) / file
                            try:
                                size = file_path.stat().st_size
                                if self.delete_file(file_path):
                                    result.files_deleted += 1
                                    result.bytes_freed += size
                            except Exception as e:
                                result.errors.append(f"Error: {str(e)}")
            else:
                for item in directory.iterdir():
                    if item.is_file():
                        if any(fnmatch.fnmatch(item.name, p) for p in patterns):
                            try:
                                size = item.stat().st_size
                                if self.delete_file(item):
                                    result.files_deleted += 1
                                    result.bytes_freed += size
                            except Exception as e:
                                result.errors.append(f"Error: {str(e)}")
        except Exception as e:
            result.errors.append(f"Error scanning directory: {str(e)}")
            result.success = False

        return result

    def run_system_cleanup(self) -> CleanupResult:
        """Run macOS built-in cleanup commands."""
        result = CleanupResult(success=True)

        if self.dry_run:
            self._log("[DRY RUN] Would run system cleanup commands")
            return result

        commands = [
            # Clear system caches (requires password for some)
            ["sudo", "-n", "periodic", "daily", "weekly", "monthly"],
            # Clear DNS cache
            ["sudo", "-n", "dscacheutil", "-flushcache"],
            # Clear font caches
            ["atsutil", "databases", "-remove"],
        ]

        for cmd in commands:
            try:
                subprocess.run(cmd, capture_output=True, timeout=60)
                self._log(f"Ran: {' '.join(cmd)}")
            except subprocess.TimeoutExpired:
                result.errors.append(f"Timeout running: {' '.join(cmd)}")
            except subprocess.CalledProcessError as e:
                result.errors.append(f"Error running {' '.join(cmd)}: {e}")
            except FileNotFoundError:
                pass  # Command not available, skip

        return result

    def clean_brew_cache(self) -> CleanupResult:
        """Clean Homebrew cache using brew cleanup."""
        result = CleanupResult(success=True)

        if self.dry_run:
            self._log("[DRY RUN] Would run brew cleanup")
            return result

        try:
            # Run brew cleanup
            subprocess.run(
                ["brew", "cleanup", "--prune=all"],
                capture_output=True,
                check=True,
                timeout=300
            )
            self._log("Homebrew cache cleaned")
        except FileNotFoundError:
            result.errors.append("Homebrew not installed")
        except subprocess.CalledProcessError as e:
            result.errors.append(f"Homebrew cleanup failed: {e}")
        except subprocess.TimeoutExpired:
            result.errors.append("Homebrew cleanup timed out")

        return result

    def clean_npm_cache(self) -> CleanupResult:
        """Clean NPM cache."""
        result = CleanupResult(success=True)

        if self.dry_run:
            self._log("[DRY RUN] Would run npm cache clean")
            return result

        try:
            subprocess.run(
                ["npm", "cache", "clean", "--force"],
                capture_output=True,
                check=True,
                timeout=120
            )
            self._log("NPM cache cleaned")
        except FileNotFoundError:
            result.errors.append("NPM not installed")
        except subprocess.CalledProcessError as e:
            result.errors.append(f"NPM cache cleanup failed: {e}")
        except subprocess.TimeoutExpired:
            result.errors.append("NPM cache cleanup timed out")

        return result

    def clean_pip_cache(self) -> CleanupResult:
        """Clean pip cache."""
        result = CleanupResult(success=True)

        if self.dry_run:
            self._log("[DRY RUN] Would run pip cache purge")
            return result

        try:
            subprocess.run(
                ["pip", "cache", "purge"],
                capture_output=True,
                check=True,
                timeout=120
            )
            self._log("Pip cache cleaned")
        except FileNotFoundError:
            result.errors.append("Pip not installed")
        except subprocess.CalledProcessError as e:
            result.errors.append(f"Pip cache cleanup failed: {e}")
        except subprocess.TimeoutExpired:
            result.errors.append("Pip cache cleanup timed out")

        return result

    def clean_docker(self) -> CleanupResult:
        """Clean Docker unused images, containers, and volumes."""
        result = CleanupResult(success=True)

        if self.dry_run:
            self._log("[DRY RUN] Would run docker system prune")
            return result

        try:
            subprocess.run(
                ["docker", "system", "prune", "-af", "--volumes"],
                capture_output=True,
                check=True,
                timeout=600
            )
            self._log("Docker cache cleaned")
        except FileNotFoundError:
            result.errors.append("Docker not installed")
        except subprocess.CalledProcessError as e:
            result.errors.append(f"Docker cleanup failed: {e}")
        except subprocess.TimeoutExpired:
            result.errors.append("Docker cleanup timed out")

        return result
