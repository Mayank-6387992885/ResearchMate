#!/usr/bin/env python3
"""Convenience root wrapper for backend/toggle_verification.py.

Usage:
    python toggle_verification.py status
    python toggle_verification.py on
    python toggle_verification.py off
    python toggle_verification.py off --verify-all
    python toggle_verification.py toggle
"""
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from toggle_verification import main

if __name__ == "__main__":
    main()
