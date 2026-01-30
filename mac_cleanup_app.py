#!/usr/bin/env python3
"""
Mac Cleanup App - Personal System Cleaner for macOS
Author: YS
Version: 1.0.0

A single-file Mac cleanup utility to remove junk files and free up disk space.
No dependencies required - uses Python standard library only.

Usage:
    python3 mac_cleanup.py              # Interactive mode
    python3 mac_cleanup.py --scan       # Scan only
    python3 mac_cleanup.py --clean      # Clean all safe categories
    python3 mac_cleanup.py --dry-run    # Preview without deleting
"""

import os
import sys
import shutil
import hashlib
import argparse
import subprocess
import fnmatch
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Generator
from collections import defaultdict

# ============================================================================
# CONFIGURATION
# ============================================================================

HOME = Path.home()

@dataclass
class CleanupCategory:
    name: str
    description: str
    paths: List[Path]
    patterns: List[str] = field(default_factory=lambda: ["*"])
    safe_to_delete: bool = True

CLEANUP_CATEGORIES = {
    "system_caches": CleanupCategory(
        name="System Caches",
        description="macOS system cache files",
        paths=[HOME / "Library" / "Caches"],
    ),
    "browser_caches": CleanupCategory(
        name="Browser Caches",
        description="Safari, Chrome, Firefox caches",
        paths=[
            HOME / "Library" / "Caches" / "com.apple.Safari",
            HOME / "Library" / "Caches" / "Google" / "Chrome",
            HOME / "Library" / "Caches" / "com.google.Chrome",
            HOME / "Library" / "Caches" / "Firefox",
            HOME / "Library" / "Caches" / "org.mozilla.firefox",
        ],
    ),
    "logs": CleanupCategory(
        name="Log Files",
        description="System and application logs",
        paths=[HOME / "Library" / "Logs"],
        patterns=["*.log", "*.log.*"],
    ),
    "downloads": CleanupCategory(
        name="Old Downloads",
        description="Downloads older than 30 days",
        paths=[HOME / "Downloads"],
        safe_to_delete=False,
    ),
    "trash": CleanupCategory(
        name="Trash",
        description="Files in Trash",
        paths=[HOME / ".Trash"],
    ),
    "temp_files": CleanupCategory(
        name="Temporary Files",
        description="Temp files and crash reports",
        paths=[
            Path("/tmp"),
            Path("/var/tmp"),
            HOME / "Library" / "Application Support" / "CrashReporter",
        ],
    ),
    "xcode": CleanupCategory(
        name="Xcode Cache",
        description="Xcode derived data and archives",
        paths=[
            HOME / "Library" / "Developer" / "Xcode" / "DerivedData",
            HOME / "Library" / "Developer" / "Xcode" / "Archives",
            HOME / "Library" / "Developer" / "Xcode" / "iOS DeviceSupport",
        ],
    ),
    "ios_backups": CleanupCategory(
        name="iOS Backups",
        description="iPhone/iPad backups",
        paths=[HOME / "Library" / "Application Support" / "MobileSync" / "Backup"],
        safe_to_delete=False,
    ),
    "pip_cache": CleanupCategory(
        name="Pip Cache",
        description="Python package cache",
        paths=[HOME / "Library" / "Caches" / "pip", HOME / ".cache" / "pip"],
    ),
    "npm_cache": CleanupCategory(
        name="NPM Cache",
        description="Node.js package cache",
        paths=[HOME / ".npm" / "_cacache", HOME / ".npm" / "_logs"],
    ),
    "homebrew_cache": CleanupCategory(
        name="Homebrew Cache",
        description="Homebrew downloads",
        paths=[HOME / "Library" / "Caches" / "Homebrew"],
    ),
    "docker": CleanupCategory(
        name="Docker Cache",
        description="Docker images and containers",
        paths=[HOME / "Library" / "Containers" / "com.docker.docker" / "Data" / "vms"],
        safe_to_delete=False,
    ),
    "mail_downloads": CleanupCategory(
        name="Mail Downloads",
        description="Mail attachment downloads",
        paths=[HOME / "Library" / "Containers" / "com.apple.mail" / "Data" / "Library" / "Mail Downloads"],
    ),
    "spotify_cache": CleanupCategory(
        name="Spotify Cache",
        description="Spotify streaming cache",
        paths=[HOME / "Library" / "Caches" / "com.spotify.client"],
    ),
    "discord_cache": CleanupCategory(
        name="Discord Cache",
        description="Discord app cache",
        paths=[HOME / "Library" / "Application Support" / "discord" / "Cache"],
    ),
    "slack_cache": CleanupCategory(
        name="Slack Cache",
        description="Slack app cache",
        paths=[HOME / "Library" / "Application Support" / "Slack" / "Cache"],
    ),
}

