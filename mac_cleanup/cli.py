"""
Command-line interface for Mac Cleanup App.
Provides an interactive menu for cleaning junk files.
"""

import sys
import argparse
from pathlib import Path
from typing import List, Optional

from .scanner import MacCleanupScanner, ScanResult, FileInfo
from .cleaner import MacCleaner, CleanupResult
from .config import CLEANUP_CATEGORIES, HOME


class Colors:
    """ANSI color codes for terminal output."""
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
        """Disable colors for non-terminal output."""
        cls.HEADER = ''
        cls.BLUE = ''
        cls.CYAN = ''
        cls.GREEN = ''
        cls.YELLOW = ''
        cls.RED = ''
        cls.ENDC = ''
        cls.BOLD = ''
        cls.DIM = ''


def print_header(text: str):
    """Print a styled header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {text}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.ENDC}\n")


def print_section(text: str):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}--- {text} ---{Colors.ENDC}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}[OK] {text}{Colors.ENDC}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}[!] {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}[ERROR] {text}{Colors.ENDC}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.CYAN}[i] {text}{Colors.ENDC}")


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def confirm_action(message: str, default: bool = False) -> bool:
    """Ask user for confirmation."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    try:
        response = input(f"{Colors.YELLOW}{message}{suffix}{Colors.ENDC}").strip().lower()
        if not response:
            return default
        return response in ('y', 'yes')
    except (KeyboardInterrupt, EOFError):
        print()
        return False


def show_progress(current: int, total: int, filename: str):
    """Show progress during cleanup."""
    percent = (current / total) * 100 if total > 0 else 0
    bar_length = 30
    filled = int(bar_length * current / total) if total > 0 else 0
    bar = '=' * filled + '-' * (bar_length - filled)
    # Truncate filename if too long
    max_name_len = 40
    display_name = filename if len(filename) <= max_name_len else '...' + filename[-(max_name_len-3):]
    print(f"\r[{bar}] {percent:5.1f}% ({current}/{total}) {display_name:<{max_name_len}}", end='', flush=True)


def print_scan_result(result: ScanResult, show_files: bool = False, max_files: int = 10):
    """Print a formatted scan result."""
    print(f"\n{Colors.BOLD}{result.category}{Colors.ENDC}")
    print(f"  Files found: {Colors.CYAN}{result.file_count:,}{Colors.ENDC}")
    print(f"  Total size:  {Colors.GREEN}{result.total_size_formatted}{Colors.ENDC}")

    if result.errors:
        print(f"  {Colors.RED}Errors: {len(result.errors)}{Colors.ENDC}")

    if show_files and result.files:
        print(f"\n  {Colors.DIM}Top files:{Colors.ENDC}")
        sorted_files = sorted(result.files, key=lambda f: f.size, reverse=True)
        for i, file in enumerate(sorted_files[:max_files]):
            print(f"    {Colors.DIM}{format_size(file.size):>10}{Colors.ENDC}  {file.path}")
        if len(result.files) > max_files:
            print(f"    {Colors.DIM}... and {len(result.files) - max_files} more files{Colors.ENDC}")


def interactive_menu(scanner: MacCleanupScanner, cleaner: MacCleaner):
    """Run the interactive cleanup menu."""
    print_header("Mac Cleanup App")

    # Show disk usage
    disk_info = scanner.get_disk_usage()
    if "error" not in disk_info:
        print(f"Disk Usage: {disk_info['used_formatted']} / {disk_info['total_formatted']} "
              f"({disk_info['percent_used']:.1f}% used)")
        print(f"Free Space: {Colors.GREEN}{disk_info['free_formatted']}{Colors.ENDC}")

    while True:
        print_section("Main Menu")
        print("1. Quick Scan (all categories)")
        print("2. Scan specific category")
        print("3. Find large files")
        print("4. Find duplicate files")
        print("5. Find junk files")
        print("6. Clean package manager caches (brew, npm, pip)")
        print("7. Empty Trash")
        print("8. Run full cleanup")
        print("0. Exit")

        try:
            choice = input(f"\n{Colors.CYAN}Enter choice [0-8]: {Colors.ENDC}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n")
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
            junk_scan(scanner, cleaner)

        elif choice == '6':
            clean_package_managers(cleaner)

        elif choice == '7':
            empty_trash(cleaner)

        elif choice == '8':
            full_cleanup(scanner, cleaner)

        else:
            print_warning("Invalid choice. Please try again.")


