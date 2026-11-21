#!/usr/bin/env python3
"""Convenience root wrapper for backend/create_admin.py.

Usage:
    python create_admin.py
    python create_admin.py --email admin@researchmate.com --password "Admin@ResearchMate2026"
"""
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from create_admin import main

if __name__ == "__main__":
    main()
