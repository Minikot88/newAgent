[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$SourcePath,
    [Parameter(Mandatory)] [string]$HarnessPath,
    [Parameter(Mandatory)] [string]$PolicyPath,
    [Parameter(Mandatory)] [string]$WorkingRoot
)

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
New-Item -ItemType Directory -Path $WorkingRoot -Force | Out-Null
$Provider = New-Object Microsoft.CSharp.CSharpCodeProvider
$Options = New-Object System.CodeDom.Compiler.CompilerParameters
$Options.GenerateExecutable = $true
$Options.GenerateInMemory = $false
$Options.TempFiles = New-Object System.CodeDom.Compiler.TempFileCollection($WorkingRoot, $false)
$Options.CompilerOptions = '/nologo /main:Kimmizo.CodexAuto.AutoModelScopeHarness /platform:anycpu /optimize+'
$Options.ReferencedAssemblies.Add('System.dll') | Out-Null
$Options.ReferencedAssemblies.Add('System.Core.dll') | Out-Null
$Options.ReferencedAssemblies.Add('System.Web.Extensions.dll') | Out-Null
$Result = $Provider.CompileAssemblyFromFile($Options, [string[]]@($SourcePath, $HarnessPath))
if ($Result.Errors.HasErrors) {
    $Result.Errors | ForEach-Object { Write-Error $_.ToString() }
    exit 1
}
& $Result.CompiledAssembly.Location (Join-Path $WorkingRoot 'project') $PolicyPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