JUNK_EXTENSIONS = {".tmp", ".temp", ".swp", ".bak", ".old", ".log", ".pyc", ".DS_Store"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".idea", ".vscode"}
DOWNLOADS_MIN_AGE_DAYS = 30
LARGE_FILE_THRESHOLD_MB = 100

# ============================================================================
# COLORS
# ============================================================================

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    @classmethod
    def disable(cls):
        for attr in ['HEADER', 'BLUE', 'CYAN', 'GREEN', 'YELLOW', 'RED', 'ENDC', 'BOLD', 'DIM']:
            setattr(cls, attr, '')

def print_header(text): print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}\n  {text}\n{'='*60}{Colors.ENDC}\n")
def print_section(text): print(f"\n{Colors.BOLD}{Colors.BLUE}--- {text} ---{Colors.ENDC}\n")
def print_ok(text): print(f"{Colors.GREEN}[OK] {text}{Colors.ENDC}")
def print_warn(text): print(f"{Colors.YELLOW}[!] {text}{Colors.ENDC}")
def print_err(text): print(f"{Colors.RED}[ERROR] {text}{Colors.ENDC}")
def print_info(text): print(f"{Colors.CYAN}[i] {text}{Colors.ENDC}")

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024: return f"{size_bytes} B"
    elif size_bytes < 1024**2: return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024**3: return f"{size_bytes/1024**2:.1f} MB"
    else: return f"{size_bytes/1024**3:.2f} GB"

