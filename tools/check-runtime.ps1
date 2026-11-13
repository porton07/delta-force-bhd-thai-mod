$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ThaiMenuLoaderCheck {
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern IntPtr LoadLibraryW(string name);
  [DllImport("kernel32.dll")]
  public static extern bool FreeLibrary(IntPtr module);
}
'@
$taskRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -LiteralPath $taskRoot
$taskModules = @('dplayx.dll', 'dpnhpast.dll', 'd3d8.dll', 'dinput8.dll', 'dsound.dll')
foreach ($taskModule in $taskModules) {
    $taskPath = $taskModule
    if (Test-Path -LiteralPath (Join-Path $taskRoot $taskModule)) {
        $taskPath = Join-Path $taskRoot $taskModule
    }
    $taskHandle = [ThaiMenuLoaderCheck]::LoadLibraryW($taskPath)
    $taskError = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    [pscustomobject]@{Module=$taskModule; Loaded=($taskHandle -ne [IntPtr]::Zero); Error=$taskError}
    if ($taskHandle -ne [IntPtr]::Zero) { $null = [ThaiMenuLoaderCheck]::FreeLibrary($taskHandle) }
}
