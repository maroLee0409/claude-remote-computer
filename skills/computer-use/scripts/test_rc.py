"""rc.py 자가 점검.  python test_rc.py

먼저 캡처 좌표 환산(--img)·크기 상한·화면 변화 감지를 입력 없이 확인한다.
그다음 WinForms 시험 창을 띄워 이름으로 넣기·누르기·읽기를 하고(ui),
같은 PC 에 도우미를 띄워 클립보드 왕복(remote)을 확인한다. 클립보드를 덮어쓴다.
InitUia 가 빠지면(pitfalls 10) ui 첫 assert 에서 깨진다.
"""
import os
import subprocess
import tempfile
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

FORM = r"""
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object Windows.Forms.Form; $f.Text = 'rc selftest'
$t = New-Object Windows.Forms.TextBox; $t.Name = 'txtLot'
$b = New-Object Windows.Forms.Button; $b.Name = 'btnSearch'; $b.Text = 'Search'; $b.Top = 40
$l = New-Object Windows.Forms.Label; $l.Name = 'lblResult'; $l.Text = 'ready'; $l.Top = 80
$b.Add_Click({ $l.Text = 'searched: ' + $t.Text })
$f.Controls.AddRange(@($t, $b, $l)); [void]$f.ShowDialog()
"""
COVER = r"""
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object Windows.Forms.Form; $f.Text = 'rc cover'; $f.BackColor = 'Red'; $f.TopMost = $true
$f.StartPosition = 'Manual'; $f.Location = New-Object Drawing.Point(%d, %d); $f.Size = New-Object Drawing.Size(%d, %d)
[void]$f.ShowDialog()
"""


def ps(script):
    return subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])


form = ps(FORM)
agent = cover = None
try:
    assert rc.wait_for(lambda: rc.find_window("rc selftest"), 15), "시험 창이 안 떴다"
    ok, out = rc.ui("controls", "rc selftest", "btn")
    assert ok and "Button | Search | btnSearch" in out, out
    assert rc.ui("set", "rc selftest", "txtLot", "LOT-1")[0]
    assert rc.ui("invoke", "rc selftest", "btnSearch")[0]
    assert rc.ui("get", "rc selftest", "lblResult") == (True, "searched: LOT-1")
    assert not rc.ui("invoke", "rc selftest", "없는것")[0]

    # --bg: 빨간 창이 포그라운드로 오른쪽 절반을 덮은 채 뒤에서 넣고 누르고 찍는다. 포커스를 뺏으면 안 된다.
    def center(line):
        x, y, w, h = map(int, line.rsplit("|", 1)[1].split(","))
        return x + w // 2, y + h // 2
    ctl = {l.split("|")[2].strip(): l for l in rc.ui("controls", "rc selftest")[1].splitlines() if l.count("|") >= 3}
    fx, fy, fw, fh = rc.window_rect("rc selftest")
    cover = ps(COVER % (fx + fw // 2, fy, fw, fh))
    assert rc.wait_for(lambda: rc.find_window("rc cover"), 15), "덮개 창이 안 떴다"
    time.sleep(0.5)
    me = rc.find_window("rc selftest")
    assert rc.foreground()[0] != me
    assert rc.integrity(rc._pid(me)) == rc.integrity(os.getpid()) == 0x2000, "권한 읽기가 틀렸다(관리자로 돌렸다면 일반 권한으로)"
    rc.bg_click("rc selftest", *center(ctl["txtLot"]))
    rc.bg_type("rc selftest", "한글2")
    rc.bg_click("rc selftest", *center(ctl["btnSearch"]))   # 버튼 자리는 안 덮였다 - 덮이면 WinForms 가 Click 을 안 낸다(pitfalls 11)
    assert rc.ui("get", "rc selftest", "lblResult") == (True, "searched: LOT-1한글2")
    img = rc.grab_window(me)
    assert img.getpixel((img.width * 3 // 4, img.height // 2))[:3] != (255, 0, 0), "덮개가 찍혔다"
    assert rc.foreground()[0] != me, "포커스를 뺏었다"

    agent = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", rc.AGENT])
    assert rc.remote_hello(30), "도우미 READY 가 안 왔다"
    assert rc.remote("ping")[1].startswith("pong")
    assert rc.remote("run", "1 + 1") == (True, "2")
    assert rc.remote("run", 'throw "boom"') == (False, "boom")
    assert rc.remote("get", "rc selftest", "lblResult") == (True, "searched: LOT-1한글2")
    assert rc.remote("stop") == (True, "bye")
    print("ok")
finally:
    form.kill()
    if cover:
        cover.kill()
    if agent and agent.poll() is None:
        time.sleep(1)
        agent.kill()
