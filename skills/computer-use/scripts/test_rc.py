"""rc.py 자가 점검.  python test_rc.py

먼저 캡처 좌표 환산(--img)·크기 상한·화면 변화 감지를 입력 없이 확인한다.
그다음 WinForms 시험 창을 띄워 이름으로 넣기·누르기·읽기를 하고(ui),
같은 PC 에 도우미를 띄워 클립보드 왕복(remote)을 확인한다. 클립보드를 덮어쓴다.
덮개 창으로 덮은 채 뒤에서(--bg) 넣고·누르고·조합키로 복사·붙이기를 하고, 엑셀이 있으면 새 통합 문서에
COM 으로 쓰고 읽는다(xl). 시험 창은 전부 모니터 밖에 뜨고 포그라운드는 사용자 것 그대로 둔다 -
시험 창이 한 번이라도 앞으로 오면 실패다(사용자 키가 샌다).
ui invoke 는 창을 앞으로 가져오니(pitfalls 15) RC_TEST_FOCUS=1 일 때만 본다 - 키보드를 안 쓸 때.
InitUia 가 빠지면(pitfalls 10) ui 첫 assert 에서 깨진다.
"""
import os
import subprocess
import tempfile
import threading
import time

from PIL import Image, ImageDraw

import rc

png = os.path.join(tempfile.gettempdir(), "rc_selftest.png")
rc.shot(png, (100, 50, 400, 200), 0.5)
assert rc.img_meta(png) == (100, 50, 0.5)
assert rc.img_to_shot(png, 10, 20) == (120, 90)
_, size, s = rc.shot(png)
assert max(size) <= rc.MAX_EDGE and size[0] * size[1] <= rc.MAX_PIXELS, size
assert rc.img_to_shot(png, size[0], size[1])[0] >= rc.grab().width - 2 / s

blank = Image.new("RGB", (100, 100))
caret, box = blank.copy(), blank.copy()
ImageDraw.Draw(caret).line((50, 10, 50, 30), fill="white", width=2)
ImageDraw.Draw(box).rectangle((10, 10, 29, 19), fill="white")
assert rc.changed(blank, caret) is None          # 깜빡이는 커서는 변화로 안 친다
assert rc.changed(blank, box) == (10, 10, 30, 20)
os.remove(png)

try:
    rc.find_shortcut("없는바로가기12345")
    raise AssertionError("없는 바로가기를 찾았다")
except RuntimeError:
    pass

