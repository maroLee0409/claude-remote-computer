<#
  이 저장소의 skills/ 를 ~/.claude/skills/ 로 복사한다.
  그래야 이 PC 의 모든 Claude Code 세션이 최신 버전을 쓴다.

      .\scripts\install.ps1            # 바뀐 것만 복사
      .\scripts\install.ps1 -WhatIf    # 무엇이 바뀔지만 보기
      .\scripts\install.ps1 -Force     # 내용 같아도 전부 덮어쓰기

  저장소 안에서 작업이 끝나면 .claude/settings.json 의 Stop 훅이 이걸 자동으로 부른다.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param([switch]$Force)

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$src = Join-Path $repo 'skills'
$dst = Join-Path $env:USERPROFILE '.claude\skills'

if (-not (Test-Path $src)) { throw "skills 폴더가 없다: $src" }
New-Item -ItemType Directory -Force $dst | Out-Null

$changed = 0
$same = 0

Get-ChildItem $src -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($src.Length).TrimStart('\')
    $target = Join-Path $dst $rel

    $needsCopy = $Force -or -not (Test-Path $target)
    if (-not $needsCopy) {
        # 해시로 비교한다. 타임스탬프는 복사할 때마다 바뀌어서 신뢰할 수 없다.
        $a = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
        $b = (Get-FileHash $target     -Algorithm SHA256).Hash
        $needsCopy = ($a -ne $b)
    }

    if (-not $needsCopy) { $same++; return }

    $dir = Split-Path $target -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    if ($PSCmdlet.ShouldProcess($rel, '복사')) {
        Copy-Item $_.FullName $target -Force
        Write-Host ("  갱신  {0}" -f $rel) -ForegroundColor Green
    }
    $changed++
}

if ($changed -eq 0) {
    Write-Host ("이미 최신이다 ({0}개 파일). -> {1}" -f $same, $dst) -ForegroundColor DarkGray
} else {
    Write-Host ("{0}개 갱신, {1}개 그대로.  -> {2}" -f $changed, $same, $dst) -ForegroundColor Cyan
    Write-Host "새 Claude Code 세션부터 반영된다." -ForegroundColor DarkGray
}
