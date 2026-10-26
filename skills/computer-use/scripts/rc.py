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
  python rc.py shot out.png ... --scale 0.6    축소 저장 (긴 변 1568px 를 넘으면 알아서 줄인다)
  python rc.py shot zoom.png X Y W H --img out.png --scale 3   out.png 에서 읽은 영역을 확대

  python rc.py move   X Y
  python rc.py click  X Y [--focus "창제목"]
  python rc.py click  X Y --img out.png        out.png 에서 읽은 좌표 그대로 (자른 영역·축소를 되돌린다)
  python rc.py dblclick X Y
  python rc.py rclick X Y
  python rc.py scroll N [X Y]
  python rc.py drag X1 Y1 X2 Y2

  python rc.py shot out.png --bg "MES"          뒤에서: 가려진 창도 그 창만 찍는다 (앞으로 안 가져옴)
  python rc.py click X Y --bg "MES" --img out.png   뒤에서: 마우스 안 움직이고 그 창에 클릭 메시지만
                                               dblclick / rclick 도 된다. 최소화된 창은 안 된다
  python rc.py type "글자" --bg "MES"           뒤에서: 그 창의 포커스 칸에 입력.  key enter --bg 도 (키 하나만)
  python rc.py launch "바로가기 이름" [초]       시작 메뉴·바탕화면 바로가기를 일반 권한으로 실행, 새로 뜬 창 제목을 찍는다
                                               이미 떠 있는지는 안 본다 - 먼저 windows 로 확인할 것

  python rc.py key ctrl v                      조합키
  python rc.py type "아무 유니코드나"           한 글자씩 입력(느림, 짧은 것만)
  python rc.py clip "클립보드에 넣기"
  python rc.py clipfile path.txt               파일 내용을 클립보드로
  python rc.py getclip [저장경로]               클립보드 읽기
  python rc.py paste "텍스트"                   클립보드+Ctrl+V

  python rc.py focus "창제목일부"               그 창을 확실히 포그라운드로
  python rc.py foreground                      지금 포커스 가진 창 제목
  python rc.py cursor / scale

  python rc.py waitwin  "제목" [초]             그 창이 뜰 때까지 (기본 10초, 시간 초과면 종료코드 1)
  python rc.py waitgone "제목" [초]             그 창이 닫힐 때까지
  python rc.py waitclip "문자열" [초]           클립보드에 그 문자열이 들어올 때까지 (기본 60초)
  python rc.py waitchange [x y w h] [초]        화면(또는 영역·--window)이 바뀔 때까지. 바뀐 곳 좌표를 찍는다
  python rc.py waitstable [x y w h] [초]        화면이 1초 동안 안 바뀔 때까지 (로딩 끝 대기)

  python rc.py ui controls "창" [필터]          이 PC 창의 컨트롤 목록 (UI Automation, rc-agent.ps1)
  python rc.py ui invoke "창" "조회"            이름/AutomationId 로 누르기 - 좌표 없음
  python rc.py ui get|set "창" "이름" [값]       값 읽기/넣기.  windows / fg / focus / wait 도 된다

  python rc.py remote boot|push|hello          RDP 세션 안에 rc-agent 띄우기 (references/rdp.md)
  python rc.py remote <ui 와 같은 명령>          세션 안에서 실행 - 클립보드로 주고받는다
  python rc.py remote run "PowerShell 코드"     세션 안에서 실행하고 출력 회수.  runfile x.ps1 도 된다

입력 계열 명령에는 전부 `--focus "창제목일부"` 를 붙일 수 있다.
붙이면 입력 직전에 그 창을 포그라운드로 만들고, 실패하면 **입력을 아예 하지 않고 종료**한다.
클릭이면 그 자리를 다른 프로그램의 창이 가리고 있을 때도 누르지 않는다.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import tempfile
import time

from PIL import Image, ImageChops, ImageGrab, PngImagePlugin

user32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
# 모니터별 DPI 인식(v2) - 창 좌표·커서·캡처가 전부 물리 픽셀로 맞아서 모니터마다 배율이 달라도 안 어긋난다.
# Windows 10 1703 이전에는 없으니 예전 방식(시스템 DPI)으로 내려간다.
try:
    if not user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
        user32.SetProcessDPIAware()
except AttributeError:
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
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN = 76, 77, 78


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