def confirm(msg: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    try:
        resp = input(f"{Colors.YELLOW}{msg}{suffix}{Colors.ENDC}").strip().lower()
        return resp in ('y', 'yes') if resp else default
    except (KeyboardInterrupt, EOFError):
        print()
        return False

# ============================================================================
# FILE INFO & RESULTS
# ============================================================================

@dataclass
class FileInfo:
    path: Path
    size: int
    modified: datetime
    category: str = ""

    @property
    def size_formatted(self) -> str:
        return format_size(self.size)

@dataclass
class ScanResult:
    category: str
    files: List[FileInfo] = field(default_factory=list)
    total_size: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_size_formatted(self) -> str:
        return format_size(self.total_size)

@dataclass
class CleanResult:
    success: bool = True
    files_deleted: int = 0
    bytes_freed: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def bytes_freed_formatted(self) -> str:
        return format_size(self.bytes_freed)

# ============================================================================
# SCANNER
# ============================================================================

class Scanner:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def _get_file_info(self, path: Path, category: str = "") -> Optional[FileInfo]:
        try:
            stat = path.stat()
            return FileInfo(path=path, size=stat.st_size,
                          modified=datetime.fromtimestamp(stat.st_mtime), category=category)
        except (PermissionError, OSError):
            return None

    def scan_directory(self, directory: Path, patterns: List[str] = None,
                      min_age_days: int = 0) -> Generator[FileInfo, None, None]:
        if not directory.exists():
            return
        patterns = patterns or ["*"]
        cutoff = datetime.now() - timedelta(days=min_age_days) if min_age_days > 0 else None

        try:
            for root, dirs, files in os.walk(directory):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in files:
                    if any(fnmatch.fnmatch(f, p) for p in patterns):
                        info = self._get_file_info(Path(root) / f)
                        if info and (not cutoff or info.modified < cutoff):
                            yield info
        except (PermissionError, OSError):
            pass

    def scan_category(self, key: str) -> ScanResult:
        if key not in CLEANUP_CATEGORIES:
            return ScanResult(category=key, errors=[f"Unknown: {key}"])

        cat = CLEANUP_CATEGORIES[key]
        result = ScanResult(category=cat.name)
        min_age = DOWNLOADS_MIN_AGE_DAYS if key == "downloads" else 0

        for path in cat.paths:
            for info in self.scan_directory(path, cat.patterns, min_age):
                info.category = cat.name
                result.files.append(info)
                result.total_size += info.size
        return result

    def scan_all(self) -> Dict[str, ScanResult]:
        return {k: self.scan_category(k) for k in CLEANUP_CATEGORIES}

    def scan_large_files(self, root: Path = None, threshold_mb: float = None, limit: int = 50) -> ScanResult:
        root = root or HOME
        threshold = int((threshold_mb or LARGE_FILE_THRESHOLD_MB) * 1024 * 1024)
        result = ScanResult(category="Large Files")
        large = []

        try:
            for rt, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_DIRS]
                if "Library" in rt:
                    dirs[:] = [d for d in dirs if d not in ["Application Support", "Preferences", "Keychains"]]
                for f in files:
                    info = self._get_file_info(Path(rt) / f, "Large Files")
                    if info and info.size >= threshold:
                        large.append(info)
        except (PermissionError, OSError):
            pass

        large.sort(key=lambda x: x.size, reverse=True)
        result.files = large[:limit]
        result.total_size = sum(f.size for f in result.files)
        return result

    def scan_duplicates(self, root: Path = None, min_size_mb: float = 1.0) -> Dict[str, List[FileInfo]]:
        root = root or HOME
        min_size = int(min_size_mb * 1024 * 1024)
        size_groups: Dict[int, List[Path]] = defaultdict(list)

        try:
            for rt, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_DIRS]
                for f in files:
                    p = Path(rt) / f
                    try:
                        sz = p.stat().st_size
                        if sz >= min_size:
                            size_groups[sz].append(p)
                    except:
                        pass
        except:
            pass

        duplicates = {}
        for size, paths in size_groups.items():
            if len(paths) < 2:
                continue
            hashes: Dict[str, List[Path]] = defaultdict(list)
            for p in paths:
                try:
                    h = hashlib.md5()
                    with open(p, 'rb') as f:
                        h.update(f.read(8192))
                        f.seek(0, 2)
                        h.update(str(f.tell()).encode())
                    hashes[h.hexdigest()].append(p)
                except:
                    pass
            for hsh, dups in hashes.items():
                if len(dups) >= 2:
                    duplicates[hsh] = [self._get_file_info(p, "Duplicate") for p in dups if self._get_file_info(p)]
        return duplicates

    def get_disk_usage(self) -> Dict:
        try:
            total, used, free = shutil.disk_usage("/")
            return {"total": f"{total/1024**3:.1f} GB", "used": f"{used/1024**3:.1f} GB",
                    "free": f"{free/1024**3:.1f} GB", "percent": f"{used/total*100:.1f}%"}
        except:
            return {"error": "Unable to get disk usage"}

# ============================================================================
# CLEANER
# ============================================================================

