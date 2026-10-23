param([int]$FirstId=1)
$ErrorActionPreference = 'Continue'
$taskResearchRoot = $PSScriptRoot
$taskCacheRoot = Join-Path $taskResearchRoot 'source_cache'
$taskSources = Get-Content -LiteralPath (Join-Path $taskResearchRoot 'sources.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($taskSource in $taskSources) {
    if ([int]($taskSource.id.Substring(1)) -lt $FirstId) { continue }
    $taskCacheFile = Join-Path $taskCacheRoot ($taskSource.id + '.source')
    if (Test-Path -LiteralPath $taskCacheFile) { continue }
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $taskSource.url -OutFile $taskCacheFile -TimeoutSec 25 -ErrorAction Stop
        Write-Output ($taskSource.id + ' downloaded')
    } catch { Write-Output ($taskSource.id + ' unavailable: ' + $_.Exception.Message) }
}
