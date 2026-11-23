<#
.SYNOPSIS
  Rebuild the local site data from a saved Blender project. Add -Publish to push the release to Pages.
.EXAMPLE
  .\release.ps1 -BlendFile ..\Apartment_Wall_Profiles.blend -Publish
#>
[CmdletBinding()]
param(
    [string]$BlendFile = (Join-Path (Split-Path $PSScriptRoot -Parent) 'Apartment_Wall_Profiles.blend'),
    [string]$Blender,
    [string]$Python,
    [string]$Version,
    [switch]$Publish
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $BlendFile).Path

function Find-Application([string[]]$Candidates, [string]$Option) {
    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Executable not found. Pass its path using -$Option."
}

if (!$Blender) {
    $candidates = @((Get-Command blender.exe -ErrorAction SilentlyContinue).Source)
    $candidates += @(Get-Process -Name blender -ErrorAction SilentlyContinue | ForEach-Object { $_.Path })
    $candidates += @(Get-ChildItem "$env:ProgramFiles\Blender Foundation\Blender*\blender.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | ForEach-Object { $_.FullName })
    $candidates += @(Get-PSDrive -PSProvider FileSystem | ForEach-Object { Join-Path $_.Root 'SteamLibrary\steamapps\common\Blender\blender.exe' })
    $Blender = Find-Application $candidates 'Blender'
}
if (!$Python) {
    $runtime = Join-Path (Split-Path (Split-Path $PSHOME -Parent) -Parent) 'python\python.exe'
    $candidates = @((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'), $runtime, (Get-Command python.exe -ErrorAction SilentlyContinue).Source)
    $Python = Find-Application $candidates 'Python'
}
& $Python -c 'import PIL, pypdf, reportlab'
if ($LASTEXITCODE) { throw 'Install Pillow, pypdf and reportlab in the interpreter selected by -Python.' }

if ($Publish) {
    $branch = git -C $PSScriptRoot branch --show-current
    if ($LASTEXITCODE -or $branch -ne 'main') { throw 'Switch to the main branch before publishing.' }
}
$exportArgs = @((Join-Path $PSScriptRoot 'tools/release.py'), '--blend', $project, '--blender', $Blender)
if ($Version) { $exportArgs += @('--version', $Version) }
& $Python @exportArgs
if ($LASTEXITCODE) { throw 'The Blender release failed.' }
$data = Join-Path $PSScriptRoot 'public/data'
$release = Get-Content -Encoding UTF8 -Raw (Join-Path $data 'release.json') | ConvertFrom-Json
$localPdf = Join-Path (Split-Path $project -Parent) 'output/pdf'
[void](New-Item -ItemType Directory -Force -Path $localPdf)
Copy-Item -LiteralPath (Join-Path $data $release.pdf) -Destination (Join-Path $localPdf 'Apartment_Wall_Profiles.pdf')
if ($Publish) {
    git -C $PSScriptRoot add -A -- public/data
    if ($LASTEXITCODE) { throw 'Could not stage the release.' }
    git -C $PSScriptRoot diff --cached --quiet -- public/data
    if ($LASTEXITCODE -eq 1) {
        git -C $PSScriptRoot commit --only -m "Release apartment $($release.version)" -- public/data
        if ($LASTEXITCODE) { throw 'Could not commit the release.' }
    } elseif ($LASTEXITCODE) { throw 'Could not compare release data.' }
    git -C $PSScriptRoot push origin main
    if ($LASTEXITCODE) { throw 'Could not push to GitHub. The release is available locally.' }
}
Write-Host "Release $($release.version) ready."
