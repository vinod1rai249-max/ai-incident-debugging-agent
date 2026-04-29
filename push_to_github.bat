@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  push_to_github.bat
::  Run once from the project root to initialise git and push
::  to GitHub.  Edit GITHUB_URL before running.
:: ============================================================

set "GITHUB_URL=https://github.com/vinod1rai249-max/ai-incident-debugging-agent"
set "BRANCH=main"
set "COMMIT_MSG=Initial commit: AI Production Incident Debugger"

:: ── Colour helpers (requires Windows 10 1511+) ──────────────
for /f %%a in ('echo prompt $E^| cmd /q') do set "ESC=%%a"
set "GREEN=%ESC%[32m"
set "YELLOW=%ESC%[33m"
set "RED=%ESC%[31m"
set "CYAN=%ESC%[36m"
set "RESET=%ESC%[0m"

echo.
echo %CYAN%============================================================%RESET%
echo %CYAN%  GitHub Push Script — AI Incident Debugger%RESET%
echo %CYAN%============================================================%RESET%
echo.

:: ── Preflight: git installed? ────────────────────────────────
where git >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR] git is not installed or not on PATH.%RESET%
    echo        Download from https://git-scm.com/download/win
    goto :fail
)
echo %GREEN%[OK]%RESET%    git found

:: ── Preflight: URL placeholder not replaced? ────────────────
if "%GITHUB_URL%"=="https://github.com/YOUR_USERNAME/YOUR_REPO.git" (
    echo %RED%[ERROR] Replace GITHUB_URL at the top of this script%RESET%
    echo        before running.
    goto :fail
)

:: ── Step 1: Initialise git repo if needed ───────────────────
echo.
echo %YELLOW%[1/6]%RESET% Checking git repository...
if exist ".git\" (
    echo %GREEN%[OK]%RESET%    Git already initialised — skipping
) else (
    git init
    if errorlevel 1 goto :fail
    echo %GREEN%[OK]%RESET%    Git initialised
)

:: ── Step 2: Set default branch to main ──────────────────────
echo.
echo %YELLOW%[2/6]%RESET% Setting default branch to %BRANCH%...
git checkout -b %BRANCH% >nul 2>&1
:: Ignore error — branch may already exist
git branch -M %BRANCH%
if errorlevel 1 goto :fail
echo %GREEN%[OK]%RESET%    Branch set to %BRANCH%

:: ── Step 3: Create .gitignore if missing ────────────────────
echo.
echo %YELLOW%[3/6]%RESET% Checking .gitignore...
if exist ".gitignore" (
    echo %GREEN%[OK]%RESET%    .gitignore already exists — skipping
) else (
    echo Creating .gitignore...
    (
        echo # ── Environment ^& secrets ───────────────────────
        echo .env
        echo .env.*
        echo !.env.example
        echo *.pem
        echo *.key
        echo secrets/
        echo.
        echo # ── Python ───────────────────────────────────────
        echo __pycache__/
        echo *.py[cod]
        echo *.egg-info/
        echo dist/
        echo build/
        echo .venv/
        echo venv/
        echo .Python
        echo pip-log.txt
        echo.
        echo # ── Testing ^& coverage ───────────────────────────
        echo .pytest_cache/
        echo .coverage
        echo htmlcov/
        echo .tox/
        echo.
        echo # ── Type checking / linting ──────────────────────
        echo .mypy_cache/
        echo .ruff_cache/
        echo.
        echo # ── Docker ───────────────────────────────────────
        echo *.log
        echo docker-data/
        echo.
        echo # ── Data ^& ML artifacts ──────────────────────────
        echo data/raw/*
        echo data/processed/*
        echo data/vector_stores/*
        echo !data/raw/.gitkeep
        echo !data/processed/.gitkeep
        echo !data/vector_stores/.gitkeep
        echo *.pkl
        echo *.pt
        echo *.pth
        echo *.onnx
        echo *.safetensors
        echo.
        echo # ── IDE ──────────────────────────────────────────
        echo .vscode/
        echo .idea/
        echo *.swp
        echo.
        echo # ── OS ───────────────────────────────────────────
        echo .DS_Store
        echo Thumbs.db
    ) > .gitignore
    if errorlevel 1 goto :fail
    echo %GREEN%[OK]%RESET%    .gitignore created
)

:: ── Step 4: Stage all files ──────────────────────────────────
echo.
echo %YELLOW%[4/6]%RESET% Staging files...
git add .
if errorlevel 1 goto :fail
echo %GREEN%[OK]%RESET%    Files staged
git status --short

:: ── Step 5: Commit ───────────────────────────────────────────
echo.
echo %YELLOW%[5/6]%RESET% Committing...
git diff --cached --quiet
if not errorlevel 1 (
    echo %YELLOW%[SKIP]%RESET%  Nothing to commit — working tree clean
) else (
    git commit -m "%COMMIT_MSG%"
    if errorlevel 1 goto :fail
    echo %GREEN%[OK]%RESET%    Committed: %COMMIT_MSG%
)

:: ── Step 6: Remote + push ────────────────────────────────────
echo.
echo %YELLOW%[6/6]%RESET% Connecting to GitHub and pushing...

:: Remove stale origin if it points somewhere else
git remote get-url origin >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%u in ('git remote get-url origin') do set "CURRENT_URL=%%u"
    if /i "!CURRENT_URL!" neq "%GITHUB_URL%" (
        echo %YELLOW%[INFO]%RESET%  Updating remote origin: !CURRENT_URL! -> %GITHUB_URL%
        git remote set-url origin "%GITHUB_URL%"
    ) else (
        echo %GREEN%[OK]%RESET%    Remote origin already correct
    )
) else (
    git remote add origin "%GITHUB_URL%"
    if errorlevel 1 goto :fail
    echo %GREEN%[OK]%RESET%    Remote origin added
)

git push -u origin %BRANCH%
if errorlevel 1 (
    echo.
    echo %RED%[ERROR] Push failed.%RESET%
    echo        Common fixes:
    echo          - Authenticate: gh auth login  ^(GitHub CLI^)
    echo          - Or set credential: git config --global credential.helper manager
    echo          - If repo has commits: git pull --rebase origin %BRANCH% then re-run
    goto :fail
)

:: ── Done ─────────────────────────────────────────────────────
echo.
echo %GREEN%============================================================%RESET%
echo %GREEN%  Done! Project pushed to:%RESET%
echo %GREEN%  %GITHUB_URL%%RESET%
echo %GREEN%============================================================%RESET%
echo.
endlocal
exit /b 0

:fail
echo.
echo %RED%[FAILED] Script stopped. Fix the error above and re-run.%RESET%
echo.
endlocal
exit /b 1
