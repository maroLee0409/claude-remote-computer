<#
rc-agent.ps1 - UI Automation 도우미. 설치 없이 Windows 기본 .NET 만 쓴다.

두 가지로 쓴다.
  1) 이 PC  (rc.py ui ...)
       powershell -NoProfile -ExecutionPolicy Bypass -File rc-agent.ps1 -Once controls "메모장"
  2) RDP 세션 안  (rc.py remote ...)
       세션 안 PowerShell 에서 이 파일을 실행해 두면 클립보드를 통로로 명령을 받는다.
       키보드·마우스를 안 쓰니 세션 안 포커스 사고가 없다.

프로토콜 (클립보드 텍스트)
  요청  "#RC <토큰> <seq> <명령>`n<인자1>`n<인자2>..."   (run 은 나머지 줄 전체가 코드)
  응답  "#RE <seq> OK|ERR`n<출력>"
  시작  "#RE 0 READY <토큰> <컴퓨터명>"
토큰은 실행할 때마다 새로 만든다 - 클립보드에 남은 예전 명령이 새 도우미에서 다시 실행되지 않게.

명령
  ping | windows | fg | focus <창> | wait <창> [초] | waitgone <창> [초]
  controls <창> [필터] | invoke <창> <이름|AutomationId> | get <창> <이름> | set <창> <이름> <값>
  run <PowerShell 코드> | stop
