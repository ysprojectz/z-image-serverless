"""
Configuration for Mac cleanup paths and categories.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

HOME = Path.home()

@dataclass
class CleanupCategory:
    """Represents a category of files to clean."""
    name: str
    description: str
    paths: List[Path]
    patterns: List[str] = field(default_factory=list)
    safe_to_delete: bool = True
    requires_sudo: bool = False


# Define all cleanup categories
CLEANUP_CATEGORIES = {
    "system_caches": CleanupCategory(
        name="System Caches",
        description="macOS system cache files that can be safely removed",
        paths=[
            HOME / "Library" / "Caches",
            Path("/Library/Caches"),
        ],
        patterns=["*"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "user_caches": CleanupCategory(
        name="User Application Caches",
        description="Application cache files in your user directory",
        paths=[
            HOME / "Library" / "Caches",
        ],
        patterns=["*"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "browser_caches": CleanupCategory(
        name="Browser Caches",
        description="Web browser cache files (Safari, Chrome, Firefox)",
        paths=[
            HOME / "Library" / "Caches" / "com.apple.Safari",
            HOME / "Library" / "Caches" / "Google" / "Chrome",
            HOME / "Library" / "Caches" / "Firefox",
            HOME / "Library" / "Caches" / "com.google.Chrome",
            HOME / "Library" / "Caches" / "org.mozilla.firefox",
        ],
        patterns=["*"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "logs": CleanupCategory(
        name="Log Files",
        description="System and application log files",
        paths=[
            HOME / "Library" / "Logs",
            Path("/var/log"),
            Path("/Library/Logs"),
        ],
        patterns=["*.log", "*.log.*", "*.old"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "downloads": CleanupCategory(
        name="Downloads Folder",
        description="Files in your Downloads folder (older than 30 days)",
        paths=[
            HOME / "Downloads",
        ],
        patterns=["*"],
        safe_to_delete=False,  # Requires confirmation
        requires_sudo=False
    ),

    "trash": CleanupCategory(
        name="Trash",
        description="Files in the Trash that can be permanently deleted",
        paths=[
            HOME / ".Trash",
        ],
        patterns=["*"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "temp_files": CleanupCategory(
        name="Temporary Files",
        description="Temporary files that applications left behind",
        paths=[
            Path("/tmp"),
            Path("/var/tmp"),
            HOME / "Library" / "Application Support" / "CrashReporter",
        ],
        patterns=["*"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "xcode": CleanupCategory(
        name="Xcode Derived Data",
        description="Xcode build caches and derived data (can be very large)",
        paths=[
            HOME / "Library" / "Developer" / "Xcode" / "DerivedData",
            HOME / "Library" / "Developer" / "Xcode" / "Archives",
            HOME / "Library" / "Developer" / "Xcode" / "iOS DeviceSupport",
        ],
        patterns=["*"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "ios_backups": CleanupCategory(
        name="iOS Backups",
        description="iPhone/iPad backup files (can be very large)",
        paths=[
            HOME / "Library" / "Application Support" / "MobileSync" / "Backup",
        ],
        patterns=["*"],
        safe_to_delete=False,  # Requires confirmation
        requires_sudo=False
    ),

    "pip_cache": CleanupCategory(
        name="Python Pip Cache",
        description="Python package installation cache",
        paths=[
            HOME / "Library" / "Caches" / "pip",
            HOME / ".cache" / "pip",
        ],
        patterns=["*"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "npm_cache": CleanupCategory(
        name="NPM Cache",
        description="Node.js package manager cache",
        paths=[
            HOME / ".npm" / "_cacache",
            HOME / ".npm" / "_logs",
        ],
        patterns=["*"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "homebrew_cache": CleanupCategory(
        name="Homebrew Cache",
        description="Homebrew package manager cache",
        paths=[
            HOME / "Library" / "Caches" / "Homebrew",
            Path("/Library/Caches/Homebrew"),
        ],
        patterns=["*"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "docker": CleanupCategory(
        name="Docker Cache",
        description="Docker images, containers, and volumes cache",
        paths=[
            HOME / "Library" / "Containers" / "com.docker.docker" / "Data" / "vms",
            HOME / ".docker",
        ],
        patterns=["*"],
        safe_to_delete=False,  # Requires confirmation
        requires_sudo=False
    ),

    "mail_attachments": CleanupCategory(
        name="Mail Attachments",
        description="Downloaded mail attachments",
        paths=[
            HOME / "Library" / "Containers" / "com.apple.mail" / "Data" / "Library" / "Mail Downloads",
        ],
        patterns=["*"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "ds_store": CleanupCategory(
        name=".DS_Store Files",
        description="macOS folder metadata files",
        paths=[
            HOME,
        ],
        patterns=[".DS_Store"],
        safe_to_delete=True,
        requires_sudo=False
    ),

    "localized_files": CleanupCategory(
        name="Localization Files",
        description="Unused language files from applications",
        paths=[
            Path("/Applications"),
        ],
        patterns=["*.lproj"],
        safe_to_delete=False,  # Can break apps
        requires_sudo=True
    ),
}


# File extensions considered as junk
JUNK_EXTENSIONS = {
    ".tmp", ".temp", ".swp", ".swo", ".bak", ".old", ".orig",
    ".log", ".crash", ".dmp", ".dump",
    ".pyc", ".pyo", "__pycache__",
    ".DS_Store", ".localized",
    ".Spotlight-V100", ".fseventsd", ".Trashes",
}

# Directories that are safe to skip during scanning
SKIP_DIRECTORIES = {
    ".git", ".svn", ".hg",
    "node_modules",
    ".venv", "venv", "env",
    "__pycache__",
    ".idea", ".vscode",
}

# Minimum file age (in days) for downloads cleanup
DOWNLOADS_MIN_AGE_DAYS = 30

# Large file threshold (in MB)
LARGE_FILE_THRESHOLD_MB = 100
