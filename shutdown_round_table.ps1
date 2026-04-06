param(
    [int]$DelaySeconds = 2,
    [switch]$DryRun
)

$ErrorActionPreference = 'SilentlyContinue'
$rootPath = $PSScriptRoot

function Stop-MatchingProcesses {
    param(
        [string[]]$Patterns,
        [string]$Label
    )

    $matched = Get-CimInstance Win32_Process | Where-Object {
        $commandLine = $_.CommandLine
        if (-not $commandLine) {
            return $false
        }

        foreach ($pattern in $Patterns) {
            if ($commandLine -like $pattern) {
                return $true
            }
        }
        return $false
    }

    foreach ($process in $matched) {
        if ($DryRun) {
            Write-Output "[dry-run] $Label -> PID $($process.ProcessId)"
        } else {
            Stop-Process -Id $process.ProcessId -Force
        }
    }
}

Start-Sleep -Seconds $DelaySeconds

$windowTitles = @(
    'Backend :43117',
    'Frontend :43118',
    'AI Round Table',
    'Start AI Round Table'
)

foreach ($title in $windowTitles) {
    if ($DryRun) {
        Write-Output "[dry-run] close window '$title'"
    } else {
        cmd /c "taskkill /F /FI ""WINDOWTITLE eq $title""" | Out-Null
    }
}

Stop-MatchingProcesses -Label 'backend' -Patterns @(
    "*$rootPath\\backend*uvicorn*main:app*",
    "*$rootPath\\backend*python.exe*main:app*"
)

Stop-MatchingProcesses -Label 'frontend' -Patterns @(
    "*$rootPath\\frontend*npm run dev*",
    "*$rootPath\\frontend*vite*",
    "*$rootPath\\frontend*node*"
)

if ($DryRun) {
    Write-Output '[dry-run] shutdown helper completed'
}
