<#
  이 저장소의 skills/ 와 agents/ 를 ~/.claude/ 아래로 복사한다.
  그래야 이 PC 의 모든 Claude Code 세션이 최신 버전을 쓴다.

      .\scripts\install.ps1            # 바뀐 것만 복사
      .\scripts\install.ps1 -WhatIf    # 무엇이 바뀔지만 보기
      .\scripts\install.ps1 -Force     # 사본이 더 새로워도, 내용 같아도 전부 덮어쓰기

  사본이 저장소보다 새로우면(사본을 직접 고친 경우) 덮지 않고 경고만 한다.
  그 변경을 저장소로 옮긴 뒤 다시 돌리거나, 버려도 되면 -Force.

  저장소 안에서 작업이 끝나면 .claude/settings.json 의 Stop 훅이 이걸 자동으로 부른다.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param([switch]$Force)

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $repo 'skills'))) { throw "skills 폴더가 없다: $repo\skills" }

# -WhatIf 일 때 Get-FileHash 까지 '하는 척'만 해서 해시가 비고, 전부 "같다"로 나오던 문제를 막는다.
function Get-Sha([string]$path) { $WhatIfPreference = $false; (Get-FileHash $path -Algorithm SHA256).Hash }

$changed = 0
$same = 0
$kept = 0

foreach ($name in 'skills', 'agents') {
    $src = Join-Path $repo $name
    $dst = Join-Path $env:USERPROFILE ".claude\$name"
    if (-not (Test-Path $src)) { continue }
    New-Item -ItemType Directory -Force $dst | Out-Null

    Get-ChildItem $src -Recurse -File | Where-Object { $_.FullName -notmatch '\\__pycache__\\' } | ForEach-Object {
        $rel = $_.FullName.Substring($src.Length).TrimStart('\')
        $target = Join-Path $dst $rel

        $needsCopy = $Force -or -not (Test-Path $target)
        if (-not $needsCopy) {
            # 해시로 비교한다. 내용이 같으면 시각과 상관없이 건너뛴다.
            $needsCopy = ((Get-Sha $_.FullName) -ne (Get-Sha $target))
            # 내용이 다른데 사본 쪽이 더 나중에 고쳐졌으면 사본을 직접 고친 것이다. 덮으면 그 작업이 사라진다.
            # (Copy-Item 은 수정 시각을 그대로 옮기므로, 복사만 된 사본은 저장소보다 새롭지 않다.)
            if ($needsCopy -and (Get-Item $target).LastWriteTime -gt $_.LastWriteTime) {
                Write-Warning ("사본이 더 새롭다 - 건너뜀: {0}\{1}  (저장소로 옮기거나 -Force)" -f $name, $rel)
                $kept++
                return
            }
        }

        if (-not $needsCopy) { $same++; return }

        $dir = Split-Path $target -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
        if ($PSCmdlet.ShouldProcess("$name\$rel", '복사')) {
            Copy-Item $_.FullName $target -Force
            Write-Host ("  갱신  {0}\{1}" -f $name, $rel) -ForegroundColor Green
        }
        $changed++
    }
}

if ($changed -eq 0) {
    Write-Host ("이미 최신이다 ({0}개 파일, 건너뜀 {1}개)." -f $same, $kept) -ForegroundColor DarkGray
} else {
    Write-Host ("{0}개 갱신, {1}개 그대로, {2}개 건너뜀." -f $changed, $same, $kept) -ForegroundColor Cyan
    Write-Host "새 Claude Code 세션부터 반영된다." -ForegroundColor DarkGray
}
