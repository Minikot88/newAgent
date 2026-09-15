[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet('setup', 'doctor', 'update', 'repair', 'team-report', 'auto-status', 'auto-uninstall')]
    [string]$Mode = 'setup',

    [Parameter()]
    [string]$Target = (Get-Location).Path,

    [Parameter()]
    [switch]$SkipInstall,

    [Parameter()]
    [switch]$DryRun,

    [Parameter()]
    [switch]$NoPluginRegistration,

    [Parameter()]
    [switch]$NoAutoModel
)

$ErrorActionPreference = 'Stop'
$ScriptPath = Join-Path $PSScriptRoot 'plugins\kimmizo-setup\scripts\kimmizo.py'
$AutoModelInstaller = Join-Path $PSScriptRoot 'plugins\kimmizo-setup\scripts\auto-model\Install-KimmizoCodexAuto.ps1'

if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
    throw "Kimmizo entry point was not found: $ScriptPath"
}

if (-not (Test-Path -LiteralPath $AutoModelInstaller -PathType Leaf)) {
    throw "Kimmizo Auto installer was not found: $AutoModelInstaller"
}

function Invoke-KimmizoAutoModel {
    param(
        [Parameter(Mandatory)]
        [ValidateSet('Install', 'Status', 'Uninstall')]
        [string]$Action
    )

    $WindowsHost = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
    if (-not $WindowsHost) {
        if ($Action -eq 'Install') {
            Write-Warning 'Kimmizo Auto currently supports the Codex desktop app on Windows only.'
        }
        return
    }
    & $AutoModelInstaller -Action $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Kimmizo Auto $Action failed with exit code $LASTEXITCODE"
    }
}

if ($Mode -eq 'auto-status') {
    Invoke-KimmizoAutoModel -Action Status
    exit 0
}

if ($Mode -eq 'auto-uninstall') {
    Invoke-KimmizoAutoModel -Action Uninstall
    exit 0
}

function Update-ProcessPath {
    $MachinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = @($MachinePath, $UserPath) -join [IO.Path]::PathSeparator
}

function Install-WingetPrerequisite {
    param(
        [Parameter(Mandatory)] [string]$Id,
        [Parameter(Mandatory)] [string]$DisplayName
    )

    $Winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $Winget) {
        throw "$DisplayName is missing and Windows Package Manager (winget) is unavailable. Install it through the Microsoft Store App Installer, then run Kimmizo again."
    }
    & $Winget.Source install --id $Id --exact --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install $DisplayName from the signed winget source (exit $LASTEXITCODE)."
    }
    Update-ProcessPath
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python -and -not $SkipInstall -and -not $DryRun) {
    Install-WingetPrerequisite -Id 'Python.Python.3.13' -DisplayName 'Python 3.13'
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $Python) {
        $Python = Get-Command py -ErrorAction SilentlyContinue
    }
}
if (-not $Python) {
    throw 'Python 3 is required. Run setup without -SkipInstall/-DryRun to let Kimmizo install it, or install Python 3.13 yourself.'
}

if (-not $SkipInstall -and -not $DryRun -and -not (Get-Command git -ErrorAction SilentlyContinue)) {
    Install-WingetPrerequisite -Id 'Git.Git' -DisplayName 'Git'
}

function Invoke-Kimmizo {
    param(
        [Parameter(Mandatory)] [string]$Command,
        [Parameter()] [string[]]$ExtraArguments = @(),
        [Parameter()] [switch]$Capture
    )

    $Arguments = @($ScriptPath, $Command, '--target', $Target, '--json') + $ExtraArguments
    if ($Python.Name -eq 'py.exe' -or $Python.Name -eq 'py') {
        $Arguments = @('-3') + $Arguments
    }
    if ($Capture) {
        $Output = & $Python.Source @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Kimmizo $Command failed with exit code $LASTEXITCODE"
        }
        return ($Output -join [Environment]::NewLine)
    }
    & $Python.Source @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Kimmizo $Command failed with exit code $LASTEXITCODE"
    }
}

if ($Mode -ne 'setup') {
    $Extra = @()
    if ($DryRun -and $Mode -in @('update', 'repair')) {
        $Extra += '--dry-run'
    }
    Invoke-Kimmizo -Command $Mode -ExtraArguments $Extra
    if (-not $NoAutoModel) {
        if ($Mode -in @('update', 'repair') -and -not $DryRun) {
            Invoke-KimmizoAutoModel -Action Install
        }
        elseif ($Mode -eq 'doctor') {
            Invoke-KimmizoAutoModel -Action Status
        }
    }
    exit 0
}

$BootstrapArgs = @('--skip-install')
if ($DryRun) {
    $BootstrapArgs += '--dry-run'
}
$Bootstrap = Invoke-Kimmizo -Command 'setup' -ExtraArguments $BootstrapArgs -Capture

if ($DryRun) {
    $Bootstrap
    exit 0
}

if (-not $NoPluginRegistration) {
        $Codex = Get-Command codex -ErrorAction SilentlyContinue
    if ($Codex) {
        $Override = 'model_reasoning_effort="xhigh"'
        $MarketplaceList = (& $Codex.Source -c $Override plugin marketplace list 2>&1) -join [Environment]::NewLine
        $MarketplaceMatch = [regex]::Match($MarketplaceList, '(?im)^kimmizo\s+(.+?)\s*$')
        if ($MarketplaceMatch.Success) {
            $RegisteredRoot = (Resolve-Path -LiteralPath $MarketplaceMatch.Groups[1].Value.Trim()).Path
            $ExpectedRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
            if (-not [string]::Equals($RegisteredRoot, $ExpectedRoot, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Marketplace name 'kimmizo' is already registered to a different source: $RegisteredRoot"
            }
        }
        else {
            & $Codex.Source -c $Override plugin marketplace add $PSScriptRoot
            if ($LASTEXITCODE -ne 0) {
                throw "Could not register the local Kimmizo marketplace (exit $LASTEXITCODE)."
            }
        }

        $PluginList = (& $Codex.Source -c $Override plugin list 2>&1) -join [Environment]::NewLine
        if ($PluginList -notmatch 'kimmizo-setup@kimmizo') {
            & $Codex.Source -c $Override plugin add 'kimmizo-setup@kimmizo'
            if ($LASTEXITCODE -ne 0) {
                throw "Could not install the Kimmizo Setup plugin (exit $LASTEXITCODE)."
            }
        }
    }
}

if (-not $NoAutoModel) {
    Invoke-KimmizoAutoModel -Action Install
}

if ($SkipInstall) {
    $Bootstrap
    exit 0
}

Invoke-Kimmizo -Command 'setup'