class Cleaner:
    def __init__(self, dry_run: bool = False, verbose: bool = False, use_trash: bool = True):
        self.dry_run = dry_run
        self.verbose = verbose
        self.use_trash = use_trash

    def _move_to_trash(self, path: Path) -> bool:
        try:
            script = f'tell application "Finder" to delete POSIX file "{path}"'
            subprocess.run(["osascript", "-e", script], capture_output=True, check=True)
            return True
        except:
            try:
                trash = HOME / ".Trash" / path.name
                c = 1
                while trash.exists():
                    trash = HOME / ".Trash" / f"{path.stem}_{c}{path.suffix}"
                    c += 1
                shutil.move(str(path), str(trash))
                return True
            except:
                return False

    def _delete(self, path: Path) -> bool:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
        except:
            return False

    def delete_file(self, path: Path) -> bool:
        if self.dry_run:
            if self.verbose:
                print(f"  [DRY RUN] Would delete: {path}")
            return True
        return self._move_to_trash(path) if self.use_trash else self._delete(path)

    def clean_files(self, files: List[FileInfo], progress: Callable = None) -> CleanResult:
        result = CleanResult()
        for i, f in enumerate(files):
            if progress:
                progress(i+1, len(files), str(f.path))
            if self.delete_file(f.path):
                result.files_deleted += 1
                result.bytes_freed += f.size
            else:
                result.errors.append(str(f.path))
        return result

    def clean_scan_result(self, scan: ScanResult, progress: Callable = None) -> CleanResult:
        return self.clean_files(scan.files, progress)

    def empty_trash(self) -> CleanResult:
        result = CleanResult()
        if self.dry_run:
            print_info("[DRY RUN] Would empty Trash")
            return result
        try:
            subprocess.run(["osascript", "-e", 'tell application "Finder" to empty trash'],
                          capture_output=True, check=True)
        except Exception as e:
            result.success = False
            result.errors.append(str(e))
        return result

    def clean_brew(self) -> CleanResult:
        result = CleanResult()
        if self.dry_run:
            print_info("[DRY RUN] Would run brew cleanup")
            return result
        try:
            subprocess.run(["brew", "cleanup", "--prune=all"], capture_output=True, timeout=300)
        except FileNotFoundError:
            result.errors.append("Homebrew not installed")
        except Exception as e:
            result.errors.append(str(e))
        return result

    def clean_npm(self) -> CleanResult:
        result = CleanResult()
        if self.dry_run:
            print_info("[DRY RUN] Would run npm cache clean")
            return result
        try:
            subprocess.run(["npm", "cache", "clean", "--force"], capture_output=True, timeout=120)
        except FileNotFoundError:
            result.errors.append("NPM not installed")
        except Exception as e:
            result.errors.append(str(e))
        return result

    def clean_pip(self) -> CleanResult:
        result = CleanResult()
        if self.dry_run:
            print_info("[DRY RUN] Would run pip cache purge")
            return result
        try:
            subprocess.run(["pip3", "cache", "purge"], capture_output=True, timeout=120)
        except Exception as e:
            result.errors.append(str(e))
        return result

# ============================================================================
# CLI INTERFACE
# ============================================================================

def show_progress(current: int, total: int, filename: str):
    pct = (current / total) * 100 if total else 0
    bar = '=' * int(30 * current / total) + '-' * (30 - int(30 * current / total)) if total else '-' * 30
    name = filename[-40:] if len(filename) > 40 else filename
    print(f"\r[{bar}] {pct:5.1f}% {name:<40}", end='', flush=True)

def print_scan_result(result: ScanResult, show_files: bool = False, max_files: int = 10):
    print(f"\n{Colors.BOLD}{result.category}{Colors.ENDC}")
    print(f"  Files: {Colors.CYAN}{result.file_count:,}{Colors.ENDC}")
    print(f"  Size:  {Colors.GREEN}{result.total_size_formatted}{Colors.ENDC}")

    if show_files and result.files:
        print(f"\n  {Colors.DIM}Top files:{Colors.ENDC}")
        for f in sorted(result.files, key=lambda x: x.size, reverse=True)[:max_files]:
            print(f"    {f.size_formatted:>10}  {f.path}")
        if result.file_count > max_files:
            print(f"    {Colors.DIM}... and {result.file_count - max_files} more{Colors.ENDC}")