# 시험 창은 모니터 밖에 띄워 사용자 화면을 안 가리고(덮개·엑셀도), 뜰 때 포그라운드도 안 가져간다.
# ShowDialog 는 무조건 활성화하니 Application.Run 으로 띄우고, 항상 위는 TopMost 속성 대신 창 스타일(WS_EX_TOPMOST)로 -
# TopMost 속성이 켜진 폼은 보일 때 첫 컨트롤에 포커스를 줘서(Form.SetVisibleCore) 창이 앞으로 온다.
NOACT = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -WarningAction SilentlyContinue -ReferencedAssemblies System.Windows.Forms -TypeDefinition @'
public class NoActForm : System.Windows.Forms.Form {
    protected override bool ShowWithoutActivation { get { return true; } }
    protected override System.Windows.Forms.CreateParams CreateParams { get { var p = base.CreateParams; p.ExStyle |= 8; return p; } }
}
'@
"""
FORM = NOACT + r"""
$f = New-Object NoActForm; $f.Text = 'rc selftest'   # 항상 위 - 다른 앱 창이 버튼을 덮으면 시험이 흔들린다
$f.StartPosition = 'Manual'; $f.Location = New-Object Drawing.Point(20000, 100)   # 모니터 밖
$t = New-Object Windows.Forms.TextBox; $t.Name = 'txtLot'
$b = New-Object Windows.Forms.Button; $b.Name = 'btnSearch'; $b.Text = 'Search'; $b.Top = 40
$l = New-Object Windows.Forms.Label; $l.Name = 'lblResult'; $l.Text = 'ready'; $l.Top = 80
$b.Add_Click({ $l.Text = 'searched: ' + $t.Text })
$g = New-Object Windows.Forms.DataGridView; $g.Name = 'grid'; $g.Top = 110; $g.Width = 260; $g.Height = 100
$g.AllowUserToAddRows = $false; $g.ClipboardCopyMode = 'EnableWithoutHeaderText'; $g.SelectionMode = 'FullRowSelect'
[void]$g.Columns.Add('LOT', 'LOT'); [void]$g.Columns.Add('QTY', 'QTY'); [void]$g.Rows.Add('LOT-A', '10'); [void]$g.Rows.Add('LOT-B', '20')
# 실제 MES 처럼 '한 번 써 본 창' 으로 만든다. 막 띄운 창은 띄운 쪽이 준 포그라운드 권리를 한 번 쥐고 있어서, 사용자가 손을 놓고
# 있으면 첫 click --bg 에 앞으로 온다(pitfalls 15). 지금 앞에 있는 창에 포그라운드를 '주면' 아무것도 안 바뀌고 그 권리만 쓴다.
Add-Type -Namespace T -Name F -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();'
$f.Add_Shown({ [void][T.F]::SetForegroundWindow([T.F]::GetForegroundWindow()) })
$f.Controls.AddRange(@($t, $b, $l, $g)); [Windows.Forms.Application]::Run($f)
"""
XL_HOST = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -Namespace T -Name W -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
'@
$prev = [T.W]::GetForegroundWindow()
$xl = New-Object -ComObject Excel.Application; $wb = $xl.Workbooks.Add(); $h = [IntPtr]$wb.Windows.Item(1).Hwnd
[void][T.W]::SetWindowPos($h, [IntPtr]::Zero, 20000, 100, 0, 0, 0x15)   # 모니터 밖으로 (NOSIZE|NOZORDER|NOACTIVATE)
[void][T.W]::ShowWindow($h, 4)   # SW_SHOWNOACTIVATE - Visible=$true 는 포그라운드를 뺏는다
Start-Sleep -Milliseconds 1500   # 막 띄운 엑셀은 다 뜨면서 스스로 앞으로 오기도 한다(시험에서만 - 사용자 엑셀은 이미 떠 있다) -> 돌려준다
if ([T.W]::GetForegroundWindow() -ne $prev) { [void][T.W]::SetForegroundWindow($prev) }
[Console]::Out.WriteLine($wb.Name); [void][Console]::In.ReadLine()
$wb.Close($false); $xl.Quit()
"""
COVER = NOACT + r"""
$f = New-Object NoActForm; $f.Text = 'rc cover'; $f.BackColor = 'Red'
$f.StartPosition = 'Manual'; $f.Location = New-Object Drawing.Point(20000, 600)   # 모니터 밖. 자리는 시험이 맞춘다
[Windows.Forms.Application]::Run($f)
"""


def ps(script, **kw):
    return subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                            creationflags=rc.CREATE_NO_WINDOW, **kw)   # 콘솔 창도 안 띄운다