#>
param([string]$Once, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms
Add-Type -Namespace RcAgent -Name U -ReferencedAssemblies UIAutomationClient, UIAutomationTypes, WindowsBase -MemberDefinition @'
// powershell.exe 에서 UIA 를 처음 부르면 ProxyManager.LoadDefaultProxies 가 호출자 스택을 거슬러 보다가
// PowerShell 동적 메서드(ReflectedType=null)에서 NRE 를 내고, Win32/WinForms 컨트롤이 전부 패턴 없는 Pane 이 된다.
// 컴파일된 메서드에서 먼저 한 번 불러 두면 프록시가 정상으로 올라온다.
public static void InitUia() {
    System.Windows.Automation.AutomationElement.RootElement.FindAll(
        System.Windows.Automation.TreeScope.Children, System.Windows.Automation.Condition.TrueCondition);
}
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v);
[DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(int f, int x, int y, int d, IntPtr e);
[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte sc, int f, IntPtr e);
'@
# 좌표를 물리 화면 픽셀로 받는다 (rc.py 와 같은 모니터별 DPI v2, 없는 OS 면 시스템 DPI).
try { if (-not [RcAgent.U]::SetProcessDpiAwarenessContext([IntPtr]-4)) { [RcAgent.U]::SetProcessDPIAware() | Out-Null } }
catch { [RcAgent.U]::SetProcessDPIAware() | Out-Null }
[RcAgent.U]::InitUia()

$AE = [System.Windows.Automation.AutomationElement]
$Kids = [System.Windows.Automation.TreeScope]::Children
$Desc = [System.Windows.Automation.TreeScope]::Descendants
$All = [System.Windows.Automation.Condition]::TrueCondition

function Has($s, $sub) { $s -and $s.IndexOf($sub, [StringComparison]::OrdinalIgnoreCase) -ge 0 }

function Get-Wins { @($AE::RootElement.FindAll($Kids, $All)) | Where-Object { $_.Current.Name } }

function Get-Win($title) {
    $w = Get-Wins | Where-Object { Has $_.Current.Name $title } | Select-Object -First 1
    if (-not $w) { throw "창을 찾을 수 없다: $title" }
    $w
}

# 출력 좌표는 rc.py 스크린샷 좌표(가상 화면 왼쪽 위가 0,0). 주 모니터 왼쪽에 모니터가 있으면 화면 좌표와 다르다.
$OX = [RcAgent.U]::GetSystemMetrics(76); $OY = [RcAgent.U]::GetSystemMetrics(77)

function Show($el) {
    $c = $el.Current; $r = $c.BoundingRectangle
    $pos = if ($r.IsEmpty -or [double]::IsInfinity($r.X)) { '-' } else { '{0},{1},{2},{3}' -f [int]($r.X - $OX), [int]($r.Y - $OY), [int]$r.Width, [int]$r.Height }
    $off = if ($c.IsEnabled) { '' } else { ' (비활성)' }
    '{0} | {1} | {2} | {3}{4}' -f $c.ControlType.ProgrammaticName.Replace('ControlType.', ''), $c.Name, $c.AutomationId, $pos, $off
}

function Fg {
    $h = [RcAgent.U]::GetForegroundWindow()
    if ($h -eq [IntPtr]::Zero) { return '(없음)' }
    $c = $AE::FromHandle($h).Current
    "$($c.Name) [$((Get-Process -Id $c.ProcessId -ErrorAction SilentlyContinue).ProcessName)]"
}

# AutomationId 정확히 → 이름 정확히 → 이름 일부 순으로 찾는다. 여러 개면 전부 돌려준다.
function Find-El($title, $name) {
    $els = @((Get-Win $title).FindAll($Desc, $All))
    foreach ($m in { $_.Current.AutomationId -eq $name }, { $_.Current.Name -eq $name }, { Has $_.Current.Name $name }) {
        $hit = @($els | Where-Object $m)
        if ($hit) { return $hit }
    }
    throw "컨트롤을 찾을 수 없다: $name  (controls 로 이름을 확인할 것)"
}

function Pat($el, $t) { $p = $null; if ($el.TryGetCurrentPattern($t::Pattern, [ref]$p)) { $p } }

function Focus-Win($title) {
    $w = Get-Win $title; $h = [IntPtr]$w.Current.NativeWindowHandle
    for ($i = 0; $i -lt 5; $i++) {
        # 포그라운드 잠금 회피용 ALT (rc.py require_focus 와 같은 수법)
        [RcAgent.U]::keybd_event(0x12, 0, 0, [IntPtr]::Zero); [RcAgent.U]::keybd_event(0x12, 0, 2, [IntPtr]::Zero)
        [RcAgent.U]::SetForegroundWindow($h) | Out-Null
        Start-Sleep -Milliseconds 300
        if ([RcAgent.U]::GetForegroundWindow() -eq $h) { return "focused: $($w.Current.Name)" }
    }
    throw "포커스 전환 실패. 지금 앞에 있는 창: $(Fg)"
}

# 패턴이 없는 컨트롤용 - 가운데를 실제로 클릭한다. 다른 창이 가리고 있으면 누르지 않는다.
function Click-El($title, $el) {
    $r = $el.Current.BoundingRectangle
    if ($r.IsEmpty -or [double]::IsInfinity($r.X)) { throw "화면에 안 보이는 컨트롤이라 클릭할 수 없다" }
    Focus-Win $title | Out-Null
    $x = [int]($r.X + $r.Width / 2); $y = [int]($r.Y + $r.Height / 2)
    $top = $AE::FromPoint((New-Object System.Windows.Point($x, $y)))
    $walk = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    while ($top -and ($p = $walk.GetParent($top)) -and $p -ne $AE::RootElement) { $top = $p }
    if ($top.Current.NativeWindowHandle -ne (Get-Win $title).Current.NativeWindowHandle) {
        throw "그 위치를 다른 창이 가리고 있다: $($top.Current.Name)"
    }
    [RcAgent.U]::SetCursorPos($x, $y) | Out-Null; Start-Sleep -Milliseconds 80
    [RcAgent.U]::mouse_event(2, 0, 0, 0, [IntPtr]::Zero); [RcAgent.U]::mouse_event(4, 0, 0, 0, [IntPtr]::Zero)
}

function Do-Invoke($title, $name) {
    $hit = @(Find-El $title $name); $el = $hit[0]
    $what = Show $el   # 누른 뒤엔 창이 닫혀 이름을 못 읽을 수 있다
    if ($p = Pat $el ([System.Windows.Automation.InvokePattern])) {
        # 모달 창을 띄우는 버튼은 Invoke 가 그 창이 닫힐 때까지 안 돌아오기도 한다 - 별도 스레드로 쏘고 3초만 기다린다.
        $ps = [powershell]::Create().AddScript({ param($p) $p.Invoke() }).AddArgument($p)
        $ar = $ps.BeginInvoke()
        if ($ar.AsyncWaitHandle.WaitOne(3000)) { $ps.EndInvoke($ar) | Out-Null; $how = 'invoke' }
        else { $how = 'invoke (3초 안에 안 끝남 - 모달 창이 떴을 수 있다)' }
    }
    elseif ($p = Pat $el ([System.Windows.Automation.SelectionItemPattern])) { $p.Select(); $how = 'select' }
    elseif ($p = Pat $el ([System.Windows.Automation.TogglePattern])) { $p.Toggle(); $how = 'toggle' }
    elseif ($p = Pat $el ([System.Windows.Automation.ExpandCollapsePattern])) { $p.Expand(); $how = 'expand' }
    else { Click-El $title $el; $how = 'click' }
    "$how : $what"
    if ($hit.Count -gt 1) { "[주의] 같은 이름이 $($hit.Count)개 - 첫 번째를 눌렀다" }
}

function Wait-Win($title, $sec, $gone) {
    $end = (Get-Date).AddSeconds($sec)
    do {
        $w = Get-Wins | Where-Object { Has $_.Current.Name $title } | Select-Object -First 1
        if ([bool]$w -ne [bool]$gone) { if ($gone) { return "gone: $title" } else { return "found: $(Show $w)" } }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $end)
    throw "시간 초과 ($sec 초): $title"
}

function Invoke-Rc($cmd, [string[]]$a) {
    switch ($cmd) {
        'ping' { "pong $env:COMPUTERNAME $env:USERNAME $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" }
        'windows' {
            $fg = [RcAgent.U]::GetForegroundWindow()
            Get-Wins | ForEach-Object {
                $mark = if ([IntPtr]$_.Current.NativeWindowHandle -eq $fg) { '*' } else { ' ' }
                "$mark $(Show $_) [$((Get-Process -Id $_.Current.ProcessId -ErrorAction SilentlyContinue).ProcessName)]"
            }
        }
        'fg' { Fg }
        'focus' { Focus-Win $a[0] }
        'wait' { Wait-Win $a[0] $(if ($a[1]) { [int]$a[1] } else { 10 }) $false }
        'waitgone' { Wait-Win $a[0] $(if ($a[1]) { [int]$a[1] } else { 10 }) $true }
        'controls' {
            $f = $a[1]
            # ponytail: 300개에서 자른다. 큰 그리드는 필터로 좁힐 것.
            @((Get-Win $a[0]).FindAll($Desc, $All)) | Where-Object {
                $c = $_.Current
                ($c.Name -or $c.AutomationId) -and (-not $f -or (Has $c.Name $f) -or (Has $c.AutomationId $f) -or (Has $c.ControlType.ProgrammaticName $f))
            } | Select-Object -First 300 | ForEach-Object { Show $_ }
        }
        'invoke' { Do-Invoke $a[0] $a[1] }
        'get' {
            $el = @(Find-El $a[0] $a[1])[0]
            if ($p = Pat $el ([System.Windows.Automation.ValuePattern])) { $p.Current.Value }
            elseif ($p = Pat $el ([System.Windows.Automation.TextPattern])) { $p.DocumentRange.GetText(200000) }
            else { $el.Current.Name }
        }
        'set' {
            $el = @(Find-El $a[0] $a[1])[0]
            $p = Pat $el ([System.Windows.Automation.ValuePattern])
            if (-not $p) { throw "값을 넣을 수 없는 컨트롤: $(Show $el)" }
            $p.SetValue($a[2]); "set : $(Show $el)"
        }
        'run' { & ([scriptblock]::Create(($a -join "`n"))) *>&1 | Out-String -Width 250 }
        'stop' { 'bye' }
        default { throw "모르는 명령: $cmd" }
    }
}

if ($Once) {
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    try { Write-Output (Invoke-Rc $Once @($Rest) | Out-String).TrimEnd(); exit 0 }
    catch { Write-Output "ERR $($_.Exception.Message)"; exit 1 }
}

# ── 도우미 모드: 클립보드를 보고 있다가 토큰이 맞는 명령만 실행한다.
function Clip-Get { for ($i = 0; $i -lt 3; $i++) { try { return [Windows.Forms.Clipboard]::GetText() } catch { Start-Sleep -Milliseconds 100 } } }
function Clip-Set($t) { for ($i = 0; $i -lt 5; $i++) { try { [Windows.Forms.Clipboard]::SetText($t); return } catch { Start-Sleep -Milliseconds 200 } } }

$token = -join (1..12 | ForEach-Object { 'abcdefghjkmnpqrstuvwxyz23456789'[(Get-Random -Maximum 31)] })
Clip-Set "#RE 0 READY $token $env:COMPUTERNAME"
Write-Host "rc-agent 실행 중 (토큰 $token). 끝내려면 이 창에서 Ctrl+C"
$last = $null
while ($true) {
    Start-Sleep -Milliseconds 400
    $t = Clip-Get
    if (-not $t -or -not $t.StartsWith("#RC $token ")) { continue }
    $lines = $t -split "`r?`n"
    $h = $lines[0] -split ' '
    if ($h[2] -eq $last) { continue }
    $last = $h[2]; $cmd = $h[3]; $a = @($lines | Select-Object -Skip 1)
    $shown = ($a -join ' | '); if ($shown.Length -gt 100) { $shown = $shown.Substring(0, 100) + '...' }
    Write-Host "[$(Get-Date -Format HH:mm:ss)] $cmd $shown"
    try { $out = (Invoke-Rc $cmd $a | Out-String).TrimEnd(); $st = 'OK' }
    catch { $out = $_.Exception.Message; $st = 'ERR' }
    Clip-Set "#RE $($h[2]) $st`n$out"
    if ($cmd -eq 'stop') { break }
}