def quick_scan(scanner: MacCleanupScanner, cleaner: MacCleaner):
    """Perform a quick scan of all categories."""
    print_section("Quick Scan")
    print_info("Scanning all cleanup categories...")

    results = {}
    total_size = 0

    for key, category in CLEANUP_CATEGORIES.items():
        print(f"  Scanning {category.name}...", end='', flush=True)
        result = scanner.scan_category(key)
        results[key] = result
        total_size += result.total_size
        print(f" {result.total_size_formatted}")

    print_section("Scan Results")
    print(f"Total reclaimable space: {Colors.GREEN}{Colors.BOLD}{format_size(total_size)}{Colors.ENDC}")

    # Show breakdown
    sorted_results = sorted(results.items(), key=lambda x: x[1].total_size, reverse=True)
    print("\nBreakdown by category:")
    for key, result in sorted_results:
        if result.total_size > 0:
            percent = (result.total_size / total_size * 100) if total_size > 0 else 0
            bar_len = int(percent / 5)
            bar = '=' * bar_len
            print(f"  {result.total_size_formatted:>10}  {bar:<20} {result.category}")

    # Ask to clean
    if total_size > 0:
        if confirm_action("\nWould you like to clean these files?"):
            for key, result in sorted_results:
                if result.total_size > 0:
                    category = CLEANUP_CATEGORIES[key]
                    if not category.safe_to_delete:
                        if not confirm_action(f"  Clean {category.name}? (requires extra confirmation)"):
                            continue
                    print(f"  Cleaning {category.name}...")
                    cleanup_result = cleaner.clean_scan_result(result, show_progress)
                    print()
                    print_success(f"  Freed {cleanup_result.bytes_freed_formatted}")


def category_scan(scanner: MacCleanupScanner, cleaner: MacCleaner):
    """Scan a specific category."""
    print_section("Category Selection")

    categories = list(CLEANUP_CATEGORIES.items())
    for i, (key, cat) in enumerate(categories, 1):
        print(f"  {i}. {cat.name}")
        print(f"     {Colors.DIM}{cat.description}{Colors.ENDC}")

    try:
        choice = int(input(f"\n{Colors.CYAN}Select category [1-{len(categories)}]: {Colors.ENDC}")) - 1
        if 0 <= choice < len(categories):
            key, category = categories[choice]
            print_info(f"Scanning {category.name}...")

            result = scanner.scan_category(key)
            print_scan_result(result, show_files=True)

            if result.files and confirm_action("\nClean these files?"):
                cleanup_result = cleaner.clean_scan_result(result, show_progress)
                print()
                print_success(f"Freed {cleanup_result.bytes_freed_formatted}")
        else:
            print_warning("Invalid selection")
    except (ValueError, KeyboardInterrupt, EOFError):
        print()


def large_file_scan(scanner: MacCleanupScanner, cleaner: MacCleaner):
    """Find and optionally remove large files."""
    print_section("Large File Finder")

    try:
        threshold = input(f"{Colors.CYAN}Minimum file size in MB [100]: {Colors.ENDC}").strip()
        threshold = float(threshold) if threshold else 100

        path = input(f"{Colors.CYAN}Path to scan [{HOME}]: {Colors.ENDC}").strip()
        path = Path(path) if path else HOME
    except (KeyboardInterrupt, EOFError):
        print()
        return

    print_info(f"Scanning for files larger than {threshold} MB...")
    result = scanner.scan_large_files(path, threshold)
    print_scan_result(result, show_files=True, max_files=20)

    if result.files:
        print_warning("\nBe careful when deleting large files!")
        print_info("Review the list above before proceeding.")

        # Let user select specific files to delete
        if confirm_action("Would you like to review and delete specific files?"):
            for i, file in enumerate(result.files[:20], 1):
                if confirm_action(f"  Delete {file.path} ({file.size_formatted})?"):
                    cleanup_result = cleaner.clean_files([file])
                    if cleanup_result.success:
                        print_success(f"    Deleted, freed {cleanup_result.bytes_freed_formatted}")
                    else:
                        print_error(f"    Failed to delete")


