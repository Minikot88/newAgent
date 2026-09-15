[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet('Install', 'Status', 'Uninstall')]
    [string]$Action = 'Install',

    [Parameter()]
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Kimmizo\CodexAuto'),

    [Parameter()]
    [switch]$PolicyBundleSelfTest,

    [Parameter()]
    [ValidateRange(0, 60000)]
    [int]$PolicyBundleHoldMilliseconds = 0,

    [Parameter()]
    [switch]$MakeDefault
)

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
$SourcePath = Join-Path $PSScriptRoot 'KimmizoCodexAuto.cs'
$SyncSourcePath = Join-Path $PSScriptRoot 'Sync-KimmizoCodexRuntime.ps1'
$PolicySourcePath = Join-Path $PSScriptRoot '..\..\registry\model-policy.json'
$DefaultProxyPath = Join-Path $InstallRoot 'codex-kimmizo-auto.exe'
$ProxyPath = $DefaultProxyPath
$RealCodexPath = Join-Path $InstallRoot 'codex-real.exe'
$CodeModeHostPath = Join-Path $InstallRoot 'codex-code-mode-host.exe'
$CommandRunnerPath = Join-Path $InstallRoot 'codex-command-runner.exe'
$SandboxSetupPath = Join-Path $InstallRoot 'codex-windows-sandbox-setup.exe'
$StatePath = Join-Path $InstallRoot 'state.json'
$InstallRecordPath = Join-Path $InstallRoot 'install.json'
$SyncInstalledPath = Join-Path $InstallRoot 'Sync-KimmizoCodexRuntime.ps1'
$SyncStatePath = Join-Path $InstallRoot 'runtime-sync.json'
$PolicyInstalledPath = Join-Path $InstallRoot 'model-policy.json'
$PolicyHashPath = Join-Path $InstallRoot 'model-policy.sha256'
$GlobalVoiceBootstrapPath = Join-Path $InstallRoot 'voice-bootstrap.json'
$PolicyBundleLockPath = Join-Path $InstallRoot 'policy-bundle.lock'
$WindowsRoot = if ($env:WINDIR) { $env:WINDIR } elseif ($env:SystemRoot) { $env:SystemRoot } else { 'C:\Windows' }

function Get-Sha256 {
    param([Parameter(Mandatory)][string]$Path)

    $ResolvedPath = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    $Stream = [IO.File]::Open($ResolvedPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($Hasher.ComputeHash($Stream))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $Hasher.Dispose()
        $Stream.Dispose()
    }
}

function Test-KimmizoProxyPath {
    param([string]$Path)

    if (-not $Path) { return $false }
    $ResolvedRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\') + '\'
    $ResolvedPath = [IO.Path]::GetFullPath($Path)
    return $ResolvedPath.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase) -and
        ([IO.Path]::GetFileName($ResolvedPath) -like 'codex-kimmizo-auto*.exe')
}

function Test-ProcessUsingPath {
    param([string]$Path)

    if (-not $Path) { return $false }
    $ResolvedPath = [IO.Path]::GetFullPath($Path)
    foreach ($Process in (Get-Process -ErrorAction SilentlyContinue)) {
        try {
            if ($Process.Path -and [string]::Equals([IO.Path]::GetFullPath($Process.Path), $ResolvedPath, [StringComparison]::OrdinalIgnoreCase)) {
                return $true
            }
        }
        catch {
            continue
        }
    }
    return $false
}

$ConfiguredCliPath = [Environment]::GetEnvironmentVariable('CODEX_CLI_PATH', 'User')
if (Test-KimmizoProxyPath $ConfiguredCliPath) {
    $ProxyPath = $ConfiguredCliPath
}

