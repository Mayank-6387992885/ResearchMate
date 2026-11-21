@echo off
echo ========================================================
echo   ResearchMate - Local Environment Launcher
echo ========================================================
echo.
echo   [1] Full Local: Backend (Supabase) + Frontend
echo   [2] Full Local: Backend (SQLite) + Frontend
echo   [3] Hybrid: Frontend connected to Render Cloud API
echo   [4] Backend Only (Supabase)
echo   [5] Backend Only (Local SQLite)
echo   [6] Frontend Only (Local API :8000)
echo   [0] Exit
echo.
set /p choice="Enter choice [1-6, 0]: "

if "%choice%"=="1" (
    python run_local.py --all
) else if "%choice%"=="2" (
    python run_local.py --all --sqlite
) else if "%choice%"=="3" (
    python run_local.py --frontend-cloud
) else if "%choice%"=="4" (
    python run_local.py --backend
) else if "%choice%"=="5" (
    python run_local.py --backend-sqlite
) else if "%choice%"=="6" (
    python run_local.py --frontend
) else (
    echo Exiting.
)
pause