def _origin():
    """가상 화면 왼쪽 위. 주 모니터 왼쪽/위에 모니터가 있으면 음수다(예: -2560).
    캡처 래스터의 (0,0) 이 여기라서, 화면 좌표 ↔ 스크린샷 좌표 환산에 꼭 넣어야 한다."""
    return user32.GetSystemMetrics(SM_XVIRTUALSCREEN), user32.GetSystemMetrics(SM_YVIRTUALSCREEN)


def to_screen(x, y):
    s = scale(); ox, oy = _origin()
    return int(round(x * s)) + ox, int(round(y * s)) + oy


def to_shot(x, y):
    s = scale(); ox, oy = _origin()
    return int(round((x - ox) / s)), int(round((y - oy) / s))


def _size(w, h):
    s = scale()
    return int(round(w / s)), int(round(h / s))


# ─────────────────────────────────────────────── 창
def foreground():
    """(핸들, 제목) — 지금 키보드 포커스를 가진 최상위 창."""
    h = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return h, b.value


def _top_windows():
    """보이고 제목이 있는 최상위 창 [(핸들, 제목)], 앞에 있는 것부터."""
    EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    out = []

    def cb(h, _):
        n = user32.GetWindowTextLengthW(h) if user32.IsWindowVisible(h) else 0
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, b, n + 1)
            out.append((h, b.value))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return out


def _rect(h):
    """창 핸들의 (x, y, w, h) — 스크린샷 좌표."""
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return to_shot(r.left, r.top) + _size(r.right - r.left, r.bottom - r.top)


def list_windows(filt=None, min_size=120):
    """보이는 최상위 창들을 [(제목, x, y, w, h)] 로. 좌표는 스크린샷 기준."""
    out = []
    for h, t in _top_windows():
        x, y, w, hh = _rect(h)
        if w >= min_size and hh >= min_size and (not filt or filt.lower() in t.lower()):
            out.append((t, x, y, w, hh))
    return out


def find_window(substr):
    """제목에 substr 이 들어간 보이는 창 핸들(첫 번째)."""
    return next((h for h, t in _top_windows() if substr.lower() in t.lower()), None)


def window_rect(substr):
    """창의 (x, y, w, h) — 스크린샷 좌표. shot 의 region 으로 바로 쓸 수 있다."""
    h = find_window(substr)
    return _rect(h) if h else None


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


def hwnd_at(x, y):
    """스크린샷 좌표 아래에 있는 최상위 창 핸들."""
    sx, sy = to_screen(x, y)
    return user32.GetAncestor(user32.WindowFromPoint(wt.POINT(sx, sy)), 2)


def window_at(x, y):
    """스크린샷 좌표 아래에 있는 최상위 창 제목. 클릭 전 확인용."""
    h = hwnd_at(x, y)
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return b.value


def _pid(h):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def require_clear(substr, x, y):
    """클릭 자리를 다른 프로그램 창이 가리고 있으면 예외.

    같은 프로그램이면 통과시킨다 — 그 앱의 대화상자·드롭다운 목록은 제목이 달라도 눌러야 하니까.
    """
    if _pid(hwnd_at(x, y)) != _pid(find_window(substr)):
        raise RuntimeError("클릭 자리를 다른 프로그램 창이 가리고 있다: %r" % window_at(x, y))


# ─────────────────────────────────────────────── 권한 (UIPI)
# 일반 권한 프로세스가 관리자 권한 창에 보내는 입력·메시지·그리기 요청은 Windows 가 막는다.
# SendInput 은 오류 없이 버려져서 "눌렀는데 안 눌림"이 된다 - 그래서 보내기 전에 권한부터 본다.
advapi = ctypes.WinDLL("advapi32", use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.CloseHandle.argtypes = [wt.HANDLE]
advapi.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
advapi.GetTokenInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
advapi.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
advapi.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
advapi.GetSidSubAuthority.restype = ctypes.POINTER(wt.DWORD)
advapi.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wt.DWORD]


def integrity(pid):
    """프로세스 권한 수준. 0x2000 일반, 0x3000 관리자. 못 읽으면 None."""
    p = k32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION - 관리자 프로세스도 이건 열린다
    if not p:
        return None
    t = wt.HANDLE()
    try:
        buf, n = ctypes.create_string_buffer(64), wt.DWORD()
        if not (advapi.OpenProcessToken(p, 0x8, ctypes.byref(t))                       # TOKEN_QUERY
                and advapi.GetTokenInformation(t, 25, buf, 64, ctypes.byref(n))):        # TokenIntegrityLevel
            return None
        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        return advapi.GetSidSubAuthority(sid, advapi.GetSidSubAuthorityCount(sid)[0] - 1)[0]
    finally:
        if t:
            k32.CloseHandle(t)
        k32.CloseHandle(p)


