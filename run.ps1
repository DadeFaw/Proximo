# Lance semantic-api (8100) puis game-api (8000) en local, sous Windows.
# Prérequis : .\setup.ps1 exécuté une fois (venv + dépendances + modèle spaCy).
# Ctrl+C pour arrêter le game-api ; le semantic-api tourne en tâche de fond (job).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "venv introuvable. Lancez d'abord .\setup.ps1" }

$env:PYTHONUTF8 = "1"

Write-Host "Démarrage du semantic-api (8100)…" -ForegroundColor Cyan
$sem = Start-Job -ScriptBlock {
    param($py, $dir)
    $env:PYTHONUTF8 = "1"
    Set-Location $dir
    & $py -m uvicorn app.main:app --host 127.0.0.1 --port 8100
} -ArgumentList $py, (Join-Path $root "semantic-api")

Write-Host "Attente du chargement du moteur sémantique…" -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 120; $i++) {
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:8100/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) { Stop-Job $sem; Remove-Job $sem; throw "semantic-api n'a pas démarré." }
Write-Host "semantic-api prêt." -ForegroundColor Green

# Détecte l'IP LAN pour que les autres joueurs (même Wi-Fi) puissent se connecter,
# et pour que les QR / liens de salon pointent vers une adresse joignable.
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.PrefixOrigin -ne 'WellKnown' -and $_.IPAddress -notlike '169.254.*' } |
    Sort-Object -Property @{ Expression = { $_.InterfaceAlias -like 'Wi-Fi*' } } -Descending |
    Select-Object -First 1).IPAddress
if (-not $lanIp) { $lanIp = '127.0.0.1' }

$env:SEMANTIC_API_URL = "http://127.0.0.1:8100"
# PUBLIC_BASE_URL : forcez-la pour un tunnel/déploiement (ex. https://xxx.trycloudflare.com).
if (-not $env:PUBLIC_BASE_URL) { $env:PUBLIC_BASE_URL = "http://${lanIp}:8000" }

Write-Host ""
Write-Host "  game-api prêt. Adresses à partager aux joueurs :" -ForegroundColor Green
Write-Host "    ce PC        : http://127.0.0.1:8000"
Write-Host "    même Wi-Fi   : http://${lanIp}:8000   (+ QR dans le lobby)" -ForegroundColor Cyan
Write-Host "    à distance   : lancez un tunnel, ex. cloudflared tunnel --url http://localhost:8000"
Write-Host "  (Autorisez le port 8000 si le pare-feu Windows le demande.)" -ForegroundColor Yellow
Write-Host ""
try {
    Set-Location (Join-Path $root "game-api")
    # 0.0.0.0 = écoute sur toutes les interfaces (accessible depuis le réseau local).
    & $py -m uvicorn app.main:app --host 0.0.0.0 --port 8000
} finally {
    Write-Host "Arrêt du semantic-api…" -ForegroundColor Yellow
    Stop-Job $sem -ErrorAction SilentlyContinue
    Remove-Job $sem -ErrorAction SilentlyContinue
    Set-Location $root
}