def duplicate_scan(scanner: MacCleanupScanner):
    """Find duplicate files."""
    print_section("Duplicate File Finder")

    try:
        path = input(f"{Colors.CYAN}Path to scan [{HOME}]: {Colors.ENDC}").strip()
        path = Path(path) if path else HOME

        min_size = input(f"{Colors.CYAN}Minimum file size in MB [1]: {Colors.ENDC}").strip()
        min_size = float(min_size) if min_size else 1.0
    except (KeyboardInterrupt, EOFError):
        print()
        return

    print_info(f"Scanning for duplicate files (this may take a while)...")
    duplicates = scanner.scan_duplicates(path, min_size)

    if not duplicates:
        print_success("No duplicate files found!")
        return

    total_waste = 0
    print(f"\nFound {len(duplicates)} sets of duplicate files:\n")

    for i, (hash_val, files) in enumerate(list(duplicates.items())[:10], 1):
        print(f"{Colors.BOLD}Duplicate set {i}:{Colors.ENDC}")
        for f in files:
            print(f"  {f.size_formatted:>10}  {f.path}")
        # Calculate wasted space (all but one copy)
        waste = sum(f.size for f in files[1:])
        total_waste += waste
        print(f"  {Colors.DIM}Potential savings: {format_size(waste)}{Colors.ENDC}\n")

    print(f"\n{Colors.GREEN}Total potential savings: {format_size(total_waste)}{Colors.ENDC}")
    print_warning("Manual review recommended before deleting duplicates.")


def junk_scan(scanner: MacCleanupScanner, cleaner: MacCleaner):
    """Find and clean junk files."""
    print_section("Junk File Scanner")

    try:
        path = input(f"{Colors.CYAN}Path to scan [{HOME}]: {Colors.ENDC}").strip()
        path = Path(path) if path else HOME
    except (KeyboardInterrupt, EOFError):
        print()
        return

    print_info("Scanning for junk files (.DS_Store, .pyc, temp files, etc.)...")
    result = scanner.scan_junk_files(path)
    print_scan_result(result, show_files=True)

    if result.files and confirm_action("\nClean these junk files?"):
        cleanup_result = cleaner.clean_scan_result(result, show_progress)
        print()
        print_success(f"Freed {cleanup_result.bytes_freed_formatted}")


def clean_package_managers(cleaner: MacCleaner):
    """Clean package manager caches."""
    print_section("Package Manager Cleanup")

    cleaners = [
        ("Homebrew", cleaner.clean_brew_cache),
        ("NPM", cleaner.clean_npm_cache),
        ("Pip", cleaner.clean_pip_cache),
        ("Docker", cleaner.clean_docker),
    ]

    for name, clean_func in cleaners:
        if confirm_action(f"Clean {name} cache?"):
            print_info(f"Cleaning {name}...")
            result = clean_func()
            if result.success:
                print_success(f"{name} cache cleaned")
            else:
                for error in result.errors:
                    print_warning(error)


def empty_trash(cleaner: MacCleaner):
    """Empty the Trash."""
    print_section("Empty Trash")

    if confirm_action("Are you sure you want to empty the Trash? This cannot be undone."):
        print_info("Emptying Trash...")
        result = cleaner.empty_trash()
        if result.success:
            print_success("Trash emptied successfully!")
        else:
            for error in result.errors:
                print_error(error)


