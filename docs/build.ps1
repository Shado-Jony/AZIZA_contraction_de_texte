# Script de compilation du mémoire AZIZA
# Usage : .\build.ps1

Write-Host "=== Compilation du mémoire AZIZA ===" -ForegroundColor Cyan

$name = "these"
$ErrorActionPreference = "Continue"

Write-Host "[1/4] xelatex (première passe)..." -ForegroundColor Yellow
xelatex -synctex=1 -interaction=nonstopmode -file-line-error $name

Write-Host "[2/4] biber (bibliographie)..." -ForegroundColor Yellow
biber $name

Write-Host "[3/4] xelatex (deuxième passe)..." -ForegroundColor Yellow
xelatex -synctex=1 -interaction=nonstopmode -file-line-error $name

Write-Host "[4/4] xelatex (troisième passe, finalisation)..." -ForegroundColor Yellow
xelatex -synctex=1 -interaction=nonstopmode -file-line-error $name

# Nettoyage
$extensions = @("aux","bbl","bcf","blg","idx","ind","lof","lot","out","run.xml","synctex.gz","toc","log")
foreach ($ext in $extensions) {
    $file = "$name.$ext"
    if (Test-Path $file) { Remove-Item $file -Force }
}
# Nettoyage des .aux dans pages/
Get-ChildItem pages\*.aux -ErrorAction SilentlyContinue | Remove-Item -Force

if (Test-Path "$name.pdf") {
    Write-Host "=== OK : $name.pdf généré ===" -ForegroundColor Green
} else {
    Write-Host "=== ERREUR : fichier PDF non trouvé ===" -ForegroundColor Red
}
