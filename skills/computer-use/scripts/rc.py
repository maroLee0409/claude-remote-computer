"""
rc.py — Windows 데스크톱 제어 툴킷 (화면 캡처 + 마우스 + 키보드 + 클립보드)

의존성은 Pillow 하나뿐. 나머지는 ctypes 로 user32/kernel32 를 직접 부른다.
pyautogui 같은 것을 설치하지 않아도 되고, 관리자 권한도 필요 없다.

────────────────────────────────────────────────────────────────────────
좌표계 — 딱 하나만 기억하면 된다
────────────────────────────────────────────────────────────────────────
  **모든 좌표는 "스크린샷 픽셀 좌표"다.**

  혼합 DPI(모니터마다 배율이 다른) 환경에서는 세 종류의 좌표계가 공존한다.
  ImageGrab 래스터 / DPI-aware 가상화면 / DPI-unaware 논리좌표가 전부 다르다.
  이 모듈은 스크린샷 좌표만 받고 내부에서 한 번만 환산한다(`scale()`).
  즉 캡처 이미지에서 눈으로 읽은 좌표를 그대로 넣으면 된다.

────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────
  python rc.py monitors                        모니터 목록(스크린샷 좌표)
  python rc.py windows [필터]                  보이는 창 목록(스크린샷 좌표)
  python rc.py shot out.png                    전체 화면
  python rc.py shot out.png 4480 0 1920 1080   영역 x y w h
  python rc.py shot out.png --window "PowerShell"   해당 창만 잘라서
  python rc.py shot out.png ... --scale 0.6    축소 저장

  python rc.py move   X Y
  python rc.py click  X Y [--focus "창제목"]
  python rc.py dblclick X Y
  python rc.py rclick X Y
  python rc.py scroll N [X Y]
  python rc.py drag X1 Y1 X2 Y2

  python rc.py key ctrl v                      조합키
  python rc.py type "아무 유니코드나"           한 글자씩 입력(느림, 짧은 것만)
  python rc.py clip "클립보드에 넣기"
  python rc.py clipfile path.txt               파일 내용을 클립보드로
  python rc.py getclip [저장경로]               클립보드 읽기
  python rc.py paste "텍스트"                   클립보드+Ctrl+V

  python rc.py focus "창제목일부"               그 창을 확실히 포그라운드로
  python rc.py foreground                      지금 포커스 가진 창 제목
  python rc.py cursor / scale

입력 계열 명령에는 전부 `--focus "창제목일부"` 를 붙일 수 있다.
붙이면 입력 직전에 그 창을 포그라운드로 만들고, 실패하면 **입력을 아예 하지 않고 종료**한다.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import sys
import time

from PIL import ImageGrab

user32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.SetProcessDPIAware()

# 64비트 핸들이 int 로 잘리지 않도록 시그니처를 명시한다. 안 하면 OverflowError.
k32.GlobalAlloc.restype = wt.HGLOBAL
k32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = [wt.HGLOBAL]
k32.GlobalUnlock.restype = wt.BOOL
k32.GlobalUnlock.argtypes = [wt.HGLOBAL]
user32.SetClipboardData.restype = wt.HANDLE
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
user32.GetClipboardData.restype = wt.HANDLE
user32.GetClipboardData.argtypes = [wt.UINT]
user32.GetForegroundWindow.restype = wt.HWND
user32.WindowFromPoint.restype = wt.HWND
user32.WindowFromPoint.argtypes = [wt.POINT]

# ─────────────────────────────────────────────── SendInput 구조체
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, KEYEVENTF_EXTENDEDKEY = 0x0002, 0x0004, 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL = 0x0800
SM_CXVIRTUALSCREEN = 78


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _IU(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _IU)]


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    if user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
        raise OSError("SendInput 실패: %s" % ctypes.get_last_error())


def _p(text, stream=None):
    """콘솔 코드페이지에 없는 글자(이모지·CJK)가 섞여도 안 죽는 출력.

    창 제목에는 이모지가 흔한데, cp949 콘솔에 그냥 print 하면
    UnicodeEncodeError 로 스크립트가 통째로 죽는다.
    """
    stream = stream or sys.stdout
    enc = getattr(stream, "encoding", None) or "utf-8"
    stream.write(str(text).encode(enc, "replace").decode(enc) + "\n")


# ─────────────────────────────────────────────── 좌표 환산
_SCALE = None


def scale():
    """스크린샷 좌표 → 실제 화면 좌표 배율."""
    global _SCALE
    if _SCALE is None:
        _SCALE = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN) / ImageGrab.grab(all_screens=True).size[0]
    return _SCALE


def to_screen(x, y):
    s = scale()
    return int(round(x * s)), int(round(y * s))


def to_shot(x, y):
    s = scale()
    return int(round(x / s)), int(round(y / s))


# ─────────────────────────────────────────────── 창
def foreground():
    """(핸들, 제목) — 지금 키보드 포커스를 가진 최상위 창."""
    h = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return h, b.value


def list_windows(filt=None, min_size=120):
    """보이는 최상위 창들을 [(제목, x, y, w, h)] 로. 좌표는 스크린샷 기준."""
    EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    out = []

    def cb(h, _):
        if not user32.IsWindowVisible(h):
            return True
        n = user32.GetWindowTextLengthW(h)
        if not n:
            return True
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, b, n + 1)
        r = wt.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        x, y = to_shot(r.left, r.top)
        w, hh = to_shot(r.right - r.left, r.bottom - r.top)
        if w < min_size or hh < min_size:
            return True
        if filt and filt.lower() not in b.value.lower():
            return True
        out.append((b.value, x, y, w, hh))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return out


def find_window(substr):
    """제목에 substr 이 들어간 보이는 창 핸들(첫 번째)."""
    EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    found = []

    def cb(h, _):
        if not user32.IsWindowVisible(h):
            return True
        n = user32.GetWindowTextLengthW(h)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, b, n + 1)
            if substr.lower() in b.value.lower():
                found.append(h)
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return found[0] if found else None


def window_rect(substr):
    """창의 (x, y, w, h) — 스크린샷 좌표. shot 의 region 으로 바로 쓸 수 있다."""
    h = find_window(substr)
    if not h:
        return None
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    x, y = to_shot(r.left, r.top)
    w, hh = to_shot(r.right - r.left, r.bottom - r.top)
    return (x, y, w, hh)


def require_focus(substr, tries=6):
    """substr 창을 확실히 포그라운드로. 실패하면 예외 → 입력이 엉뚱한 곳으로 안 간다.

    이게 이 툴킷에서 제일 중요한 안전장치다. 포커스 확인 없이 키를 보내면
    브라우저 주소창이나 남의 문서에 그대로 타이핑된다(실제로 겪음).
    """
    h = find_window(substr)
    if not h:
        raise RuntimeError("창을 찾을 수 없다: %r" % substr)
    for _ in range(tries):
        # 포그라운드 잠금 회피: ALT 를 한 번 눌러주면 SetForegroundWindow 가 먹는다.
        # 주의 - 이 ALT 는 대상 앱에 전달된다(탐색기/오피스는 리본 단축키가 뜬다).
        _kd(VK["alt"]); _ku(VK["alt"])
        user32.SetForegroundWindow(h)
        time.sleep(0.35)
        if foreground()[0] == h:
            return True
    raise RuntimeError("포커스 전환 실패. 현재 포커스: %r" % (foreground()[1],))


def window_at(x, y):
    """스크린샷 좌표 아래에 있는 최상위 창 제목. 클릭 전 확인용."""
    sx, sy = to_screen(x, y)
    h = user32.GetAncestor(user32.WindowFromPoint(wt.POINT(sx, sy)), 2)
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return b.value


# ─────────────────────────────────────────────── 마우스
def move(x, y):
    sx, sy = to_screen(x, y)
    user32.SetCursorPos(sx, sy)
    time.sleep(0.03)


def _btn(down, up, hold=0.04):
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, down, 0, None)))
    time.sleep(hold)
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, up, 0, None)))


def click(x=None, y=None):
    if x is not None:
        move(x, y); time.sleep(0.08)
    _btn(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
    time.sleep(0.15)


def dblclick(x=None, y=None):
    if x is not None:
        move(x, y); time.sleep(0.08)
    _btn(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
    time.sleep(0.06)
    _btn(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
    time.sleep(0.15)


def rclick(x=None, y=None):
    if x is not None:
        move(x, y); time.sleep(0.08)
    _btn(MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
    time.sleep(0.15)


def drag(x1, y1, x2, y2, steps=18):
    move(x1, y1); time.sleep(0.12)
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None)))
    time.sleep(0.1)
    for i in range(1, steps + 1):
        move(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
        time.sleep(0.02)
    time.sleep(0.1)
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None)))
    time.sleep(0.15)


def scroll(amount, x=None, y=None):
    if x is not None:
        move(x, y)
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, int(amount) * 120, MOUSEEVENTF_WHEEL, 0, None)))
    time.sleep(0.1)


def cursor():
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return to_shot(pt.x, pt.y)


# ─────────────────────────────────────────────── 키보드
VK = {
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "back": 0x08, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "capslock": 0x14, "printscreen": 0x2C, "apps": 0x5D,
}
for _i in range(1, 25):
    VK["f%d" % _i] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _c in "0123456789":
    VK[_c] = ord(_c)

EXTENDED = {0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0x5B, 0x5C, 0x5D}


def _kd(vk):
    _send(INPUT(type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(vk, 0, KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0, 0, None)))


def _ku(vk):
    fl = KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0)
    _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, fl, 0, None)))


def key(*names):
    """key('ctrl','v') / key('enter') / key('alt','f4')"""
    vks = [VK[n.lower()] for n in names]
    for v in vks:
        _kd(v); time.sleep(0.02)
    time.sleep(0.05)
    for v in reversed(vks):
        _ku(v); time.sleep(0.02)
    time.sleep(0.12)


def type_unicode(text, delay=0.005):
    """유니코드 직접 주입. 한글/이모지도 IME 없이 들어간다. 느리니 짧은 것만."""
    for ch in text:
        c = ord(ch)
        _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, c, KEYEVENTF_UNICODE, 0, None)))
        _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, c, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)))
        time.sleep(delay)


# ─────────────────────────────────────────────── 클립보드
CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002


def set_clipboard(text):
    buf = ctypes.create_unicode_buffer(text)
    if not user32.OpenClipboard(None):
        raise OSError("OpenClipboard 실패")
    try:
        user32.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(buf))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, buf, ctypes.sizeof(buf))
        k32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            raise OSError("SetClipboardData 실패")
    finally:
        user32.CloseClipboard()


def get_clipboard():
    if not user32.OpenClipboard(None):
        raise OSError("OpenClipboard 실패")
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = k32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            k32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def paste(text):
    """긴 텍스트/한글은 타이핑보다 이 방법이 압도적으로 빠르고 안정적이다."""
    set_clipboard(text)
    time.sleep(0.25)
    key("ctrl", "v")
    time.sleep(0.2)


# ─────────────────────────────────────────────── 화면 캡처
def monitors(warn=True):
    """[(index, x, y, w, h)] — 스크린샷 좌표 기준 모니터 배치.

    주의: 모니터마다 배율이 다르면(예: 주 모니터만 150%) 단일 `scale()` 환산이
    그 모니터에서 어긋난다. 아래에서 모니터 폭 합과 실제 캡처 폭을 비교해
    어긋나면 경고를 찍는다. 경고가 뜨면 이 목록의 좌표를 믿지 말고
    `windows` / `windowrect` 로 대상 창 좌표를 얻어 쓸 것.
    """
    MonEnum = ctypes.WINFUNCTYPE(wt.BOOL, wt.HANDLE, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)
    out = []

    def cb(hmon, hdc, lprc, _):
        r = lprc.contents
        x, y = to_shot(r.left, r.top)
        w, h = to_shot(r.right - r.left, r.bottom - r.top)
        out.append((len(out) + 1, x, y, w, h))
        return True

    user32.EnumDisplayMonitors(None, None, MonEnum(cb), 0)
    if warn and len(out) > 1:
        # 모니터가 가로로 붙어 있는데 환산 결과에 틈/겹침이 생기면
        # 단일 배율 환산이 어긋난 것이다(모니터마다 배율이 다른 경우).
        row = sorted(out, key=lambda m: m[1])
        bad = any(abs(row[i][1] - (row[i - 1][1] + row[i - 1][3])) > 8
                  for i in range(1, len(row)))
        if bad:
            _p("[경고] 모니터 배치에 틈/겹침이 있다 - 모니터별 배율이 다른 환경이다.", sys.stderr)
            _p("       이 목록의 좌표를 믿지 말 것. `windows` / `windowrect` 로"
               " 대상 창 좌표를 얻어 쓰면 정확하다.", sys.stderr)
    return out


def shot(path, region=None, scale_factor=None):
    """region=(x, y, w, h) 스크린샷 좌표. 생략하면 전체.

    ImageGrab 은 가상 데스크톱 래스터를 (0,0) 기준으로 돌려준다.
    DPI-aware GetSystemMetrics 값과 크기가 다를 수 있으므로 오프셋을 빼면 안 된다.
    """
    img = ImageGrab.grab(all_screens=True)
    if region:
        x, y, w, h = [int(v) for v in region]
        img = img.crop((x, y, x + w, y + h))
    if scale_factor and scale_factor != 1:
        img = img.resize((max(1, int(img.width * scale_factor)), max(1, int(img.height * scale_factor))))
    img.save(path)
    return path, img.size


# ─────────────────────────────────────────────── CLI
def main(argv):
    ap = argparse.ArgumentParser(prog="rc.py", add_help=True,
                                 description="Windows 데스크톱 제어. 좌표는 전부 스크린샷 픽셀 기준.")
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--focus", help="입력 전에 이 창을 포그라운드로. 실패하면 입력하지 않고 종료")
    ap.add_argument("--window", help="shot: 이 창 영역만 잘라서 캡처")
    ap.add_argument("--scale", type=float, help="shot: 축소 비율")
    a = ap.parse_args(argv)
    c, rest = a.cmd, a.args

    INPUT_CMDS = {"move", "click", "dblclick", "rclick", "drag", "scroll",
                  "key", "type", "paste"}
    if a.focus and c in INPUT_CMDS:
        require_focus(a.focus)

    if c == "monitors":
        for i, x, y, w, h in monitors():
            _p("  monitor %d :  x=%-6d y=%-6d w=%-6d h=%d" % (i, x, y, w, h))
    elif c == "windows":
        filt = rest[0] if rest else None
        for t, x, y, w, h in list_windows(filt):
            _p("  %6d,%-6d %5dx%-5d  %s" % (x, y, w, h, t[:70]))
    elif c == "shot":
        out = rest[0] if rest else "shot.png"
        region = None
        if a.window:
            region = window_rect(a.window)
            if not region:
                print("창을 찾을 수 없다: %r" % a.window); return 1
        elif len(rest) >= 5:
            region = tuple(int(v) for v in rest[1:5])
        p, size = shot(out, region, a.scale)
        print("saved %s  %dx%d  region=%s" % (p, size[0], size[1], region or "full"))
    elif c == "move":
        move(int(rest[0]), int(rest[1])); print("cursor", cursor())
    elif c in ("click", "dblclick", "rclick"):
        fn = {"click": click, "dblclick": dblclick, "rclick": rclick}[c]
        if len(rest) >= 2:
            _p("클릭 대상 창: " + repr(window_at(int(rest[0]), int(rest[1]))))
            fn(int(rest[0]), int(rest[1]))
        else:
            fn()
        print(c, "at", cursor())
    elif c == "drag":
        drag(*[int(v) for v in rest[:4]]); print("dragged")
    elif c == "scroll":
        scroll(int(rest[0]), *[int(v) for v in rest[1:3]]); print("scrolled")
    elif c == "key":
        key(*rest); print("key", "+".join(rest))
    elif c == "type":
        type_unicode(rest[0]); print("typed %d chars" % len(rest[0]))
    elif c == "paste":
        paste(rest[0]); print("pasted %d chars" % len(rest[0]))
    elif c == "clip":
        set_clipboard(rest[0]); print("clipboard set (%d chars)" % len(rest[0]))
    elif c == "clipfile":
        t = open(rest[0], encoding="utf-8").read()
        set_clipboard(t); print("clipboard set from %s (%d chars)" % (rest[0], len(t)))
    elif c == "getclip":
        t = get_clipboard()
        if rest:
            open(rest[0], "w", encoding="utf-8").write(t)
            print("saved %d chars -> %s" % (len(t), rest[0]))
        else:
            sys.stdout.buffer.write(t.encode("utf-8", "replace"))
    elif c == "focus":
        require_focus(rest[0]); _p("focused: " + repr(foreground()[1]))
    elif c == "foreground":
        _p(repr(foreground()[1]))
    elif c == "windowrect":
        print(window_rect(rest[0]))
    elif c == "cursor":
        print(cursor())
    elif c == "scale":
        print(scale())
    else:
        print("모르는 명령:", c); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