def require_same_level(h, what):
    """그 창이 rc.py 보다 높은 권한이면 예외 - 보내 봐야 Windows 가 버린다."""
    them, me = integrity(_pid(h)), integrity(os.getpid())
    if them and me and them > me:
        raise RuntimeError("%r 이(가) 관리자 권한으로 떠 있어 Windows 가 입력·캡처를 막는다.\n"
                           "  사용자가 그 프로그램을 닫은 뒤 `rc.py launch \"바로가기 이름\"` 으로 일반 권한으로 다시 띄울 것"
                           " (pitfalls 12)" % what)


# ─────────────────────────────────────────────── 프로그램 띄우기
CSIDL_DESKTOPDIRECTORY, CSIDL_COMMON_DESKTOPDIRECTORY = 0x10, 0x19


def find_shortcut(name):
    """시작 메뉴·바탕화면에서 파일 이름에 name 이 들어간 바로가기(.lnk). 0개·여러 개면 예외."""
    roots = [os.path.join(os.environ.get(v, ""), "Microsoft", "Windows", "Start Menu") for v in ("APPDATA", "PROGRAMDATA")]
    for csidl in (CSIDL_DESKTOPDIRECTORY, CSIDL_COMMON_DESKTOPDIRECTORY):   # OneDrive 로 옮겨진 바탕화면도
        b = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, b) == 0:
            roots.append(b.value)
    hits = {}
    for root in roots:
        for d, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".lnk") and name.lower() in f.lower():
                    hits.setdefault(f.lower(), os.path.join(d, f))   # 시작 메뉴·바탕화면에 같은 게 있으면 하나로
    if len(hits) != 1:
        raise RuntimeError("바로가기 %r 이(가) %s" % (name, "없다" if not hits else "여러 개다: " + ", ".join(sorted(hits))))
    return next(iter(hits.values()))


k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]


def _exe(pid):
    """프로세스 실행 파일 경로. 관리자 프로세스도 읽힌다. 못 읽으면 ''."""
    p = k32.OpenProcess(0x1000, False, pid)
    if not p:
        return ""
    try:
        b, n = ctypes.create_unicode_buffer(1024), wt.DWORD(1024)
        return b.value if k32.QueryFullProcessImageNameW(p, 0, b, ctypes.byref(n)) else ""
    finally:
        k32.CloseHandle(p)


def launch(name, timeout=60):
    """바로가기를 rc.py 와 같은 일반 권한으로 실행. (바로가기 경로, 새로 뜬 창 [(제목, 실행 파일, 권한)])

    화면을 눌러 띄우지 않는다 - 바로가기 실행(ShellExecute)은 더블클릭과 같아서 인자·작업 폴더·
    MSI 광고 바로가기(대상이 C:\\Windows\\Installer 의 아이콘으로 보이는 것)까지 적힌 그대로 뜬다.
    같은 exe 를 인자만 달리해 사이트별로 쓰는 일이 흔해서 '이미 떠 있나'를 exe 로 보지 않는다.

    매니페스트가 관리자를 요구해도(requireAdministrator) RunAsInvoker 로 일반 권한으로 띄운다.
    권한을 올리는 게 아니라 내리는 것이라 UAC 를 건너뛰는 게 아니다. 대신 그 앱이 Program Files 에 쓰는 일
    (자동 업데이트, 실행 중 캐시·설정 저장)은 실패한다. 실행 중에 쓰는 앱이면 깨진다 - pitfalls 12.
    """
    lnk = find_shortcut(name)
    before = {h for h, _ in _top_windows()}

    def new():
        # ponytail: 띄운 뒤 새로 생긴 창을 그 프로그램 것으로 본다. 그사이 다른 프로그램이 창을 띄우면 같이 잡힌다.
        return [(t, _exe(_pid(h)), integrity(_pid(h))) for h, t in _top_windows() if h not in before]

    os.environ["__COMPAT_LAYER"] = "RunAsInvoker"   # 자식 프로세스가 물려받는다
    try:
        os.startfile(lnk)
    finally:
        del os.environ["__COMPAT_LAYER"]
    first = wait_for(new, timeout)
    if not first:
        raise RuntimeError("%d초 안에 새 창이 안 떴다 - 이미 떠 있던 창을 앞으로 올렸을 수 있다(windows 로 볼 것)" % timeout)
    time.sleep(2)   # 업데이트 확인·스플래시 창이 먼저 떴다 닫히는 일이 많다
    return lnk, new() or first