function Send-EnvironmentChanged {
    if (-not ('Kimmizo.EnvironmentBroadcast' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Kimmizo {
    public static class EnvironmentBroadcast {
        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        private static extern IntPtr SendMessageTimeout(
            IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam,
            uint flags, uint timeout, out UIntPtr result);
        public static void Notify() {
            UIntPtr result;
            SendMessageTimeout(new IntPtr(0xffff), 0x001A, UIntPtr.Zero, "Environment", 2, 5000, out result);
        }
    }
}
'@
    }
    [Kimmizo.EnvironmentBroadcast]::Notify()
}

function Get-CodexRuntime {
    $Package = Get-AppxPackage OpenAI.Codex -ErrorAction SilentlyContinue |
        Sort-Object Version -Descending |
        Select-Object -First 1
    if ($Package) {
        $Candidate = Join-Path $Package.InstallLocation 'app\resources\codex.exe'
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return [pscustomobject]@{
                Path = $Candidate
                Source = 'OpenAI.Codex MSIX'
                Version = $Package.Version.ToString()
            }
        }
    }

    $PluginRuntime = Join-Path $HOME '.codex\plugins\.plugin-appserver\codex.exe'
    if (Test-Path -LiteralPath $PluginRuntime -PathType Leaf) {
        return [pscustomobject]@{
            Path = $PluginRuntime
            Source = 'Codex plugin app-server'
            Version = (& $PluginRuntime --version 2>$null) -join ''
        }
    }

    $Command = Get-Command codex.exe -ErrorAction SilentlyContinue
    if ($Command -and -not [string]::Equals($Command.Source, $ProxyPath, [StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{
            Path = $Command.Source
            Source = 'PATH'
            Version = (& $Command.Source --version 2>$null) -join ''
        }
    }
    throw 'Codex runtime was not found. Install or update the Codex desktop app, then run setup again.'
}

function Get-CSharpCompiler {
    $Candidates = @(
        (Join-Path $WindowsRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
        (Join-Path $WindowsRoot 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
    )
    $Compiler = $Candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $Compiler) {
        throw '.NET Framework C# compiler is required for the Kimmizo Auto host extension.'
    }
    return $Compiler
}

function Read-InstallRecord {
    if (-not (Test-Path -LiteralPath $InstallRecordPath -PathType Leaf)) {
        return $null
    }
    return Get-Content -LiteralPath $InstallRecordPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Install-RuntimeSyncScriptAtomic {
    $LockPath = Join-Path $InstallRoot 'runtime-sync.lock'
    $TempPath = Join-Path $InstallRoot ('.Sync-KimmizoCodexRuntime.{0}.tmp' -f [Guid]::NewGuid().ToString('N'))
    $BackupPath = Join-Path $InstallRoot ('.Sync-KimmizoCodexRuntime.{0}.bak' -f [Guid]::NewGuid().ToString('N'))
    $LockStream = $null

    try {
        for ($Attempt = 0; $Attempt -lt 90 -and -not $LockStream; $Attempt++) {
            try {
                $LockStream = [IO.File]::Open($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
            }
            catch [IO.IOException] {
                Start-Sleep -Milliseconds 500
            }
        }
        if (-not $LockStream) {
            throw 'Timed out waiting for the Kimmizo runtime sync lock.'
        }

        Copy-Item -LiteralPath $SyncSourcePath -Destination $TempPath -Force
        $SourceHash = Get-Sha256 -Path $SyncSourcePath
        $TempHash = Get-Sha256 -Path $TempPath
        if (-not [string]::Equals($SourceHash, $TempHash, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'The staged Kimmizo runtime sync verifier failed its SHA256 check.'
        }

        if (Test-Path -LiteralPath $SyncInstalledPath -PathType Leaf) {
            [IO.File]::Replace($TempPath, $SyncInstalledPath, $BackupPath, $true)
        }
        else {
            [IO.File]::Move($TempPath, $SyncInstalledPath)
        }

        $InstalledHash = Get-Sha256 -Path $SyncInstalledPath
        if (-not [string]::Equals($SourceHash, $InstalledHash, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'The installed Kimmizo runtime sync verifier failed its SHA256 check.'
        }
    }
    finally {
        if ($LockStream) { $LockStream.Dispose() }
        Remove-Item -LiteralPath $TempPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $BackupPath -Force -ErrorAction SilentlyContinue
    }
}

function Restore-PolicyBundleFile {
    param([object]$Item)

    if ($Item.HadOriginal -and (Test-Path -LiteralPath $Item.BackupPath -PathType Leaf)) {
        if (Test-Path -LiteralPath $Item.DestinationPath -PathType Leaf) {
            $DiscardedPath = $Item.BackupPath + '.discarded'
            try {
                [IO.File]::Replace($Item.BackupPath, $Item.DestinationPath, $DiscardedPath, $true)
            }
            finally {
                Remove-Item -LiteralPath $DiscardedPath -Force -ErrorAction SilentlyContinue
            }
        }
        else {
            [IO.File]::Move($Item.BackupPath, $Item.DestinationPath)
        }
    }
    elseif (-not $Item.HadOriginal -and (Test-Path -LiteralPath $Item.DestinationPath -PathType Leaf)) {
        Remove-Item -LiteralPath $Item.DestinationPath -Force -ErrorAction SilentlyContinue
    }
}

function Install-SharedPolicyAtomic {
    if (-not (Test-Path -LiteralPath $PolicySourcePath -PathType Leaf)) {
        throw "Kimmizo Auto policy source was not found: $PolicySourcePath"
    }
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    $LockStream = $null
    $BundleItems = @()
    try {
        for ($Attempt = 0; $Attempt -lt 90 -and -not $LockStream; $Attempt++) {
            try {
                $LockStream = [IO.File]::Open($PolicyBundleLockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
            }
            catch [IO.IOException] {
                Start-Sleep -Milliseconds 500
            }
        }
        if (-not $LockStream) {
            throw 'Timed out waiting for the Kimmizo policy bundle lock.'
        }
        if ($PolicyBundleHoldMilliseconds -gt 0) {
            Start-Sleep -Milliseconds $PolicyBundleHoldMilliseconds
        }

        $PolicyDocument = Get-Content -LiteralPath $PolicySourcePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $PolicyDocument -or $PolicyDocument.schema_version -ne 3 -or
        [string]$PolicyDocument.policy_version -ne '3.0.0' -or
        [string]$PolicyDocument.usage_policy.mode -ne 'chatgpt_plus_limit_first' -or
        [string]$PolicyDocument.usage_policy.default_model -ne 'gpt-5.6-luna' -or
        [string]$PolicyDocument.usage_policy.default_effort -ne 'low' -or
        $PolicyDocument.usage_policy.automatic_multi_agent -ne $false -or
        $PolicyDocument.usage_policy.fast_mode -ne $false -or
        [string]$PolicyDocument.usage_policy.execution_mode -ne 'serial' -or
        $PolicyDocument.usage_policy.verify_before_escalation -ne $true -or
        -not $PolicyDocument.voice -or
        [string]::IsNullOrWhiteSpace([string]$PolicyDocument.voice.instruction) -or
            [string]::IsNullOrWhiteSpace([string]$PolicyDocument.voice.blocked_message)) {
            throw 'Kimmizo Auto policy schema is invalid.'
        }
        $PolicyHash = Get-Sha256 -Path $PolicySourcePath

        $BundleItems = @(
            [pscustomobject]@{
                Name = 'model-policy.json'
                StagedPath = Join-Path $InstallRoot ('.model-policy.' + [guid]::NewGuid().ToString('N') + '.tmp')
                DestinationPath = $PolicyInstalledPath
                BackupPath = Join-Path $InstallRoot ('.model-policy.' + [guid]::NewGuid().ToString('N') + '.bak')
                HadOriginal = $false
                Committed = $false
            }
            [pscustomobject]@{
                Name = 'model-policy.sha256'
                StagedPath = Join-Path $InstallRoot ('.model-policy-hash.' + [guid]::NewGuid().ToString('N') + '.tmp')
                DestinationPath = $PolicyHashPath
                BackupPath = Join-Path $InstallRoot ('.model-policy-hash.' + [guid]::NewGuid().ToString('N') + '.bak')
                HadOriginal = $false
                Committed = $false
            }
            [pscustomobject]@{
                Name = 'voice-bootstrap.json'
                StagedPath = Join-Path $InstallRoot ('.voice-bootstrap.' + [guid]::NewGuid().ToString('N') + '.tmp')
                DestinationPath = $GlobalVoiceBootstrapPath
                BackupPath = Join-Path $InstallRoot ('.voice-bootstrap.' + [guid]::NewGuid().ToString('N') + '.bak')
                HadOriginal = $false
                Committed = $false
            }
        )

        $PolicyItem = $BundleItems[0]
        $HashItem = $BundleItems[1]
        $VoiceItem = $BundleItems[2]
        Copy-Item -LiteralPath $PolicySourcePath -Destination $PolicyItem.StagedPath -Force
        if ((Get-Sha256 -Path $PolicyItem.StagedPath) -ne $PolicyHash) {
            throw 'The staged Kimmizo Auto policy failed its SHA256 check.'
        }
        [IO.File]::WriteAllText($HashItem.StagedPath, $PolicyHash, (New-Object System.Text.UTF8Encoding($false)))
        $VoiceJson = [ordered]@{
            schemaVersion = [int]$PolicyDocument.schema_version
            policyVersion = [string]$PolicyDocument.policy_version
            policySha256 = $PolicyHash
            trigger = [string]$PolicyDocument.voice.trigger
            pronoun = [string]$PolicyDocument.voice.pronoun
            suffix = [string]$PolicyDocument.voice.suffix
            instruction = [string]$PolicyDocument.voice.instruction
            blockedMessage = [string]$PolicyDocument.voice.blocked_message
        } | ConvertTo-Json -Depth 4
        [IO.File]::WriteAllText($VoiceItem.StagedPath, $VoiceJson, (New-Object System.Text.UTF8Encoding($false)))

        foreach ($Item in $BundleItems) {
            $Item.HadOriginal = Test-Path -LiteralPath $Item.DestinationPath -PathType Leaf
            if ($Item.HadOriginal) {
                [IO.File]::Replace($Item.StagedPath, $Item.DestinationPath, $Item.BackupPath, $true)
            }
            elseif (Test-Path -LiteralPath $Item.DestinationPath) {
                throw "Policy bundle destination is not a file: $($Item.DestinationPath)"
            }
            else {
                [IO.File]::Move($Item.StagedPath, $Item.DestinationPath)
            }
            $Item.Committed = $true
        }

        if ((Get-Sha256 -Path $PolicyInstalledPath) -ne $PolicyHash) {
            throw 'The installed Kimmizo Auto policy failed its SHA256 check.'
        }
        if ((Get-Content -LiteralPath $PolicyHashPath -Raw -Encoding UTF8).Trim() -ne $PolicyHash) {
            throw 'The installed Kimmizo Auto policy hash stamp failed verification.'
        }
        $InstalledVoice = Get-Content -LiteralPath $GlobalVoiceBootstrapPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $InstalledVoice -or [int]$InstalledVoice.schemaVersion -ne [int]$PolicyDocument.schema_version -or
            [string]$InstalledVoice.policyVersion -ne [string]$PolicyDocument.policy_version -or
            [string]$InstalledVoice.policySha256 -ne $PolicyHash) {
            throw 'The installed Kimmizo Auto voice bootstrap manifest failed verification.'
        }
    }
    catch {
        for ($Index = $BundleItems.Count - 1; $Index -ge 0; $Index--) {
            $Item = $BundleItems[$Index]
            if ($Item.Committed) {
                Restore-PolicyBundleFile -Item $Item
            }
        }
        throw
    }
    finally {
        if ($LockStream) { $LockStream.Dispose() }
        foreach ($Item in $BundleItems) {
            Remove-Item -LiteralPath $Item.StagedPath,$Item.BackupPath -Force -ErrorAction SilentlyContinue
        }
    }
    return [pscustomobject]@{
        Version = [string]$PolicyDocument.policy_version
        Sha256 = $PolicyHash
    }
}

if ($PolicyBundleSelfTest) {
    try {
        $Receipt = Install-SharedPolicyAtomic
        [ordered]@{
            status = 'passed'
            policyVersion = [string]$Receipt.Version
            policySha256 = [string]$Receipt.Sha256
        } | ConvertTo-Json -Depth 4
        exit 0
    }
    catch {
        Write-Error ('Policy bundle self-test failed: ' + $_.Exception.Message)
        exit 1
    }
}

function Get-AutoStatus {
    $UserCliPath = [Environment]::GetEnvironmentVariable('CODEX_CLI_PATH', 'User')
    $Enabled = [string]::Equals($UserCliPath, $ProxyPath, [StringComparison]::OrdinalIgnoreCase)
    $Record = Read-InstallRecord
    $RuntimeStatus = $null
    if (Test-Path -LiteralPath $ProxyPath -PathType Leaf) {
        $Raw = (& $ProxyPath --kimmizo-status 2>$null) -join [Environment]::NewLine
        if ($Raw) {
            try {
                $RuntimeStatus = $Raw | ConvertFrom-Json
            }
            catch {
                $RuntimeStatus = $null
            }
        }
    }
    $VoiceStatus = if ($RuntimeStatus -and $RuntimeStatus.voiceBootstrap) { [string]$RuntimeStatus.voiceBootstrap.status } else { 'unverified' }
    $RuntimeReady = $RuntimeStatus -and [string]$RuntimeStatus.status -eq 'ready' -and $VoiceStatus -in @('configured', 'enforced')
    return [ordered]@{
        status = if ($Enabled -and $RuntimeReady) { 'ready' } elseif ($Enabled -and $RuntimeStatus) { 'degraded' } elseif ($Enabled) { 'broken' } else { 'disabled' }
        enabled = $Enabled
        proxyPath = $ProxyPath
        realCodexPresent = Test-Path -LiteralPath $RealCodexPath -PathType Leaf
        codeModeHostPresent = Test-Path -LiteralPath $CodeModeHostPath -PathType Leaf
        commandRunnerPresent = Test-Path -LiteralPath $CommandRunnerPath -PathType Leaf
        sandboxSetupPresent = Test-Path -LiteralPath $SandboxSetupPath -PathType Leaf
        defaultAuto = if ($RuntimeStatus) { [bool]$RuntimeStatus.defaultAuto } else { $false }
        secretaryThreadCount = if ($RuntimeStatus -and $RuntimeStatus.secretaryThreadCount) { [int]$RuntimeStatus.secretaryThreadCount } else { 0 }
        virtualModel = if ($RuntimeStatus) { $RuntimeStatus.virtualModel } else { 'kimmizo-auto' }
        displayName = if ($RuntimeStatus) { $RuntimeStatus.displayName } else { '✦ Auto' }
        storesPrompts = $false
        restartRequired = if ($RuntimeStatus -and $RuntimeStatus.runtimeSync) { [string]$RuntimeStatus.runtimeSync.status -eq 'pending_restart' } else { $false }
        autoUpdateEnabled = if ($RuntimeStatus) { [bool]$RuntimeStatus.autoUpdateEnabled } else { Test-Path -LiteralPath $SyncInstalledPath -PathType Leaf }
        runtimeSync = if ($RuntimeStatus) { $RuntimeStatus.runtimeSync } else { $null }
        policyVersion = if ($RuntimeStatus -and $RuntimeStatus.policyVersion) { [string]$RuntimeStatus.policyVersion } elseif ($Record) { [string]$Record.policyVersion } else { $null }
        policySha256 = if ($RuntimeStatus -and $RuntimeStatus.policySha256) { [string]$RuntimeStatus.policySha256 } elseif ($Record) { [string]$Record.policySha256 } else { $null }
        voiceBootstrap = if ($RuntimeStatus -and $RuntimeStatus.voiceBootstrap) { $RuntimeStatus.voiceBootstrap } else { [ordered]@{ status = 'unverified'; source = $null; policyVersion = $null; policySha256 = $null; verifiedAt = $null; reason = 'Kimmizo Auto proxy status is unavailable.' } }
    }
}

if ($Action -eq 'Status') {
    Get-AutoStatus | ConvertTo-Json -Depth 6
    exit 0
}

if ($Action -eq 'Uninstall') {
    $Record = Read-InstallRecord
    $Current = [Environment]::GetEnvironmentVariable('CODEX_CLI_PATH', 'User')
    if ($Current -and -not (Test-KimmizoProxyPath $Current)) {
        throw "CODEX_CLI_PATH is controlled by another tool and was not changed: $Current"
    }
    $Previous = if ($Record) { [string]$Record.previousCodexCliPath } else { $null }
    [Environment]::SetEnvironmentVariable('CODEX_CLI_PATH', $(if ($Previous) { $Previous } else { $null }), 'User')
    $env:CODEX_CLI_PATH = $Previous
    Send-EnvironmentChanged
    [ordered]@{
        status = 'uninstalled'
        restoredCodexCliPath = $Previous
        installFilesRetained = Test-Path -LiteralPath $InstallRoot
        restartRequired = $true
    } | ConvertTo-Json -Depth 4
    exit 0
}

if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
    throw "Kimmizo Auto source was not found: $SourcePath"
}
if (-not (Test-Path -LiteralPath $SyncSourcePath -PathType Leaf)) {
    throw "Kimmizo Auto runtime sync source was not found: $SyncSourcePath"
}
if (-not (Test-Path -LiteralPath $PolicySourcePath -PathType Leaf)) {
    throw "Kimmizo Auto policy source was not found: $PolicySourcePath"
}

$ExistingUserCliPath = $ConfiguredCliPath
if ($ExistingUserCliPath -and -not (Test-KimmizoProxyPath $ExistingUserCliPath)) {
    throw "CODEX_CLI_PATH is already controlled by another tool: $ExistingUserCliPath"
}

$Runtime = Get-CodexRuntime
$Signature = Get-AuthenticodeSignature -LiteralPath $Runtime.Path
if ($Runtime.Source -eq 'OpenAI.Codex MSIX' -and $Signature.Status -ne 'Valid') {
    throw "The installed Codex runtime signature is not valid: $($Signature.Status)"
}

$Compiler = Get-CSharpCompiler
$Reference = Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'System.Web.Extensions.dll'
if (-not (Test-Path -LiteralPath $Reference -PathType Leaf)) {
    $Reference = Join-Path $WindowsRoot 'Microsoft.NET\Framework64\v4.0.30319\System.Web.Extensions.dll'
}
if (-not (Test-Path -LiteralPath $Reference -PathType Leaf)) {
    throw 'System.Web.Extensions.dll was not found.'
}

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
Install-RuntimeSyncScriptAtomic
$PolicyReceipt = Install-SharedPolicyAtomic
$RuntimeUpdateDeferred =
    (Test-ProcessUsingPath -Path $RealCodexPath) -or
    (Test-ProcessUsingPath -Path $CodeModeHostPath) -or
    (Test-ProcessUsingPath -Path $CommandRunnerPath) -or
    (Test-ProcessUsingPath -Path $SandboxSetupPath)
$ProxyPath = Join-Path $InstallRoot ('codex-kimmizo-auto.' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss') + '.exe')
$TemporaryProxy = Join-Path $InstallRoot ('.codex-kimmizo-auto.' + [guid]::NewGuid().ToString('N') + '.exe')
try {
    & $Compiler /nologo /target:exe /platform:anycpu /optimize+ "/reference:$Reference" "/out:$TemporaryProxy" $SourcePath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $TemporaryProxy -PathType Leaf)) {
        throw "Could not compile the Kimmizo Auto host extension (exit $LASTEXITCODE)."
    }
    Move-Item -LiteralPath $TemporaryProxy -Destination $ProxyPath -Force
}
finally {
    Remove-Item -LiteralPath $TemporaryProxy -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
    [ordered]@{
        defaultAuto = $true
        autoThreads = @()
        secretaryThreads = @()
        ultraApprovalThreads = @()
        lastRoutes = @{}
        voiceBootstrap = [ordered]@{
            status = 'unverified'
            source = $null
            policyVersion = $null
            policySha256 = $null
            verifiedAt = $null
            reason = 'Voice bootstrap has not been verified yet.'
        }
    } | ConvertTo-Json -Depth 5 -Compress | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

$ExistingRecord = Read-InstallRecord
$PreviousCliPath = if ($ExistingRecord) { [string]$ExistingRecord.previousCodexCliPath } else { $ExistingUserCliPath }
$RecordedSource = if ($RuntimeUpdateDeferred -and $ExistingRecord) { [string]$ExistingRecord.source } else { $Runtime.Source }
$RecordedSourceVersion = if ($RuntimeUpdateDeferred -and $ExistingRecord) { [string]$ExistingRecord.sourceVersion } elseif ($RuntimeUpdateDeferred) { 'unknown' } else { $Runtime.Version }
$RecordedSourceHash = if ($ExistingRecord) { [string]$ExistingRecord.sourceSha256 } else { $null }
[ordered]@{
    schemaVersion = 1
    installedAt = [DateTime]::UtcNow.ToString('o')
    source = $RecordedSource
    sourceVersion = $RecordedSourceVersion
    sourceSha256 = $RecordedSourceHash
    proxySha256 = Get-Sha256 -Path $ProxyPath
    codeModeHostSha256 = if ($ExistingRecord) { [string]$ExistingRecord.codeModeHostSha256 } else { $null }
    previousCodexCliPath = $PreviousCliPath
    promptStorage = $false
    autoUpdateEnabled = $true
    runtimeUpdateDeferred = $RuntimeUpdateDeferred
    pendingSourceVersion = if ($RuntimeUpdateDeferred) { $Runtime.Version } else { $null }
    runtimeSyncScriptSha256 = Get-Sha256 -Path $SyncInstalledPath
    policyVersion = [string]$PolicyReceipt.Version
    policySha256 = [string]$PolicyReceipt.Sha256
    runtimeFileHashes = if ($ExistingRecord -and $ExistingRecord.runtimeFileHashes) { $ExistingRecord.runtimeFileHashes } else { $null }
    runtimeFileCount = if ($ExistingRecord -and $ExistingRecord.runtimeFileCount) { [int]$ExistingRecord.runtimeFileCount } else { 0 }
    lastRuntimeSyncAt = if ($ExistingRecord -and $ExistingRecord.lastRuntimeSyncAt) { [string]$ExistingRecord.lastRuntimeSyncAt } else { $null }
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $InstallRecordPath -Encoding UTF8

if ($RuntimeUpdateDeferred) {
    [ordered]@{
        status = 'pending_restart'
        checkedAt = [DateTime]::UtcNow.ToString('o')
        updatedAt = $null
        sourceVersion = $Runtime.Version
        cliVersion = (& $RealCodexPath --version 2>$null) -join ''
        message = 'The current Codex runtime is in use. The signed update will be applied automatically at the next proxy start.'
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $SyncStatePath -Encoding UTF8
}
& $SyncInstalledPath -InstallRoot $InstallRoot -Quiet
if ($LASTEXITCODE -ne 0) {
    throw "Kimmizo Auto runtime sync initialization failed with exit code $LASTEXITCODE"
}
foreach ($RequiredRuntimePath in @($RealCodexPath, $CodeModeHostPath, $CommandRunnerPath, $SandboxSetupPath)) {
    if (-not (Test-Path -LiteralPath $RequiredRuntimePath -PathType Leaf)) {
        throw "Kimmizo Auto runtime bundle is incomplete after sync: $RequiredRuntimePath"
    }
}

if ($MakeDefault) {
    & $ProxyPath --kimmizo-default-auto-on | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Kimmizo Auto could not become the default model (exit $LASTEXITCODE)."
    }
}

$SelfTest = (& $ProxyPath --kimmizo-self-test 2>&1) -join [Environment]::NewLine
if ($LASTEXITCODE -ne 0) {
    throw "Kimmizo Auto self-test failed: $SelfTest"
}
$SelfTestResult = $SelfTest | ConvertFrom-Json
if (
    $SelfTestResult.status -ne 'passed' -or
    $SelfTestResult.storesPrompts -or
    $SelfTestResult.fast.model -ne 'gpt-5.6-luna' -or
    $SelfTestResult.fast.effort -ne 'low' -or
    $SelfTestResult.balanced.model -ne 'gpt-5.6-luna' -or
    $SelfTestResult.balanced.effort -ne 'medium' -or
    $SelfTestResult.deep.model -ne 'gpt-5.6-terra' -or
    $SelfTestResult.deep.effort -ne 'high' -or
    $SelfTestResult.critical.model -ne 'gpt-5.6-sol' -or
    $SelfTestResult.critical.effort -ne 'high' -or
    $SelfTestResult.ultraApproval.requiresUltraApproval -ne $true -or
    $SelfTestResult.ultraApproval.effort -ne 'high' -or
    $SelfTestResult.ultraApproved.effort -ne 'ultra' -or
    $SelfTestResult.phaseKeepsModel.model -ne 'gpt-5.6-luna' -or
    $SelfTestResult.phaseKeepsModel.effort -ne 'medium' -or
    $SelfTestResult.phaseUpgrade.model -ne 'gpt-5.6-terra' -or
    $SelfTestResult.phaseUpgrade.effort -ne 'high' -or
    $SelfTestResult.phaseCriticalUpgrade.model -ne 'gpt-5.6-sol' -or
    $SelfTestResult.phaseCriticalUpgrade.effort -ne 'high' -or
    $SelfTestResult.phaseReset.model -ne 'gpt-5.6-luna' -or
    $SelfTestResult.phaseReset.effort -ne 'low' -or
    $SelfTestResult.policyVersion -ne $PolicyReceipt.Version -or
    $SelfTestResult.policySha256 -ne $PolicyReceipt.Sha256 -or
    $SelfTestResult.voiceBootstrap.status -notin @('configured', 'enforced')
) {
    throw 'Kimmizo Auto self-test returned an unsafe or invalid result.'
}

[Environment]::SetEnvironmentVariable('CODEX_CLI_PATH', $ProxyPath, 'User')
$env:CODEX_CLI_PATH = $ProxyPath
Send-EnvironmentChanged

$Status = Get-AutoStatus
$Status.restartRequired = $true
$Status.runtimeSource = $Runtime.Source
$Status.runtimeVersion = $Runtime.Version
$Status.selfTest = $SelfTestResult
$Status | ConvertTo-Json -Depth 8