user_fg = rc.foreground()   # 준비할 때 앞으로 가져온 것을 끝나면 사용자 창에 돌려준다 - 안 하면 포그라운드가 빈 채 남는다
form = ps(FORM)
agent = cover = xlp = None
try:
    assert rc.wait_for(lambda: rc.find_window("rc selftest"), 15), "시험 창이 안 떴다"
    me = rc.find_window("rc selftest")
    edge = rc.to_shot(rc.user32.GetSystemMetrics(76) + rc.user32.GetSystemMetrics(78), 0)[0]   # 가상 화면 오른쪽 끝
    assert rc.park("rc selftest")[0] >= edge and rc.foreground()[0] != me, "park 가 모니터 밖으로 안 옮겼다"
    stole, done, stage = [], [], ["뜬 직후"]   # 점검 몇 번이 아니라 20ms 마다 본다 - 잠깐 앞으로 왔다 가도 그 사이 사용자 키가 샌다

    def watch():
        while not done:
            if rc.foreground()[0] == me and stage[0] not in stole:
                stole.append(stage[0])   # 어느 단계에서 왔는지
            time.sleep(0.02)
    threading.Thread(target=watch, daemon=True).start()
    stage[0] = "ui"
    ok, out = rc.ui("controls", "rc selftest", "btn")
    assert ok and "Button | Search | btnSearch" in out, out
    assert rc.ui("set", "rc selftest", "txtLot", "LOT-1")[0]   # Win32 입력칸은 WM_SETTEXT - 포커스를 안 옮긴다
    assert rc.ui("get", "rc selftest", "txtLot") == (True, "LOT-1")
    assert not rc.ui("invoke", "rc selftest", "없는것")[0]

    # --bg: 빨간 창이 오른쪽 절반을 덮은 채 뒤에서 넣고 누르고 찍는다. 시험 창이 한 번이라도 앞으로 오면 안 된다.
    def center(line):
        x, y, w, h = map(int, line.rsplit("|", 1)[1].split(","))
        return x + w // 2, y + h // 2
    ctl = {l.split("|")[2].strip(): l for l in rc.ui("controls", "rc selftest")[1].splitlines() if l.count("|") >= 3}
    cover = ps(COVER)
    assert rc.wait_for(lambda: rc.find_window("rc cover"), 15), "덮개 창이 안 떴다"
    r = rc.wt.RECT(); rc.user32.GetWindowRect(me, rc.ctypes.byref(r))   # 덮개를 시험 창 오른쪽 절반에 (물리 픽셀로)
    rc.user32.SetWindowPos(rc.find_window("rc cover"), None, (r.left + r.right) // 2, r.top, r.right - r.left, r.bottom - r.top, 0x14)
    time.sleep(0.5)
    stage[0] = "--bg"
    assert rc.integrity(rc._pid(me)) == rc.integrity(os.getpid()) in (0x2000, 0x3000), "권한 읽기가 틀렸다"   # 일반·관리자 둘 다
    gif = os.path.join(tempfile.gettempdir(), "rc_selftest.gif")
    rec = threading.Thread(target=lambda: rc.record(gif, me, max_sec=8))
    rec.start(); time.sleep(1)
    rc.bg_click("rc selftest", *center(ctl["txtLot"]))
    rc.bg_type("rc selftest", "한글2")
    rc.bg_click("rc selftest", *center(ctl["btnSearch"]))   # 버튼 자리는 안 덮였다 - 덮이면 WinForms 가 Click 을 안 낸다(pitfalls 11)
    v = rc.ui("get", "rc selftest", "lblResult"), rc.ui("get", "rc selftest", "txtLot")
    assert v[0] == (True, "searched: LOT-1한글2"), v
    time.sleep(1); open(rc.REC_STOP, "w").close(); rec.join(10)
    with Image.open(gif) as g:
        assert g.n_frames >= 2, "녹화에 바뀐 장면이 안 담겼다"   # 덮인 창인데도 입력·버튼 결과가 찍혀야 한다
    os.remove(gif)
    img = rc.grab_window(me)
    assert img.getpixel((img.width * 3 // 4, img.height // 2))[:3] != (255, 0, 0), "덮개가 찍혔다"

    # 조합키: 그리드 둘째 행을 눌러 Ctrl+C. 사용자 클립보드·Ctrl 상태는 그대로여야 한다.
    rc.set_clipboard("USER-CLIP")
    out = rc.ui("controls", "rc selftest", "행")[1]
    cells = {l.split("|")[1].strip(): l for l in out.splitlines() if l.count("|") >= 3}
    assert "LOT 행 1" in cells, (out, rc.foreground()[1], rc.list_windows("rc "))
    rc.bg_click("rc selftest", *center(cells["LOT 행 1"]))
    row, restored = rc.bg_copy("rc selftest")
    row = row.strip()
    assert row == "LOT-B\t20", repr(row)   # Ctrl 이 안 먹었으면 셀에 c 가 타이핑되고 클립보드가 안 바뀐다
    assert restored and rc.get_clipboard() == "USER-CLIP", "클립보드를 돌려놓지 않았다"
    assert not rc.user32.GetAsyncKeyState(0x11) & 0x8000 and not rc.user32.GetKeyState(0x11) & 0x8000, "Ctrl 이 눌린 채 남았다"
    rc.bg_key("rc selftest", "ctrl", "a")
    assert rc.bg_copy("rc selftest")[0].split() == ["LOT-A", "10", "LOT-B", "20"]
    # 붙이기: 입력칸 글을 고르고(옛 입력칸은 Ctrl+A 가 없다 - End, Shift+Home), 빌린 클립보드로 Ctrl+V
    rc.bg_click("rc selftest", *center(ctl["txtLot"]))
    rc.bg_key("rc selftest", "end")
    rc.bg_key("rc selftest", "shift", "home")
    assert rc.bg_paste("rc selftest", "P-1") and rc.get_clipboard() == "USER-CLIP"
    v = rc.ui("get", "rc selftest", "txtLot")
    assert v == (True, "P-1"), v

    # 사용자가 쓰고 있는 창(포그라운드)에는 보내지 않는다 - 붙는 순간 사용자 키가 Ctrl 로 보인다.
    # 사용자 창에 진짜로 보내 볼 수는 없으니 지키는 쪽만 본다.
    try:
        with rc._fg_guard(rc.foreground()[0], "지금 앞 창"):
            raise AssertionError("포그라운드 창을 막지 않았다")
    except RuntimeError as e:
        assert "쓰고 있다" in str(e), e

    # 엑셀(깔려 있을 때만): 시험이 띄운 새 통합 문서에 COM 으로 쓰고 읽는다. 위에서 복사한 그리드 행도 옮긴다.
    xlp = ps(XL_HOST, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    book = xlp.stdout.readline().decode("utf-8", "replace").strip()
    if book:
        time.sleep(0.5)
        assert rc._class(rc.foreground()[0]) != "XLMAIN", "시험용 엑셀이 뜨면서 앞으로 왔다 - 시험 준비 문제(xl 탓 아님)"
        assert rc.xl_set("A1", "LOT\tQTY\nLOT-A\t10\n한글\t1.5", book) == "A1:B3"
        assert rc.xl_get("A1:B3", book) == "LOT\tQTY\nLOT-A\t10\n한글\t1.5"
        assert rc.xl_get("B2", book) == "10"
        assert rc.xl_set("D1", row, book) == "D1:E1" and rc.xl_get("D1:E1", book) == "LOT-B\t20"
        assert rc._class(rc.foreground()[0]) != "XLMAIN", "xl 이 엑셀을 앞으로 가져왔다"
        try:
            rc.xl_get("A1", "없는책12345"); raise AssertionError("없는 통합 문서를 찾았다")
        except RuntimeError:
            pass
    else:
        print("엑셀이 없어 xl 시험은 건너뜀")

    # 최소화된 창은 복원하지 않고 멈춘다 - 복원하면 포그라운드를 가져간다(pitfalls 14)
    rc.user32.ShowWindow(me, 7); time.sleep(0.6)   # SW_SHOWMINNOACTIVE - 포커스를 안 건드리고 최소화
    assert rc.user32.IsIconic(me)
    try:
        rc.bg_click("rc selftest", *center(ctl["txtLot"])); raise AssertionError("최소화된 창에 보냈다")
    except RuntimeError as e:
        assert "최소화" in str(e), e
    assert rc.user32.IsIconic(me), "최소화된 창을 건드렸다"
    time.sleep(0.5); done.append(1)
    assert not stole, "시험 창이 앞으로 왔다(%r 단계) - 사용자 키가 샌다" % stole
    if os.environ.get("RC_TEST_FOCUS"):   # 이름으로 누르기는 창을 앞으로 가져온다 - 맨 끝에, 키보드를 안 쓸 때만
        assert rc.ui("invoke", "rc selftest", "btnSearch")[0]
        assert rc.ui("get", "rc selftest", "lblResult") == (True, "searched: P-1")

    agent = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", rc.AGENT],
                             creationflags=rc.CREATE_NO_WINDOW)
    assert rc.remote_hello(30), "도우미 READY 가 안 왔다"
    assert rc.remote("ping")[1].startswith("pong")
    assert rc.remote("run", "1 + 1") == (True, "2")
    assert rc.remote("run", 'throw "boom"') == (False, "boom")
    assert rc.remote("get", "rc selftest", "txtLot") == (True, "P-1")
    assert rc.remote("stop") == (True, "bye")
    print("ok")
finally:
    if user_fg[1] and rc.foreground()[0] != user_fg[0] and rc.find_window(user_fg[1]) == user_fg[0]:
        try:
            rc.require_focus(user_fg[1])
        except Exception:
            pass
    form.kill()
    if cover:
        cover.kill()
    if xlp and xlp.poll() is None:
        try:
            xlp.communicate(b"\n", timeout=20)   # 통합 문서를 저장 없이 닫고 엑셀을 끝낸다
        except subprocess.TimeoutExpired:
            xlp.kill()
    if agent and agent.poll() is None:
        time.sleep(1)
        agent.kill()