# ─────────────────────────────────────────────── 뒤에서 (--bg) - 창을 앞으로 안 가져온다
# 실제 마우스·키보드를 안 쓰고 그 창에 메시지만 보낸다. 사용자가 다른 일을 해도 안 엉킨다.
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.ChildWindowFromPointEx.restype = wt.HWND
user32.ChildWindowFromPointEx.argtypes = [wt.HWND, wt.POINT, wt.UINT]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]

PW_RENDERFULLCONTENT = 2   # DWM 로 그리는 창(WinForms 포함)도 가려진 채로 찍힌다
CWP_SKIPINVISIBLE, CWP_SKIPTRANSPARENT = 0x1, 0x4
WM_MOUSEMOVE = 0x0200
BG_BTN = {"click": (0x0201, 0x0202, 0x1), "rclick": (0x0204, 0x0205, 0x2)}   # DOWN, UP, MK_*
WM_LBUTTONDBLCLK = 0x0203


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


def bg_window(substr):
    """--bg 대상 창 핸들. 없거나 최소화면 예외 - 최소화된 창은 그리지도 않아서 찍을 수도 누를 수도 없다.

    같은 제목이 여럿이면 다룰 수 있는 것(rc.py 보다 권한이 높지 않은 것)을 고른다 -
    관리자로 뜬 것과 launch 로 다시 띄운 것이 같이 있을 때 앞에 있는 관리자 창을 잡지 않게.
    """
    hits = [h for h, t in _top_windows() if substr.lower() in t.lower()]
    if not hits:
        raise RuntimeError("창을 찾을 수 없다: %r" % substr)
    me = integrity(os.getpid())
    h = next((h for h in hits if (integrity(_pid(h)) or 0) <= (me or 0)), hits[0])
    if user32.IsIconic(h):
        raise RuntimeError("최소화된 창이다 - 뒤로 두는 건 되지만 최소화는 안 된다: %r" % substr)
    require_same_level(h, substr)
    return h


def grab_window(h):
    """그 창만 캡처(PrintWindow). 다른 창에 가려져 있어도 그 창 내용이 찍힌다. 스크린샷 좌표 크기로 돌려준다."""
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    w, hh = r.right - r.left, r.bottom - r.top
    sdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(sdc)
    bmp = gdi32.CreateCompatibleBitmap(sdc, w, hh)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        if not user32.PrintWindow(h, mdc, PW_RENDERFULLCONTENT):
            raise OSError("PrintWindow 실패: %s - 5 면 대상이 관리자 권한이다(pitfalls 12)" % ctypes.get_last_error())
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -hh, 1, 32, 0, 0, 0, 0, 0, 0)  # -hh: 위에서부터
        buf = ctypes.create_string_buffer(w * hh * 4)
        gdi32.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bi), 0)
    finally:
        gdi32.SelectObject(mdc, old); gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(None, sdc)
    img = Image.frombuffer("RGB", (w, hh), buf, "raw", "BGRX", 0, 1)
    return img if scale() == 1 else img.resize(_size(w, hh))


def _class(h):
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, b, 256)
    return b.value


def bg_click(substr, x, y, kind="click"):
    """스크린샷 좌표 (x, y) 를 그 창 안에서 찾아 가장 안쪽 자식 창에 클릭 메시지를 보낸다.

    WindowFromPoint 가 아니라 그 창의 자식만 따라 내려가므로, 다른 창이 위를 덮고 있어도 그 창에 간다.
    """
    top = bg_window(substr)
    sx, sy = to_screen(x, y)
    r = wt.RECT()
    user32.GetWindowRect(top, ctypes.byref(r))
    if not (r.left <= sx < r.right and r.top <= sy < r.bottom):
        raise RuntimeError("그 좌표는 %r 창 밖이다" % substr)
    h = top
    while True:
        pt = wt.POINT(sx, sy)
        user32.ScreenToClient(h, ctypes.byref(pt))
        c = user32.ChildWindowFromPointEx(h, pt, CWP_SKIPINVISIBLE | CWP_SKIPTRANSPARENT)
        if not c or c == h:
            break
        h = c
    lp = (pt.y & 0xFFFF) << 16 | (pt.x & 0xFFFF)
    down, up, mk = BG_BTN["rclick" if kind == "rclick" else "click"]
    msgs = [(WM_MOUSEMOVE, 0), (down, mk), (up, 0)]
    if kind == "dblclick":
        msgs += [(WM_LBUTTONDBLCLK, mk), (up, 0)]
    for m, wp in msgs:
        _post(h, m, wp, lp)   # 관리자 권한으로 뜬 앱엔 못 보낸다(UIPI) - 조용히 안 눌리는 대신 예외로
        time.sleep(0.03)
    time.sleep(0.15)
    covered = _pid(hwnd_at(x, y)) != _pid(top)
    return "%s (%d,%d)%s" % (_class(h), pt.x, pt.y, "  [주의] 그 자리를 %r 이(가) 덮고 있다 - 버튼이면 안 눌린다"
                             "(입력칸은 된다). 덮이지 않게 옮길 것, pitfalls 11" % window_at(x, y) if covered else "")


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND),
                ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND), ("hwndMoveSize", wt.HWND),
                ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]


WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102


def bg_focus(substr):
    """그 창 안에서 키보드 포커스를 가진 컨트롤. 포커스는 스레드마다 따로 기억돼서 창이 뒤에 있어도 남아 있다.

    포커스가 그 창 밖(같은 앱의 다른 대화상자 등)에 있으면 예외 - 글자가 엉뚱한 칸에 들어가지 않게.
    """
    top = bg_window(substr)
    gi = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if not user32.GetGUIThreadInfo(user32.GetWindowThreadProcessId(top, None), ctypes.byref(gi)) or not gi.hwndFocus:
        raise RuntimeError("%r 안에 포커스 가진 칸이 없다 - 먼저 click --bg 로 입력칸을 누를 것" % substr)
    if user32.GetAncestor(gi.hwndFocus, 2) != top:
        raise RuntimeError("포커스가 %r 밖에 있다(%s) - 그 창 제목을 --bg 로 줄 것" % (substr, _class(gi.hwndFocus)))
    return gi.hwndFocus


def _post(h, m, wp, lp):
    if not user32.PostMessageW(h, m, wp, lp):
        raise OSError("PostMessage 실패(%s) - 5 면 대상이 관리자 권한이다(pitfalls 12)" % ctypes.get_last_error())


def bg_type(substr, text):
    """포커스 칸에 글자를 WM_CHAR 로. 한글도 IME 없이 들어간다. (컨트롤 클래스, 글자 수)"""
    h = bg_focus(substr)
    # UTF-16 단위로 보낸다 - 이모지 같은 서로게이트 쌍도 두 번에 나눠 들어가야 맞다. 줄바꿈은 엔터(\r).
    for u in memoryview(text.replace("\r\n", "\n").replace("\n", "\r").encode("utf-16-le")).cast("H"):
        _post(h, WM_CHAR, u, 1)
    time.sleep(0.15)
    return _class(h), len(text)


def bg_key(substr, *names):
    """포커스 칸에 키 하나(enter·tab·f5 등). 조합키는 앱이 실제 키보드 상태(GetKeyState)를 봐서 안 먹는다."""
    if len(names) != 1:
        raise RuntimeError("--bg 로는 키 하나만 된다 - 조합키(ctrl+s 등)는 버튼을 click --bg 로 누를 것")
    vk = VK[names[0].lower()]
    h = bg_focus(substr)
    lp = 1 | user32.MapVirtualKeyW(vk, 0) << 16 | (1 << 24 if vk in EXTENDED else 0)
    _post(h, WM_KEYDOWN, vk, lp)   # 글자 키면 앱의 TranslateMessage 가 WM_CHAR 를 만든다
    time.sleep(0.03)
    _post(h, WM_KEYUP, vk, lp | 0xC0000000)
    time.sleep(0.15)
    return _class(h)


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
        w, h = _size(r.right - r.left, r.bottom - r.top)
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


def grab(region=None):
    """region=(x, y, w, h) 스크린샷 좌표. 생략하면 전체.

    ImageGrab 은 가상 데스크톱 래스터를 (0,0) 기준으로 돌려준다. 스크린샷 좌표가 곧 래스터 좌표이고,
    가상 화면 원점(_origin) 환산은 to_shot / to_screen 이 맡는다.
    """
    img = ImageGrab.grab(all_screens=True)
    if region:
        x, y, w, h = [int(v) for v in region]
        img = img.crop((x, y, x + w, y + h))
    return img