def full_cleanup(scanner: MacCleanupScanner, cleaner: MacCleaner):
    """Run a full cleanup of all safe categories."""
    print_section("Full Cleanup")
    print_warning("This will clean all safe categories automatically.")

    if not confirm_action("Proceed with full cleanup?"):
        return

    total_freed = 0

    # Clean safe categories
    for key, category in CLEANUP_CATEGORIES.items():
        if category.safe_to_delete:
            print(f"\nCleaning {category.name}...")
            result = scanner.scan_category(key)
            if result.files:
                cleanup = cleaner.clean_scan_result(result, show_progress)
                print()
                total_freed += cleanup.bytes_freed
                print_success(f"  Freed {cleanup.bytes_freed_formatted}")

    # Clean package managers
    print("\nCleaning package managers...")
    cleaner.clean_brew_cache()
    cleaner.clean_npm_cache()
    cleaner.clean_pip_cache()

    print_section("Cleanup Complete")
    print_success(f"Total space freed: {format_size(total_freed)}")


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Mac Cleanup App - Remove junk files and free up disk space",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mac-cleanup                    # Run interactive mode
  mac-cleanup --scan             # Scan all categories
  mac-cleanup --clean            # Clean all safe categories
  mac-cleanup --large-files      # Find large files
  mac-cleanup --duplicates       # Find duplicate files
  mac-cleanup --dry-run --clean  # Preview what would be cleaned
        """
    )

    parser.add_argument('--scan', action='store_true',
                        help='Scan all categories and show results')
    parser.add_argument('--clean', action='store_true',
                        help='Clean all safe categories')
    parser.add_argument('--large-files', action='store_true',
                        help='Find large files')
    parser.add_argument('--duplicates', action='store_true',
                        help='Find duplicate files')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without actually deleting')
    parser.add_argument('--no-trash', action='store_true',
                        help='Permanently delete instead of moving to Trash')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed output')
    parser.add_argument('--no-color', action='store_true',
                        help='Disable colored output')
    parser.add_argument('--path', type=str, default=str(HOME),
                        help='Path to scan (default: home directory)')
    parser.add_argument('--threshold', type=float, default=100,
                        help='Size threshold for large files in MB (default: 100)')

    args = parser.parse_args()

    # Disable colors if requested or not a terminal
    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    # Initialize scanner and cleaner
    scanner = MacCleanupScanner(verbose=args.verbose)
    cleaner = MacCleaner(
        dry_run=args.dry_run,
        verbose=args.verbose,
        move_to_trash=not args.no_trash
    )

    if args.dry_run:
        print_warning("DRY RUN MODE - No files will be deleted")

    # Handle command-line modes
    if args.scan:
        print_header("Scanning All Categories")
        results = scanner.scan_all_categories()
        total = 0
        for key, result in results.items():
            print_scan_result(result)
            total += result.total_size
        print(f"\n{Colors.BOLD}Total reclaimable: {format_size(total)}{Colors.ENDC}")

    elif args.clean:
        print_header("Cleaning All Safe Categories")
        full_cleanup(scanner, cleaner)

    elif args.large_files:
        print_header("Finding Large Files")
        result = scanner.scan_large_files(Path(args.path), args.threshold)
        print_scan_result(result, show_files=True, max_files=30)

    elif args.duplicates:
        print_header("Finding Duplicate Files")
        duplicates = scanner.scan_duplicates(Path(args.path))
        total_waste = 0
        for hash_val, files in list(duplicates.items())[:20]:
            print(f"\nDuplicate set:")
            for f in files:
                print(f"  {f.size_formatted:>10}  {f.path}")
            total_waste += sum(f.size for f in files[1:])
        print(f"\n{Colors.BOLD}Potential savings: {format_size(total_waste)}{Colors.ENDC}")

    else:
        # Run interactive mode
        interactive_menu(scanner, cleaner)


if __name__ == "__main__":
    main()
