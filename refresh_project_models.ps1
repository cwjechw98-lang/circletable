$ErrorActionPreference = 'Stop'

try {
    $response = Invoke-RestMethod -Method Post 'http://localhost:8000/api/providers/refresh' -TimeoutSec 5

    if (-not $response.ok) {
        throw 'Refresh confirmation was not received.'
    }

    Write-Host 'OK: The model list was refreshed in the running app.'
    Write-Host ''
    Write-Host 'Ollama:'

    $models = @()
    if ($null -ne $response.providers.ollama) {
        $models = @($response.providers.ollama.models)
    }

    if ($models.Count -eq 0) {
        Write-Host '- no local models found'
        exit 0
    }

    foreach ($model in $models) {
        Write-Host ('- ' + $model)
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