# Claude 는 이보다 큰 이미지를 몰래 줄여서 본다. 그러면 눈으로 읽은 좌표가 실제와 어긋나므로
# 여기서 먼저 줄이고 그 배율을 PNG 에 적어 둔다(--img 가 되돌린다). 토큰도 준다.
MAX_EDGE, MAX_PIXELS = 1568, 1150000


def shot(path, region=None, scale_factor=None, hwnd=None):
    """캡처해서 저장. (경로, 크기, 배율). PNG 면 영역 원점·배율을 'rc' 텍스트로 넣는다.
    hwnd 면 그 창만 PrintWindow 로 찍는다 - region 은 그 창 영역이어야 --img 가 맞는다."""
    img = grab_window(hwnd) if hwnd else grab(region)
    s = min(scale_factor or 1, MAX_EDGE / max(img.size), (MAX_PIXELS / (img.width * img.height)) ** 0.5)
    if s != 1:
        img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))))
    if path.lower().endswith(".png"):
        info = PngImagePlugin.PngInfo()
        info.add_text("rc", "%d %d %.6f" % ((region or (0, 0))[0], (region or (0, 0))[1], s))
        img.save(path, pnginfo=info)
    else:
        img.save(path)
    return path, img.size, s


def img_meta(path):
    """shot 이 PNG 에 적어 둔 (영역 x, 영역 y, 배율)."""
    with Image.open(path) as im:
        m = im.info.get("rc")
    if not m:
        raise RuntimeError("%s 에 좌표 정보가 없다 - rc.py shot 으로 찍은 PNG 여야 한다" % path)
    return tuple(float(v) for v in m.split())


def img_to_shot(path, x, y):
    """그 이미지에서 읽은 좌표 → 스크린샷 좌표."""
    ox, oy, s = img_meta(path)
    return int(round(ox + float(x) / s)), int(round(oy + float(y) / s))


def changed(a, b):
    """두 캡처가 다른 영역 (x0, y0, x1, y1). 같으면 None."""
    bb = ImageChops.difference(a, b).getbbox()
    # ponytail: 폭 3px 이하 변화는 깜빡이는 입력 커서로 보고 무시한다. 얇은 진행 막대도 같이 놓친다.
    return bb if bb and bb[2] - bb[0] > 3 else None


def wait_stable(snap, timeout, quiet=1.0):
    """quiet 초 동안 snap() 캡처가 안 바뀌면 True, 시간 초과면 False."""
    end = time.time() + timeout
    prev, since = snap(), time.time()
    while time.time() < end:
        time.sleep(0.25)
        cur = snap()
        if changed(prev, cur):
            prev, since = cur, time.time()
        elif time.time() - since >= quiet:
            return True
    return False


# ─────────────────────────────────────────────── 기다리기
def wait_for(pred, timeout, every=0.3):
    """pred() 가 참이 될 때까지 짧게 반복 확인. 그 값을, 시간 초과면 None."""
    end = time.time() + timeout
    while True:
        r = pred()
        if r:
            return r
        if time.time() >= end:
            return None
        time.sleep(every)


def _clip_or_empty():
    try:
        return get_clipboard()
    except OSError:  # rdpclip 같은 다른 프로세스가 잠깐 쥐고 있을 때
        return ""


def _clip_starting(prefix):
    c = _clip_or_empty()
    return c if c.startswith(prefix) else None


# ─────────────────────────────────────────────── UI Automation / RDP 도우미 (rc-agent.ps1)
AGENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rc-agent.ps1")
TOKEN_FILE = os.path.join(tempfile.gettempdir(), "rc_agent_token.txt")
# 세션 안 PowerShell 에 붙여넣을 한 줄. 엔터 전에 `remote push` 로 클립보드를 스크립트로 바꿔 두면
# 엔터 순간 클립보드(=스크립트)를 파일로 저장하고 실행한다. 평문이라 AMSI 에 안 걸린다.
BOOT = ('Add-Type -A System.Windows.Forms; $f="$env:TEMP/rc-agent.ps1"; '
        '[Windows.Forms.Clipboard]::GetText() | Set-Content $f -Encoding UTF8; '
        'powershell -NoProfile -ExecutionPolicy Bypass -File $f')


def ui(cmd, *args):
    """이 PC 에서 rc-agent.ps1 을 한 번 실행. (성공여부, 출력)"""
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", AGENT,
                        "-Once", cmd, *args], capture_output=True)
    return r.returncode == 0, r.stdout.decode("utf-8", "replace").strip()


