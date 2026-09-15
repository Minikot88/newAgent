[CmdletBinding()]
param(
    [Parameter()]
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Kimmizo\CodexAuto'),

    [Parameter()]
    [switch]$Force,

    [Parameter()]
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$RealCodexPath = Join-Path $InstallRoot 'codex-real.exe'
$CodeModeHostPath = Join-Path $InstallRoot 'codex-code-mode-host.exe'
$InstallRecordPath = Join-Path $InstallRoot 'install.json'
$SyncStatePath = Join-Path $InstallRoot 'runtime-sync.json'

function Read-JsonFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Write-JsonFileAtomic {
    param(
        [string]$Path,
        [object]$Value
    )

    $Temporary = $Path + '.tmp-' + [guid]::NewGuid().ToString('N')
    $Backup = $Path + '.backup-' + [guid]::NewGuid().ToString('N')
    try {
        $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Temporary -Encoding UTF8
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            [IO.File]::Replace($Temporary, $Path, $Backup, $true)
        }
        else {
            [IO.File]::Move($Temporary, $Path)
        }
    }
    finally {
        Remove-Item -LiteralPath $Temporary,$Backup -Force -ErrorAction SilentlyContinue
    }
}

function Write-SyncState {
    param(
        [string]$Status,
        [string]$SourceVersion,
        [string]$CliVersion,
        [string]$Message,
        [string]$UpdatedAt,
        [int]$RuntimeFileCount = 0
    )

    $State = [ordered]@{
        status = $Status
        checkedAt = [DateTime]::UtcNow.ToString('o')
        updatedAt = $UpdatedAt
        sourceVersion = $SourceVersion
        cliVersion = $CliVersion
        runtimeFileCount = $RuntimeFileCount
        message = $Message
    }
    Write-JsonFileAtomic -Path $SyncStatePath -Value $State
    if (-not $Quiet) {
        $State | ConvertTo-Json -Depth 4
    }
}

function Test-RecordedBundle {
    param([object]$Record)

    if (-not $Record -or -not $Record.runtimeFileHashes) {
        return $false
    }
    $Properties = @($Record.runtimeFileHashes.PSObject.Properties)
    if ($Properties.Count -lt 4) {
        return $false
    }
    foreach ($Property in $Properties) {
        $Destination = Join-Path $InstallRoot $Property.Name
        if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
            return $false
        }
        if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ne [string]$Property.Value) {
            return $false
        }
    }
    $ExpectedNames = @($Properties.Name | Sort-Object)
    $ActualNames = @(
        Get-ChildItem -LiteralPath $InstallRoot -File -Filter 'codex-*.exe' |
            Where-Object Name -NotLike 'codex-kimmizo-auto*.exe' |
            Select-Object -ExpandProperty Name |
            Sort-Object
    )
    if (($ExpectedNames -join '|') -ne ($ActualNames -join '|')) {
        return $false
    }
    return $true
}

function Install-StagedFile {
    param(
        [string]$StagedPath,
        [string]$DestinationPath,
        [string]$BackupPath
    )

    if (Test-Path -LiteralPath $DestinationPath -PathType Leaf) {
        [IO.File]::Replace($StagedPath, $DestinationPath, $BackupPath, $true)
    }
    else {
        [IO.File]::Move($StagedPath, $DestinationPath)
    }
}

