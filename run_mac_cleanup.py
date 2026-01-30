#!/usr/bin/env python3
"""
Quick run script for Mac Cleanup App.
Usage: python run_mac_cleanup.py
"""

import sys
from pathlib import Path

# Add the project root to path
sys.path.insert(0, str(Path(__file__).parent))

from mac_cleanup.cli import main

if __name__ == "__main__":
    main()