def interactive_menu(scanner: Scanner, cleaner: Cleaner):
    print_header("Mac Cleanup App - Personal Edition")

    disk = scanner.get_disk_usage()
    if "error" not in disk:
        print(f"Disk: {disk['used']} / {disk['total']} ({disk['percent']} used)")
        print(f"Free: {Colors.GREEN}{disk['free']}{Colors.ENDC}")

    while True:
        print_section("Main Menu")
        print("1. Quick Scan (all categories)")
        print("2. Scan specific category")
        print("3. Find large files")
        print("4. Find duplicates")
        print("5. Clean package caches (brew, npm, pip)")
        print("6. Empty Trash")
        print("7. Run full cleanup")
        print("0. Exit")

        try:
            choice = input(f"\n{Colors.CYAN}Choice [0-7]: {Colors.ENDC}").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if choice == '0':
            print("\nGoodbye!")
            break
        elif choice == '1':
            quick_scan(scanner, cleaner)
        elif choice == '2':
            category_scan(scanner, cleaner)
        elif choice == '3':
            large_file_scan(scanner, cleaner)
        elif choice == '4':
            duplicate_scan(scanner)
        elif choice == '5':
            clean_package_managers(cleaner)
        elif choice == '6':
            empty_trash(cleaner)
        elif choice == '7':
            full_cleanup(scanner, cleaner)

def quick_scan(scanner: Scanner, cleaner: Cleaner):
    print_section("Quick Scan")
    results = {}
    total = 0

    for key, cat in CLEANUP_CATEGORIES.items():
        print(f"  Scanning {cat.name}...", end='', flush=True)
        r = scanner.scan_category(key)
        results[key] = r
        total += r.total_size
        print(f" {r.total_size_formatted}")

    print_section("Results")
    print(f"Total reclaimable: {Colors.GREEN}{Colors.BOLD}{format_size(total)}{Colors.ENDC}")

    if total > 0 and confirm("\nClean these files?"):
        for key, r in sorted(results.items(), key=lambda x: x[1].total_size, reverse=True):
            if r.total_size > 0:
                cat = CLEANUP_CATEGORIES[key]
                if not cat.safe_to_delete and not confirm(f"  Clean {cat.name}?"):
                    continue
                print(f"  Cleaning {cat.name}...")
                res = cleaner.clean_scan_result(r, show_progress)
                print()
                print_ok(f"  Freed {res.bytes_freed_formatted}")

def category_scan(scanner: Scanner, cleaner: Cleaner):
    print_section("Categories")
    cats = list(CLEANUP_CATEGORIES.items())
    for i, (k, c) in enumerate(cats, 1):
        print(f"  {i}. {c.name} - {Colors.DIM}{c.description}{Colors.ENDC}")

    try:
        idx = int(input(f"\n{Colors.CYAN}Select [1-{len(cats)}]: {Colors.ENDC}")) - 1
        if 0 <= idx < len(cats):
            key, cat = cats[idx]
            print_info(f"Scanning {cat.name}...")
            r = scanner.scan_category(key)
            print_scan_result(r, show_files=True)
            if r.files and confirm("\nClean?"):
                res = cleaner.clean_scan_result(r, show_progress)
                print()
                print_ok(f"Freed {res.bytes_freed_formatted}")
    except (ValueError, KeyboardInterrupt, EOFError):
        pass

def large_file_scan(scanner: Scanner, cleaner: Cleaner):
    print_section("Large File Finder")
    try:
        thresh = input(f"{Colors.CYAN}Min size MB [100]: {Colors.ENDC}").strip()
        thresh = float(thresh) if thresh else 100
    except:
        return

    print_info(f"Scanning for files > {thresh} MB...")
    r = scanner.scan_large_files(HOME, thresh)
    print_scan_result(r, show_files=True, max_files=20)

    if r.files and confirm("\nReview and delete specific files?"):
        for f in r.files[:20]:
            if confirm(f"  Delete {f.path} ({f.size_formatted})?"):
                res = cleaner.clean_files([f])
                if res.success:
                    print_ok(f"    Freed {res.bytes_freed_formatted}")

def duplicate_scan(scanner: Scanner):
    print_section("Duplicate Finder")
    print_info("Scanning for duplicates (this may take a while)...")
    dups = scanner.scan_duplicates(HOME)

    if not dups:
        print_ok("No duplicates found!")
        return

    total_waste = 0
    print(f"\nFound {len(dups)} duplicate sets:\n")
    for i, (h, files) in enumerate(list(dups.items())[:10], 1):
        print(f"{Colors.BOLD}Set {i}:{Colors.ENDC}")
        for f in files:
            if f:
                print(f"  {f.size_formatted:>10}  {f.path}")
        waste = sum(f.size for f in files[1:] if f)
        total_waste += waste
        print(f"  {Colors.DIM}Savings: {format_size(waste)}{Colors.ENDC}\n")

    print(f"{Colors.GREEN}Total potential savings: {format_size(total_waste)}{Colors.ENDC}")
    print_warn("Manual review recommended before deleting.")