function Restore-File {
    param(
        [string]$DestinationPath,
        [string]$BackupPath,
        [bool]$HadOriginal
    )

    if ($HadOriginal -and (Test-Path -LiteralPath $BackupPath -PathType Leaf)) {
        if (Test-Path -LiteralPath $DestinationPath -PathType Leaf) {
            $DiscardedPath = $BackupPath + '.discarded'
            try {
                [IO.File]::Replace($BackupPath, $DestinationPath, $DiscardedPath, $true)
            }
            finally {
                Remove-Item -LiteralPath $DiscardedPath -Force -ErrorAction SilentlyContinue
            }
        }
        else {
            [IO.File]::Move($BackupPath, $DestinationPath)
        }
    }
    elseif (-not $HadOriginal) {
        Remove-Item -LiteralPath $DestinationPath -Force -ErrorAction SilentlyContinue
    }
}

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
$LockPath = Join-Path $InstallRoot 'runtime-sync.lock'
$SyncLock = $null
for ($Attempt = 0; $Attempt -lt 90 -and -not $SyncLock; $Attempt++) {
    try {
        $SyncLock = [IO.File]::Open($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    }
    catch [IO.IOException] {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $SyncLock) {
    Write-Error 'Another Kimmizo Auto runtime sync is still running.'
    exit 3
}

$Record = Read-JsonFile -Path $InstallRecordPath
$ExistingSync = Read-JsonFile -Path $SyncStatePath
$PreviousBundleVerified = Test-RecordedBundle -Record $Record
$Package = Get-AppxPackage OpenAI.Codex -ErrorAction SilentlyContinue |
    Sort-Object Version -Descending |
    Select-Object -First 1

if (-not $Package) {
    if ($PreviousBundleVerified) {
        Write-SyncState -Status 'using_verified_previous' -CliVersion ([string]$ExistingSync.cliVersion) -Message 'OpenAI.Codex MSIX package was not found; using the previous verified runtime bundle.' -RuntimeFileCount @($Record.runtimeFileHashes.PSObject.Properties).Count
        exit 0
    }
    Write-SyncState -Status 'failed_integrity' -Message 'OpenAI.Codex MSIX package was not found and no previous verified runtime bundle is available.'
    exit 2
}

$ResourcesPath = Join-Path $Package.InstallLocation 'app\resources'
$SourceVersion = $Package.Version.ToString()

try {
    $RequiredSourceNames = @(
        'codex.exe',
        'codex-code-mode-host.exe',
        'codex-command-runner.exe',
        'codex-windows-sandbox-setup.exe'
    )
    foreach ($RequiredSourceName in $RequiredSourceNames) {
        $RequiredSourcePath = Join-Path $ResourcesPath $RequiredSourceName
        if (-not (Test-Path -LiteralPath $RequiredSourcePath -PathType Leaf)) {
            throw "Required Codex runtime file was not found: $RequiredSourcePath"
        }
    }

    $SourceFiles = @(
        Get-Item -LiteralPath (Join-Path $ResourcesPath 'codex.exe')
        Get-ChildItem -LiteralPath $ResourcesPath -File -Filter 'codex-*.exe' | Sort-Object Name
    )
    $RuntimeSpecs = @()
    foreach ($SourceFile in $SourceFiles) {
        $Signature = Get-AuthenticodeSignature -LiteralPath $SourceFile.FullName
        if ($Signature.Status -ne 'Valid') {
            throw "The installed Codex runtime file signature is not valid ($($SourceFile.Name)): $($Signature.Status)"
        }
        $DestinationName = if ($SourceFile.Name -eq 'codex.exe') { 'codex-real.exe' } else { $SourceFile.Name }
        $DestinationPath = Join-Path $InstallRoot $DestinationName
        $SourceHash = (Get-FileHash -LiteralPath $SourceFile.FullName -Algorithm SHA256).Hash
        $DestinationHash = if (Test-Path -LiteralPath $DestinationPath -PathType Leaf) {
            (Get-FileHash -LiteralPath $DestinationPath -Algorithm SHA256).Hash
        }
        else {
            $null
        }
        $RuntimeSpecs += [pscustomobject]@{
            SourceName = $SourceFile.Name
            SourcePath = $SourceFile.FullName
            DestinationName = $DestinationName
            DestinationPath = $DestinationPath
            SourceHash = $SourceHash
            DestinationHash = $DestinationHash
            NeedsUpdate = $SourceHash -ne $DestinationHash
        }
    }

    $AlreadyCurrent = -not $Force -and $Record -and
        [string]$Record.sourceVersion -eq $SourceVersion -and
        -not ($RuntimeSpecs | Where-Object NeedsUpdate) -and
        (Test-RecordedBundle -Record $Record)

    if ($AlreadyCurrent) {
        $CurrentCliVersion = if ($ExistingSync -and $ExistingSync.cliVersion) {
            [string]$ExistingSync.cliVersion
        }
        else {
            (& $RealCodexPath --version 2>$null) -join ''
        }
        $UpdatedAt = if ($ExistingSync) { [string]$ExistingSync.updatedAt } else { $null }
        Write-SyncState -Status 'current' -SourceVersion $SourceVersion -CliVersion $CurrentCliVersion -UpdatedAt $UpdatedAt -RuntimeFileCount $RuntimeSpecs.Count
        exit 0
    }

    $ChangedSpecs = @($RuntimeSpecs | Where-Object NeedsUpdate)
    $StagedItems = @()
    $ExpectedDestinationNames = @($RuntimeSpecs.DestinationName)
    $ObsoleteItems = @(
        Get-ChildItem -LiteralPath $InstallRoot -File -Filter 'codex-*.exe' |
            Where-Object Name -NotLike 'codex-kimmizo-auto*.exe' |
            Where-Object Name -NotIn $ExpectedDestinationNames |
            ForEach-Object {
                [pscustomobject]@{
                    OriginalPath = $_.FullName
                    BackupPath = Join-Path $InstallRoot ('.obsolete.' + $_.Name + '.' + [guid]::NewGuid().ToString('N'))
                    Moved = $false
                }
            }
    )

    try {
        foreach ($Spec in $ChangedSpecs) {
            $StagedPath = Join-Path $InstallRoot ('.' + $Spec.DestinationName + '.staged.' + [guid]::NewGuid().ToString('N'))
            $BackupPath = Join-Path $InstallRoot ('.' + $Spec.DestinationName + '.backup.' + [guid]::NewGuid().ToString('N'))
            Copy-Item -LiteralPath $Spec.SourcePath -Destination $StagedPath -Force
            if ((Get-FileHash -LiteralPath $StagedPath -Algorithm SHA256).Hash -ne $Spec.SourceHash) {
                throw "Staged Codex runtime file failed SHA256 verification: $($Spec.SourceName)"
            }
            $StagedItems += [pscustomobject]@{
                Spec = $Spec
                StagedPath = $StagedPath
                BackupPath = $BackupPath
                HadOriginal = Test-Path -LiteralPath $Spec.DestinationPath -PathType Leaf
                Installed = $false
            }
        }

        foreach ($Item in $StagedItems) {
            Install-StagedFile -StagedPath $Item.StagedPath -DestinationPath $Item.Spec.DestinationPath -BackupPath $Item.BackupPath
            $Item.Installed = $true
        }

        foreach ($Spec in $RuntimeSpecs) {
            if ((Get-FileHash -LiteralPath $Spec.DestinationPath -Algorithm SHA256).Hash -ne $Spec.SourceHash) {
                throw "Installed Codex runtime file failed SHA256 verification: $($Spec.DestinationName)"
            }
        }
        foreach ($Obsolete in $ObsoleteItems) {
            [IO.File]::Move($Obsolete.OriginalPath, $Obsolete.BackupPath)
            $Obsolete.Moved = $true
        }
        $ActualDestinationNames = @(
            Get-ChildItem -LiteralPath $InstallRoot -File -Filter 'codex-*.exe' |
                Where-Object Name -NotLike 'codex-kimmizo-auto*.exe' |
                Select-Object -ExpandProperty Name |
                Sort-Object
        )
        if ((@($ExpectedDestinationNames | Sort-Object) -join '|') -ne ($ActualDestinationNames -join '|')) {
            throw 'Installed Codex runtime bundle contains an unexpected executable set.'
        }
    }
    catch {
        for ($Index = $ObsoleteItems.Count - 1; $Index -ge 0; $Index--) {
            $Obsolete = $ObsoleteItems[$Index]
            if ($Obsolete.Moved -and (Test-Path -LiteralPath $Obsolete.BackupPath -PathType Leaf)) {
                [IO.File]::Move($Obsolete.BackupPath, $Obsolete.OriginalPath)
            }
        }
        for ($Index = $StagedItems.Count - 1; $Index -ge 0; $Index--) {
            $Item = $StagedItems[$Index]
            if ($Item.Installed) {
                Restore-File -DestinationPath $Item.Spec.DestinationPath -BackupPath $Item.BackupPath -HadOriginal $Item.HadOriginal
            }
        }
        throw
    }
    finally {
        foreach ($Item in $StagedItems) {
            Remove-Item -LiteralPath $Item.StagedPath,$Item.BackupPath -Force -ErrorAction SilentlyContinue
        }
        foreach ($Obsolete in $ObsoleteItems) {
            Remove-Item -LiteralPath $Obsolete.BackupPath -Force -ErrorAction SilentlyContinue
        }
    }

    $CliVersion = (& $RealCodexPath --version 2>$null) -join ''
    if (-not $Record) {
        $Record = [pscustomobject]@{}
    }
    $Record | Add-Member -NotePropertyName source -NotePropertyValue 'OpenAI.Codex MSIX' -Force
    $Record | Add-Member -NotePropertyName sourceVersion -NotePropertyValue $SourceVersion -Force
    $RuntimeFileHashes = [ordered]@{}
    foreach ($Spec in $RuntimeSpecs) {
        $RuntimeFileHashes[$Spec.DestinationName] = $Spec.SourceHash
    }
    $CodexSpec = $RuntimeSpecs | Where-Object DestinationName -eq 'codex-real.exe' | Select-Object -First 1
    $HostSpec = $RuntimeSpecs | Where-Object DestinationName -eq 'codex-code-mode-host.exe' | Select-Object -First 1
    $Record | Add-Member -NotePropertyName sourceSha256 -NotePropertyValue $CodexSpec.SourceHash -Force
    $Record | Add-Member -NotePropertyName codeModeHostSha256 -NotePropertyValue $HostSpec.SourceHash -Force
    $Record | Add-Member -NotePropertyName runtimeFileHashes -NotePropertyValue $RuntimeFileHashes -Force
    $Record | Add-Member -NotePropertyName runtimeFileCount -NotePropertyValue $RuntimeSpecs.Count -Force
    $Record | Add-Member -NotePropertyName autoUpdateEnabled -NotePropertyValue $true -Force
    $Record | Add-Member -NotePropertyName runtimeUpdateDeferred -NotePropertyValue $false -Force
    $Record | Add-Member -NotePropertyName pendingSourceVersion -NotePropertyValue $null -Force
    $Record | Add-Member -NotePropertyName lastRuntimeSyncAt -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    Write-JsonFileAtomic -Path $InstallRecordPath -Value $Record

    $UpdatedAt = [DateTime]::UtcNow.ToString('o')
    Write-SyncState -Status 'updated' -SourceVersion $SourceVersion -CliVersion $CliVersion -UpdatedAt $UpdatedAt -RuntimeFileCount $RuntimeSpecs.Count
    exit 0
}
catch {
    $UpdatedAt = if ($ExistingSync) { [string]$ExistingSync.updatedAt } else { $null }
    if ($PreviousBundleVerified) {
        Write-SyncState -Status 'pending_restart' -SourceVersion $SourceVersion -CliVersion ([string]$ExistingSync.cliVersion) -Message ($_.Exception.Message + ' The previous verified runtime bundle will remain active and the update will retry automatically.') -UpdatedAt $UpdatedAt -RuntimeFileCount @($Record.runtimeFileHashes.PSObject.Properties).Count
        exit 0
    }
    Write-SyncState -Status 'failed_integrity' -SourceVersion $SourceVersion -Message $_.Exception.Message -UpdatedAt $UpdatedAt
    exit 1
}
