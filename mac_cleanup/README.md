# Mac Cleanup App

A powerful command-line utility to find and remove junk files, caches, and unwanted data from your Mac.

## Features

- **Category-based Cleanup**: Clean specific categories like browser caches, system caches, logs, etc.
- **Large File Finder**: Find files above a certain size threshold
- **Duplicate Detector**: Find duplicate files based on content hash
- **Junk File Scanner**: Find .DS_Store, .pyc, temp files, and more
- **Package Manager Cleanup**: Clean Homebrew, NPM, Pip, and Docker caches
- **Safe by Default**: Files are moved to Trash instead of permanently deleted
- **Dry Run Mode**: Preview what would be deleted without making changes
- **Interactive Menu**: Easy-to-use interactive interface

## Cleanup Categories

| Category | Description |
|----------|-------------|
| System Caches | macOS system cache files |
| User Caches | Application cache files |
| Browser Caches | Safari, Chrome, Firefox caches |
| Logs | System and application log files |
| Downloads | Old files in Downloads folder (30+ days) |
| Trash | Files in the Trash |
| Temp Files | Temporary files left by applications |
| Xcode | Derived data, archives, device support |
| iOS Backups | iPhone/iPad backup files |
| Pip Cache | Python package cache |
| NPM Cache | Node.js package cache |
| Homebrew Cache | Homebrew package cache |
| Docker | Docker images and containers |
| Mail Attachments | Downloaded mail attachments |
| .DS_Store | macOS folder metadata files |

## Installation

```bash
# Install from source
pip install -e .

# Or run directly
python -m mac_cleanup
```

## Usage

### Interactive Mode (Recommended)

```bash
mac-cleanup
# or
python -m mac_cleanup
```

### Command-Line Options

```bash
# Scan all categories
mac-cleanup --scan

# Clean all safe categories
mac-cleanup --clean

# Find large files (default: >100MB)
mac-cleanup --large-files
mac-cleanup --large-files --threshold 500  # >500MB

# Find duplicate files
mac-cleanup --duplicates

# Dry run (preview without deleting)
mac-cleanup --dry-run --clean

# Permanently delete instead of Trash
mac-cleanup --no-trash --clean

# Verbose output
mac-cleanup -v --scan

# Scan specific path
mac-cleanup --path /Users/you/Projects --large-files
```

## Safety Features

1. **Dry Run Mode**: Use `--dry-run` to see what would be deleted
2. **Move to Trash**: By default, files go to Trash (recoverable)
3. **Confirmation Prompts**: Dangerous operations require confirmation
4. **Category Safety Flags**: Some categories marked as "requires confirmation"
5. **Skip System Files**: Critical system directories are never touched

## Menu Options

1. **Quick Scan** - Scan all categories and show summary
2. **Scan Category** - Scan a specific cleanup category
3. **Large Files** - Find files above size threshold
4. **Duplicates** - Find duplicate files by content
5. **Junk Files** - Find common junk files
6. **Package Managers** - Clean brew/npm/pip/docker caches
7. **Empty Trash** - Permanently delete Trash contents
8. **Full Cleanup** - Clean all safe categories automatically

## Requirements

- macOS 10.15 or later
- Python 3.8 or later
- No external dependencies (uses standard library only)

## Tips

- Run `mac-cleanup --scan` first to see what can be cleaned
- Use `--dry-run` before any cleanup to preview changes
- Xcode Derived Data can be very large - safe to clean if not actively building
- iOS Backups are important - only clean if you have iCloud backups
- Browser caches rebuild automatically - safe to clean regularly

## License

MIT License
