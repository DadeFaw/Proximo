# Installation unique (Windows) : venv + dépendances + modèle spaCy français.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Write-Host "Création du venv…" -ForegroundColor Cyan
python -m venv (Join-Path $root ".venv")
$py = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "Installation des dépendances…" -ForegroundColor Cyan
& $py -m pip install --upgrade pip
& $py -m pip install -r (Join-Path $root "semantic-api\requirements.txt")
& $py -m pip install -r (Join-Path $root "game-api\requirements.txt")

Write-Host "Téléchargement du modèle spaCy fr_core_news_md (~43 Mo)…" -ForegroundColor Cyan
& $py -m spacy download fr_core_news_md

Write-Host "Pré-construction du cache du lexique…" -ForegroundColor Cyan
Push-Location (Join-Path $root "semantic-api")
$env:PYTHONUTF8 = "1"
& $py -c "from app.engine import load_engine; load_engine()"
Pop-Location

Write-Host "OK. Lancez maintenant : .\run.ps1" -ForegroundColor Green