def clean_package_managers(cleaner: Cleaner):
    print_section("Package Manager Cleanup")
    for name, func in [("Homebrew", cleaner.clean_brew), ("NPM", cleaner.clean_npm), ("Pip", cleaner.clean_pip)]:
        if confirm(f"Clean {name} cache?"):
            print_info(f"Cleaning {name}...")
            r = func()
            if r.success and not r.errors:
                print_ok(f"{name} cleaned")
            else:
                for e in r.errors:
                    print_warn(e)

def empty_trash(cleaner: Cleaner):
    print_section("Empty Trash")
    if confirm("Empty Trash? This cannot be undone."):
        r = cleaner.empty_trash()
        if r.success:
            print_ok("Trash emptied!")
        else:
            for e in r.errors:
                print_err(e)

def full_cleanup(scanner: Scanner, cleaner: Cleaner):
    print_section("Full Cleanup")
    print_warn("This will clean all safe categories.")

    if not confirm("Proceed?"):
        return

    total_freed = 0
    for key, cat in CLEANUP_CATEGORIES.items():
        if cat.safe_to_delete:
            print(f"\nCleaning {cat.name}...")
            r = scanner.scan_category(key)
            if r.files:
                res = cleaner.clean_scan_result(r, show_progress)
                print()
                total_freed += res.bytes_freed
                print_ok(f"  Freed {res.bytes_freed_formatted}")

    print("\nCleaning package managers...")
    cleaner.clean_brew()
    cleaner.clean_npm()
    cleaner.clean_pip()

    print_section("Complete")
    print_ok(f"Total freed: {format_size(total_freed)}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Mac Cleanup App - Personal System Cleaner")
    parser.add_argument('--scan', action='store_true', help='Scan all categories')
    parser.add_argument('--clean', action='store_true', help='Clean all safe categories')
    parser.add_argument('--large-files', action='store_true', help='Find large files')
    parser.add_argument('--duplicates', action='store_true', help='Find duplicates')
    parser.add_argument('--dry-run', action='store_true', help='Preview without deleting')
    parser.add_argument('--no-trash', action='store_true', help='Permanently delete')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--no-color', action='store_true', help='Disable colors')
    parser.add_argument('--threshold', type=float, default=100, help='Large file threshold (MB)')
    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    scanner = Scanner(verbose=args.verbose)
    cleaner = Cleaner(dry_run=args.dry_run, verbose=args.verbose, use_trash=not args.no_trash)

    if args.dry_run:
        print_warn("DRY RUN MODE - No files will be deleted")

    if args.scan:
        print_header("Scanning All Categories")
        results = scanner.scan_all()
        total = 0
        for r in results.values():
            print_scan_result(r)
            total += r.total_size
        print(f"\n{Colors.BOLD}Total reclaimable: {format_size(total)}{Colors.ENDC}")

    elif args.clean:
        print_header("Full Cleanup")
        full_cleanup(scanner, cleaner)

    elif args.large_files:
        print_header("Large Files")
        r = scanner.scan_large_files(HOME, args.threshold)
        print_scan_result(r, show_files=True, max_files=30)

    elif args.duplicates:
        print_header("Duplicates")
        dups = scanner.scan_duplicates(HOME)
        total = 0
        for h, files in list(dups.items())[:20]:
            print("\nDuplicate set:")
            for f in files:
                if f:
                    print(f"  {f.size_formatted:>10}  {f.path}")
            total += sum(f.size for f in files[1:] if f)
        print(f"\n{Colors.BOLD}Potential savings: {format_size(total)}{Colors.ENDC}")

    else:
        interactive_menu(scanner, cleaner)

if __name__ == "__main__":
    main()
