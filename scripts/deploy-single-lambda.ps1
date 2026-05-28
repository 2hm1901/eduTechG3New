param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("text-extraction", "api-backend", "chat")]
  [string]$Lambda,

  [switch]$Apply
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
  $scriptDir = $PSScriptRoot
  return (Resolve-Path (Join-Path $scriptDir "..")).Path
}

function New-Timestamp {
  return Get-Date -Format "yyyyMMddHHmmss"
}

function New-TextExtractionZip {
  param(
    [string]$RepoRoot
  )

  $placeholderDir = Join-Path $RepoRoot "terraform\lambda_placeholder"
  $sourceFile = Join-Path $placeholderDir "text_extraction.py"
  $buildCandidates = @(
    (Join-Path $placeholderDir "build_text_extract"),
    (Join-Path $placeholderDir "build_text_extract_20260528175544")
  )

  $buildDir = $buildCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $buildDir) {
    throw "No text extraction build directory found. Expected an existing build_text_extract folder with pypdf included."
  }

  Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $buildDir "text_extraction.py") -Force

  $timestamp = New-Timestamp
  $zipPath = Join-Path $placeholderDir "text_extraction_$timestamp.zip"
  $items = Get-ChildItem -LiteralPath $buildDir -Force | ForEach-Object { $_.FullName }
  Compress-Archive -Path $items -DestinationPath $zipPath -CompressionLevel Optimal -Force
  return $zipPath
}

function Sync-ApiBackendSource {
  param(
    [string]$RepoRoot
  )

  $bundleSrc = Join-Path $RepoRoot "terraform\lambda_api\src"
  $sourceSrc = Join-Path $RepoRoot "src"
  New-Item -ItemType Directory -Force -Path $bundleSrc | Out-Null

  Copy-Item -LiteralPath (Join-Path $sourceSrc "app.py") -Destination (Join-Path $bundleSrc "app.py") -Force
  Copy-Item -LiteralPath (Join-Path $sourceSrc "handlers.py") -Destination (Join-Path $bundleSrc "handlers.py") -Force
  Copy-Item -LiteralPath (Join-Path $sourceSrc "config.py") -Destination (Join-Path $bundleSrc "config.py") -Force
  Copy-Item -LiteralPath (Join-Path $sourceSrc "__init__.py") -Destination (Join-Path $bundleSrc "__init__.py") -Force

  $bundleAdapters = Join-Path $bundleSrc "adapters"
  $sourceAdapters = Join-Path $sourceSrc "adapters"
  New-Item -ItemType Directory -Force -Path $bundleAdapters | Out-Null
  Copy-Item -LiteralPath (Join-Path $sourceAdapters "ai.py") -Destination (Join-Path $bundleAdapters "ai.py") -Force
  Copy-Item -LiteralPath (Join-Path $sourceAdapters "factory.py") -Destination (Join-Path $bundleAdapters "factory.py") -Force
  Copy-Item -LiteralPath (Join-Path $sourceAdapters "sqlite_store.py") -Destination (Join-Path $bundleAdapters "sqlite_store.py") -Force
  Copy-Item -LiteralPath (Join-Path $sourceAdapters "storage.py") -Destination (Join-Path $bundleAdapters "storage.py") -Force
  Copy-Item -LiteralPath (Join-Path $sourceAdapters "userstore.py") -Destination (Join-Path $bundleAdapters "userstore.py") -Force
  Copy-Item -LiteralPath (Join-Path $sourceAdapters "vector.py") -Destination (Join-Path $bundleAdapters "vector.py") -Force
  Copy-Item -LiteralPath (Join-Path $sourceAdapters "__init__.py") -Destination (Join-Path $bundleAdapters "__init__.py") -Force
}

function New-ApiBackendZip {
  param(
    [string]$RepoRoot
  )

  Sync-ApiBackendSource -RepoRoot $RepoRoot

  $bundleDir = Join-Path $RepoRoot "terraform\lambda_api"
  $timestamp = New-Timestamp
  $zipPath = Join-Path $bundleDir "api_backend_$timestamp.zip"
  $items = Get-ChildItem -LiteralPath $bundleDir -Force |
    Where-Object { $_.Name -ne (Split-Path $zipPath -Leaf) -and $_.Extension -ne ".zip" } |
    ForEach-Object { $_.FullName }
  Compress-Archive -Path $items -DestinationPath $zipPath -CompressionLevel Optimal -Force
  return $zipPath
}

function New-ChatZip {
  param(
    [string]$RepoRoot
  )

  $placeholderDir = Join-Path $RepoRoot "terraform\lambda_placeholder"
  $sourceFile = Join-Path $placeholderDir "chat.py"
  $timestamp = New-Timestamp
  $zipPath = Join-Path $placeholderDir "chat_$timestamp.zip"
  Compress-Archive -LiteralPath $sourceFile -DestinationPath $zipPath -CompressionLevel Optimal -Force
  return $zipPath
}

function Invoke-TargetedApply {
  param(
    [string]$RepoRoot,
    [string]$Lambda,
    [string]$ZipPath
  )

  $terraformDir = Join-Path $RepoRoot "terraform"
  $relativeZip = ".\" + ((Resolve-Path $ZipPath).Path.Replace((Resolve-Path $terraformDir).Path + "\", "") -replace "/", "\")

  switch ($Lambda) {
    "text-extraction" {
      $target = 'module.lambda.aws_lambda_function.text_extraction'
      $varArg = "text_extraction_zip=$relativeZip"
    }
    "api-backend" {
      $target = 'module.lambda.aws_lambda_function.api_backend'
      $varArg = "api_backend_zip=$relativeZip"
    }
    "chat" {
      $target = 'module.lambda.aws_lambda_function.chat'
      $varArg = "chat_zip=$relativeZip"
    }
    default {
      throw "Unsupported Lambda target: $Lambda"
    }
  }

  Push-Location $terraformDir
  try {
    terraform apply -auto-approve "-target=$target" "-var=$varArg"
  }
  finally {
    Pop-Location
  }
}

$repoRoot = Get-RepoRoot

switch ($Lambda) {
  "text-extraction" {
    $zipPath = New-TextExtractionZip -RepoRoot $repoRoot
    $resource = "module.lambda.aws_lambda_function.text_extraction"
  }
  "api-backend" {
    $zipPath = New-ApiBackendZip -RepoRoot $repoRoot
    $resource = "module.lambda.aws_lambda_function.api_backend"
  }
  "chat" {
    $zipPath = New-ChatZip -RepoRoot $repoRoot
    $resource = "module.lambda.aws_lambda_function.chat"
  }
  default {
    throw "Unsupported Lambda target: $Lambda"
  }
}


Write-Output "Built: $zipPath"
Write-Output "Target: $resource"

if ($Apply) {
  Invoke-TargetedApply -RepoRoot $repoRoot -Lambda $Lambda -ZipPath $zipPath
}
else {
  Write-Output "Dry run only. Re-run with -Apply to push this Lambda to AWS."
}
