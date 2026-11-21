#!/usr/bin/env python3
"""ResearchMate Local & Cloud Launcher.

Run ResearchMate easily in both environments:
1. Full Local Mode: Local FastAPI backend (localhost:8000) + Local Vite frontend (localhost:5173)
2. Hybrid Mode: Local Vite frontend (localhost:5173) connected to Render Cloud API + Supabase
3. Pure SQLite Mode: Local backend with local SQLite (no internet / Supabase needed)

Usage:
    python run_local.py                     # Interactive menu
    python run_local.py --all               # Start both local backend and local frontend
    python run_local.py --backend           # Start local backend only (Supabase / env DB)
    python run_local.py --backend-sqlite    # Start local backend only (Local SQLite)
    python run_local.py --frontend          # Start frontend connected to local backend
    python run_local.py --frontend-cloud    # Start frontend connected to Render cloud API
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"


def run_backend(use_sqlite: bool = False):
    """Run local FastAPI backend with Uvicorn."""
    print("=" * 60)
    db_desc = "Local SQLite (researchmate.db)" if use_sqlite else "Supabase PostgreSQL (from .env)"
    print(f" Starting ResearchMate Backend on http://localhost:8000")
    print(f" Database: {db_desc}")
    print("=" * 60)
    env = os.environ.copy()
    if use_sqlite:
        env["USE_SQLITE"] = "true"
    env["PYTHONPATH"] = str(BACKEND_DIR)

    cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"]
    subprocess.run(cmd, cwd=str(BACKEND_DIR), env=env)


def run_frontend(target: str = "local"):
    """Run Vite frontend in local or cloud mode."""
    print("=" * 60)
    if target == "render":
        print(" Starting ResearchMate Frontend in CLOUD mode")
        print(" Target API: https://researchmate-api-0e78.onrender.com")
        cmd = ["npm", "run", "dev:render"]
    else:
        print(" Starting ResearchMate Frontend in LOCAL mode")
        print(" Target API: http://localhost:8000")
        cmd = ["npm", "run", "dev:local"]
    print("=" * 60)

    # Use shell=True on Windows for npm
    is_win = sys.platform == "win32"
    subprocess.run(cmd, cwd=str(FRONTEND_DIR), shell=is_win)


def run_all(use_sqlite: bool = False):
    """Run both local backend and local frontend concurrently."""
    print("=" * 60)
    db_desc = "Local SQLite" if use_sqlite else "Supabase PostgreSQL"
    print(f" Starting ResearchMate Full Stack locally ({db_desc})")
    print(" Backend:  http://localhost:8000")
    print(" Frontend: http://localhost:5173")
    print("=" * 60)

    env = os.environ.copy()
    if use_sqlite:
        env["USE_SQLITE"] = "true"
    env["PYTHONPATH"] = str(BACKEND_DIR)

    is_win = sys.platform == "win32"
    backend_cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"]
    frontend_cmd = ["npm", "run", "dev:local"]

    backend_proc = subprocess.Popen(backend_cmd, cwd=str(BACKEND_DIR), env=env)
    time.sleep(1.5)
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=str(FRONTEND_DIR), shell=is_win)

    try:
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping ResearchMate processes...")
    finally:
        for proc in [frontend_proc, backend_proc]:
            try:
                proc.terminate()
            except Exception:
                pass


def interactive_menu():
    """Display an interactive terminal menu."""
    print("\n" + "=" * 60)
    print("  RESEARCHMATE - Local & Cloud Environment Launcher")
    print("=" * 60)
    print("  [1] Full Local: Start Local Backend (Supabase) + Local Frontend")
    print("  [2] Full Local: Start Local Backend (SQLite) + Local Frontend")
    print("  [3] Hybrid:     Start Local Frontend connected to Render Cloud API")
    print("  [4] Backend:    Start Local Backend only (Supabase PostgreSQL)")
    print("  [5] Backend:    Start Local Backend only (Local SQLite)")
    print("  [6] Frontend:   Start Local Frontend only (Local API :8000)")
    print("  [0] Exit")
    print("=" * 60)

    choice = input("Enter choice [1-6, 0]: ").strip()
    if choice == "1":
        run_all(use_sqlite=False)
    elif choice == "2":
        run_all(use_sqlite=True)
    elif choice == "3":
        run_frontend(target="render")
    elif choice == "4":
        run_backend(use_sqlite=False)
    elif choice == "5":
        run_backend(use_sqlite=True)
    elif choice == "6":
        run_frontend(target="local")
    else:
        print("Exiting.")


def main():
    parser = argparse.ArgumentParser(description="ResearchMate Local & Cloud Launcher")
    parser.add_argument("--all", action="store_true", help="Start both local backend and local frontend")
    parser.add_argument("--sqlite", action="store_true", help="Use local SQLite database instead of Supabase")
    parser.add_argument("--backend", action="store_true", help="Start local backend only")
    parser.add_argument("--backend-sqlite", action="store_true", help="Start local backend with local SQLite")
    parser.add_argument("--frontend", action="store_true", help="Start local frontend connected to local API")
    parser.add_argument("--frontend-cloud", action="store_true", help="Start local frontend connected to Render Cloud API")

    args = parser.parse_args()

    if args.all:
        run_all(use_sqlite=args.sqlite)
    elif args.backend_sqlite:
        run_backend(use_sqlite=True)
    elif args.backend:
        run_backend(use_sqlite=args.sqlite)
    elif args.frontend_cloud:
        run_frontend(target="render")
    elif args.frontend:
        run_frontend(target="local")
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
