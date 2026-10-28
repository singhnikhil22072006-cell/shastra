# Run from the project root:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"

# Backend
Set-Location "$PSScriptRoot\backend"
py -3.12 -m venv .venv   # use 3.11 or 3.12 (ONNX Runtime wheels)
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

# Frontend
Set-Location "$PSScriptRoot\frontend"
npm install
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

Write-Host "`nDone. Fill in backend\.env and frontend\.env, run supabase\schema.sql in Supabase, then start both servers (see README.md)."
