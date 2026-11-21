#!/usr/bin/env python3
"""Convenience root wrapper for backend/toggle_verification.py."""
import importlib.util
import sys
from pathlib import Path

backend_file = Path(__file__).resolve().parent / "backend" / "toggle_verification.py"
spec = importlib.util.spec_from_file_location("backend_toggle_verification", backend_file)
mod = importlib.util.module_from_spec(spec)
sys.modules["backend_toggle_verification"] = mod
spec.loader.exec_module(mod)

if __name__ == "__main__":
    mod.main()