def remote_hello(timeout=60):
    """도우미가 띄운 READY 를 기다려 토큰을 저장. 컴퓨터명, 실패면 None."""
    t = wait_for(lambda: _clip_starting("#RE 0 READY "), timeout)
    if not t:
        return None
    _, _, _, tok, host = t.split()[:5]
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(tok)
    return host


def remote(cmd, *args, timeout=120):
    """RDP 세션 안 rc-agent 에 클립보드로 명령. (성공여부, 출력)"""
    if not os.path.exists(TOKEN_FILE):
        return False, "도우미 토큰이 없다 - 먼저 `remote hello`"
    tok = open(TOKEN_FILE, encoding="utf-8").read().strip()
    seq = str(int(time.time() * 1000))
    set_clipboard("\n".join(["#RC %s %s %s" % (tok, seq, cmd)] + list(args)))
    head = "#RE %s " % seq
    t = wait_for(lambda: _clip_starting(head), timeout)
    if t is None:
        return False, "응답 없음 (%d초). 도우미 창이 살아 있는지, RDP 창이 열려 있는지 확인" % timeout
    status, _, body = t[len(head):].partition("\n")
    return status.strip() == "OK", body


# ─────────────────────────────────────────────── CLI
def main(argv):
    ap = argparse.ArgumentParser(prog="rc.py", add_help=True,
                                 description="Windows 데스크톱 제어. 좌표는 전부 스크린샷 픽셀 기준.")
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--focus", help="입력 전에 이 창을 포그라운드로. 실패하면 입력하지 않고 종료")
    ap.add_argument("--window", help="shot: 이 창 영역만 잘라서 캡처")
    ap.add_argument("--bg", help="shot·click·dblclick·rclick: 이 창을 앞으로 안 가져오고 뒤에서 (가려져 있어도 됨)")
    ap.add_argument("--scale", type=float, help="shot: 축소 비율")
    ap.add_argument("--img", help="좌표를 이 캡처 PNG 에서 읽었다 - 자른 영역·축소를 되돌린다")
    ap.add_argument("--timeout", type=float, default=120, help="remote: 응답 기다리는 시간(초)")
    a = ap.parse_args(argv)
    c, rest = a.cmd, a.args

    def P(x, y):
        return img_to_shot(a.img, x, y) if a.img else (int(x), int(y))

    def region_of(v):
        """[x y w h] → 스크린샷 좌표 영역. --img 면 그 이미지 기준으로 읽은 값이다."""
        x, y = P(v[0], v[1])
        s = img_meta(a.img)[2] if a.img else 1
        return x, y, int(round(float(v[2]) / s)), int(round(float(v[3]) / s))

    INPUT_CMDS = {"move", "click", "dblclick", "rclick", "drag", "scroll",
                  "key", "type", "paste"}
    if a.bg and a.focus:
        _p("--bg 와 --focus 는 같이 못 쓴다 (뒤에서 누를지, 앞으로 가져와 누를지 하나만)"); return 1
    if a.focus and c in INPUT_CMDS:
        if find_window(a.focus):
            require_same_level(find_window(a.focus), a.focus)   # 앞으로 가져오기 전에 - 어차피 입력이 버려진다
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
        region = hwnd = None
        if a.bg:
            hwnd = bg_window(a.bg)
            region = _rect(hwnd)
        elif a.window:
            region = window_rect(a.window)
            if not region:
                print("창을 찾을 수 없다: %r" % a.window); return 1
        elif len(rest) >= 5:
            region = region_of(rest[1:5])
        p, size, s = shot(out, region, a.scale, hwnd)
        _p("saved %s  %dx%d  region=%s  x%.3f%s" % (p, size[0], size[1], region or "full", s,
           "  - 이 이미지에서 읽은 좌표는 --img %s 를 붙여서 넘긴다" % p if region or s != 1 else ""))
    elif c == "move":
        move(*P(rest[0], rest[1])); print("cursor", cursor())
    elif c in ("click", "dblclick", "rclick"):
        fn = {"click": click, "dblclick": dblclick, "rclick": rclick}[c]
        if a.bg:
            if len(rest) < 2:
                _p("--bg 는 좌표가 있어야 한다"); return 1
            _p("뒤에서 %s: %s" % (c, bg_click(a.bg, *P(rest[0], rest[1]), kind=c)))
            return 0
        if len(rest) >= 2:
            x, y = P(rest[0], rest[1])
            _p("클릭 대상 창: " + repr(window_at(x, y)))
            if a.focus:
                require_clear(a.focus, x, y)
            fn(x, y)
        else:
            fn()
        print(c, "at", cursor())
    elif c == "drag":
        drag(*P(rest[0], rest[1]), *P(rest[2], rest[3])); print("dragged")
    elif c == "scroll":
        scroll(int(rest[0]), *(P(rest[1], rest[2]) if len(rest) >= 3 else ())); print("scrolled")
    elif c == "key" and a.bg:
        _p("뒤에서 key %s -> %s" % (rest[0] if rest else "", bg_key(a.bg, *rest)))
    elif c in ("type", "paste") and a.bg:
        _p("뒤에서 typed %d chars -> %s" % bg_type(a.bg, rest[0])[::-1])
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
    elif c in ("waitwin", "waitgone"):
        gone = c == "waitgone"
        sec = float(rest[1]) if len(rest) > 1 else 10
        if not wait_for(lambda: bool(find_window(rest[0])) != gone, sec):
            _p("시간 초과 (%g초): %r" % (sec, rest[0])); return 1
        _p(("gone: " if gone else "found: ") + rest[0])
    elif c == "waitclip":
        sec = float(rest[1]) if len(rest) > 1 else 60
        if not wait_for(lambda: rest[0] in _clip_or_empty(), sec):
            _p("시간 초과 (%g초): 클립보드에 %r 없음" % (sec, rest[0])); return 1
        print("found")
    elif c in ("waitchange", "waitstable"):
        win = a.bg or a.window
        hw = bg_window(a.bg) if a.bg else None
        region = _rect(hw) if hw else window_rect(win) if win else region_of(rest[:4]) if len(rest) >= 4 else None
        if win and not region:
            _p("창을 찾을 수 없다: %r" % win); return 1
        if hw:
            snap = lambda: grab_window(hw)   # 가려져 있어도 그 창만 비교한다
        else:
            snap = lambda: grab(region)
        tail = rest[4:] if len(rest) >= 4 and not win else rest
        sec = float(tail[0]) if tail else 10
        if c == "waitstable":
            if not wait_stable(snap, sec):
                _p("시간 초과 (%g초): 화면이 계속 바뀐다" % sec); return 1
            print("stable")
        else:
            base = snap()
            bb = wait_for(lambda: changed(base, snap()), sec)
            if not bb:
                _p("시간 초과 (%g초): 화면이 안 바뀌었다" % sec); return 1
            ox, oy = (region or (0, 0))[:2]
            print("changed  %d,%d %dx%d" % (ox + bb[0], oy + bb[1], bb[2] - bb[0], bb[3] - bb[1]))
    elif c == "launch":
        lnk, wins = launch(rest[0], float(rest[1]) if len(rest) > 1 else 60)
        me = integrity(os.getpid())
        _p("띄웠다: " + os.path.basename(lnk))
        for t, exe, lv in wins:
            _p("  창 %r  %s%s" % (t, os.path.basename(exe),
               "  [관리자 권한 - rc.py 로 못 다룬다, pitfalls 12]" if lv and me and lv > me else ""))
        _p("  로그인 창이면 사용자가 직접 로그인한다(비밀번호는 넣지 않는다). 이후는 --bg \"창 제목\" 으로")
    elif c == "ui":
        ok, out = ui(*rest)
        _p(out)
        return 0 if ok else 1
    elif c == "remote":
        sub, args = rest[0], rest[1:]
        if sub == "boot":
            set_clipboard(BOOT)
            _p("클립보드 = 시작 한 줄. 세션 안 PowerShell 에 붙여넣고 캡처로 확인 -> 엔터 치기 전에 `remote push`")
        elif sub == "push":
            set_clipboard(open(AGENT, encoding="utf-8-sig").read())
            time.sleep(1)  # RDP 클립보드 동기화 여유
            _p("클립보드 = rc-agent.ps1. 이제 세션 안에서 엔터 -> `remote hello`")
        elif sub == "hello":
            host = remote_hello()
            if not host:
                _p("READY 가 안 왔다 (60초). 세션 안 PowerShell 화면을 캡처해서 오류를 볼 것"); return 1
            _p("연결됨: " + host)
        else:
            if sub == "runfile":
                sub, args = "run", [open(args[0], encoding="utf-8-sig").read()]
            ok, out = remote(sub, *args, timeout=a.timeout)
            _p(out)
            return 0 if ok else 1
    else:
        print("모르는 명령:", c); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
