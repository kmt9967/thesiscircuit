$ErrorActionPreference = 'Stop'
$ExpectedRoot = 'F:\Hackathon\thesiscircuit'
$ResolvedRoot = (Resolve-Path -LiteralPath $PSScriptRoot\..).Path

if ($ResolvedRoot -ne $ExpectedRoot) {
    throw "Unexpected project root: $ResolvedRoot"
}

$GitRoot = (git -C $ResolvedRoot rev-parse --show-toplevel).Trim().Replace('/', '\')
if ($GitRoot -ne $ExpectedRoot) {
    throw "Unexpected Git root: $GitRoot"
}

$Links = Get-ChildItem -LiteralPath $ResolvedRoot -Recurse -Force -Attributes ReparsePoint -ErrorAction SilentlyContinue
if ($Links) {
    throw "Unexpected junction/symlink found inside project root."
}

Write-Output "Workspace verification passed: $ResolvedRoot"
