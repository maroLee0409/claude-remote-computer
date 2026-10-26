# 실제로 당한 함정과 해법

전부 실전에서 겪은 것들이다. 추측이 아니다.

---

## 1. 포커스 유실 — 제일 위험하다

**증상**: 키 입력이 대상 앱이 아니라 엉뚱한 창으로 들어간다.

**실제 사고**: 2.5KB 짜리 PowerShell 명령을 붙여넣고 엔터를 쳤는데, 그 사이 포커스가
Chrome 으로 옮겨가 있어서 **구글 검색어로 전송**됐다. 서버엔 아무 일도 안 일어났고
나는 "왜 실행이 안 됐지" 하며 한참 헤맸다.

**해법**: 입력 계열 명령에 항상 `--focus "창제목일부"` 를 붙인다.
실패하면 예외를 던지고 **입력을 아예 하지 않는다.**

```bash
python "$RC" key enter --focus "PowerShell"
```

**주의**: `require_focus` 는 포그라운드 잠금을 풀려고 ALT 를 한 번 누른다.
이 ALT 가 대상 앱에 전달돼서 **탐색기·오피스에서는 리본 단축키 표시가 뜬다.**
거슬리면 `esc` 한 번 보내면 사라진다.

---

## 2. 혼합 DPI — 좌표가 어긋난다 (지금은 rc.py 가 해결)

**지금**: `rc.py` 는 모니터별 DPI 인식(v2)으로 돌고 가상 화면 원점을 환산에 넣는다.
배율이 달라도, 주 모니터 왼쪽에 모니터가 있어도(원점 -2560 같은 음수) 창 좌표·캡처·클릭이 맞는다.
원점을 빼먹었던 예전 버전은 왼쪽 모니터가 있는 PC 에서 `shot --window` 가 엉뚱한 곳을 잘랐다(실제로 겪음).

아래는 v2 를 못 쓰는 구형 Windows(10 1703 이전)에서만 해당한다.

**증상**: 클릭이 엉뚱한 곳에 들어간다. 특히 배율이 다른 모니터에서.

한 PC 에 세 가지 좌표계가 공존한다:

| | 예시 값 |
|---|---|
| `ImageGrab` 래스터 (내가 보는 것) | 6400 x 1600 |
| DPI-aware `GetSystemMetrics` | 9600 x 1620 |
| DPI-unaware 논리 좌표 | 6400 x 1080 |

`rc.py` 는 `가상화면폭 / 캡처폭` 으로 배율을 구해 스크린샷 좌표만 받는다.
**주 모니터만 150% 같은 혼합 배율이면 이 단일 배율이 그 모니터에서 어긋난다.**

**해법**: `monitors` 가 배치에 틈/겹침을 감지하면 스스로 경고한다.
경고가 뜨면 모니터 좌표를 믿지 말고 **창 기준으로 간다** — 이건 항상 정확하다.

```bash
python "$RC" windowrect "대상창"          # (x, y, w, h)
python "$RC" shot out.png --window "대상창"
```

`click` 은 실행 전에 그 좌표의 창 제목을 찍어준다. 예상과 다르면 멈춰라.

---

## 3. 콘솔 인코딩 — 스크립트가 통째로 죽는다

**증상**: `UnicodeEncodeError: 'cp949' codec can't encode character`

한글 Windows 콘솔은 cp949 다. 창 제목에 흔한 이모지나, 파이썬 `print` 에 넣은
em-dash(`—`) 하나 때문에 스크립트 전체가 죽는다.

**해법**:
- `rc.py` 는 `_p()` 안전 출력을 쓴다(인코딩 불가 문자는 `?` 로 치환).
- 내가 짜는 임시 파이썬 코드에서는 **`print` 에 ASCII 만** 쓴다.
  한글 메시지가 필요하면 파일로 쓰고 `Read` 로 본다.

---

## 4. 백슬래시 접힘 — 이 세션에서만 세 번 당했다

**증상**: `C:\temp` 가 `C:<탭>emp` 가 된다. `\n` 이 진짜 개행이 돼서 문자열이 깨진다.

Bash 툴로 파이썬 코드를 heredoc 에 넣어 보내면 `\\` 가 한 겹 접혀 `\` 가 된다.
그러면 파이썬이 `\t` `\n` 을 이스케이프로 해석해 버린다.

**해법**:
- **경로는 슬래시로 쓴다.** PowerShell 도 `C:/temp/x.ps1` 을 받는다.
- 꼭 백슬래시가 필요하면 `chr(92)` 로 조립한다.
- 만들고 나서 검증한다: `assert chr(9) not in cmd and chr(92) not in cmd`
- 긴 파일은 heredoc 말고 **Write / Edit 툴**로 쓴다. 이게 제일 확실하다.

---

## 5. AMSI 차단

**증상**: `ScriptContainedMaliciousContent` — 백신이 스크립트를 막는다.

gzip+base64 로 압축해서 보내고 원격에서 디코드·실행하는 패턴은
악성코드 난독화와 구분이 안 된다. Defender 가 정확히 그걸 막는다.

**해법**: 평문으로 보낸다. 길면 조각내서 변수에 이어 붙인다.

---

## 6. 캔버스·WebGL 캡처가 빈 이미지

**증상**: `toDataURL()` 결과가 단색이다.

WebGL 은 `preserveDrawingBuffer: false` 가 기본이라
**그린 직후(`requestAnimationFrame` 콜백 안)에만** 캔버스를 읽을 수 있다.
`setTimeout` 안에서 읽으면 버퍼가 이미 비어 있다.

```javascript
// 나쁨 - 버퍼가 비어 단색이 나온다
requestAnimationFrame(() => setTimeout(shot, 900));

// 좋음 - 기다린 뒤 rAF 안에서 읽는다
setTimeout(() => requestAnimationFrame(shot), 2000);
```

빈 프레임인지 판정하려면 축소본의 색 종류를 센다. 1~2종이면 아직 안 그려진 것이다.

---

## 7. 콘솔 붙여넣기가 이전 줄에 이어붙는다

**증상**: 두 명령이 `...HH:mm:ss')"cls; $a=Get-...` 처럼 한 줄로 합쳐져 파싱 오류.

앞 명령이 실행되지 않고 프롬프트에 남아 있는데 그 위에 또 붙여넣으면 이렇게 된다.

**해법**: 붙여넣기 전에 `esc` 로 줄을 비운다. 그리고 **엔터 전에 캡처해서 확인**한다.

---

## 8. 클릭했는데 아무 일도 안 일어난다

체크 순서:

1. 좌표가 맞나 — `click` 이 찍어준 대상 창 제목 확인
2. 포커스가 맞나 — `foreground` 로 확인
3. 창이 움직였나 — `windowrect` 로 다시 확인
4. 대화상자가 떠서 가리고 있나 — 전체 캡처해서 확인
5. 콘솔이라면 QuickEdit 선택 모드로 멈춰 있나 — `esc` 로 해제

---

## 9. 오래 걸리는 작업 기다리기

블로킹 `sleep` 을 길게 걸지 말고, 조건이 나타날 때까지 짧게 반복 확인한다.
이제 `waitwin` / `waitgone` / `waitclip` 이 그 반복을 해준다(RDP 도우미는 `remote` 가 알아서 기다린다).
클립보드로 결과를 받는다면 "내가 보낸 명령 텍스트가 아직 그대로인가"로
아직 실행 중인지 판별할 수 있다. 직접 짤 때는 이렇게:

```python
for _ in range(12):
    time.sleep(15)
    t = rc.get_clipboard()
    if '완료표시' in t:
        break
```

---

## 10. PowerShell 에서 UI Automation 을 쓰면 컨트롤이 전부 이름 없는 Pane

**증상**: WinForms·Win32 앱의 버튼·입력칸이 전부 `Pane`, 패턴 없음, AutomationId 는 숫자(창 핸들).
같은 코드를 컴파일한 exe 로 돌리면 `Button | btnSearch | InvokePattern` 으로 정상이다.

**원인**: UIA 의 `ProxyManager.LoadDefaultProxies` 가 호출자 스택을 거슬러 올라가며 호출한 어셈블리를 찾는데,
powershell.exe 에서는 그 자리가 PowerShell 동적 메서드(ReflectedType=null)라 NullReferenceException 이 나고
Win32/WinForms 프록시가 안 올라온다. 예외는 삼켜져서 겉으로는 안 보인다.

**해법**: Add-Type 으로 컴파일한 메서드에서 UIA 를 **먼저 한 번** 부른다. `rc-agent.ps1` 의 `InitUia()` 가 그것이다.
직접 PowerShell 로 UIA 코드를 짤 때도 똑같이 해야 한다.

---

## 11. 뒤에서(`--bg`) 눌렀는데 버튼만 안 눌린다 — 그 자리가 다른 창에 덮여 있다

**증상**: `click --bg` 로 입력칸을 누르고 `type --bg` 로 넣는 건 되는데, 버튼을 누르면 아무 일도 없다.
오류도 안 난다. 같은 버튼이 창이 안 덮여 있을 때는 눌린다(포그라운드가 아니어도).

**원인**: WinForms 는 마우스를 뗄 때 `WindowFromPoint(그 자리) == 내 핸들` 일 때만 Click 을 낸다.
화면에서 그 자리를 다른 창이 덮고 있으면 메시지는 받아도 Click 을 버린다. MES 의 직접 그린 버튼도 같다.
글자 입력(WM_CHAR)·네이티브 입력칸 클릭은 이 검사가 없어서 덮여 있어도 된다.

**해법**: 대상 창을 **덮이지 않는 곳**에 둔다 — 앞으로 올 필요는 없고, 누를 자리만 보이면 된다.
예: 사람은 1번 모니터에서 일하고 MES 는 2번 모니터에 둔다. 표준 `Button` 이면 `ui invoke` 가 덮여 있어도 된다(PerformClick).
누른 뒤에는 `shot --bg` 로 정말 바뀌었는지 확인한다 - 안 눌려도 오류가 없기 때문이다.

---

## 12. 관리자 권한으로 뜬 앱은 아무것도 안 먹는다 (UIPI)

**증상**: `shot --bg` 가 `PrintWindow 실패: 5`, `click --bg` 가 `PostMessage 실패(5)`.
`click`·`key`(SendInput)는 **오류 없이 조용히 무시된다** — 눌렀다고 찍히는데 화면이 안 바뀐다.
`ui controls` 로 이름 읽기는 되니 더 헷갈린다.

**원인**: 대상 앱이 관리자 권한(High)이고 rc.py 는 일반 권한(Medium)이다. Windows 는 낮은 권한에서
높은 권한 창으로 가는 입력·메시지·그리기를 막는다. 관리자로 뜨는 길은 셋이다:
매니페스트 `requireAdministrator`(띄울 때마다 UAC 창), 바로가기·호환성 탭의 "관리자로 실행", 사용자가 우클릭 → 관리자로 실행.
업무 프로그램은 `Program Files` 에 자동 업데이트를 쓰려고 매니페스트로 관리자를 요구하는 일이 많다.

**확인**: rc.py 가 보내기 전에 권한을 비교해서 `관리자 권한으로 떠 있어 Windows 가 입력·캡처를 막는다` 로 멈춘다
(`--bg` 전부, `--focus` 를 붙인 입력 - 창을 앞으로 가져오기 전에). 손으로 볼 때는 `Get-Process 이름 | Select Path` 의 Path 가 비어 나온다.

**해법**: `rc.py launch "바로가기 이름"` — `__COMPAT_LAYER=RunAsInvoker` 로 매니페스트의 관리자 요구를 무시하고 일반 권한으로 띄운다.
권한을 내리는 것이라 UAC 우회가 아니다. 대가: 그 앱의 관리자 전용 기능은 실패한다 — 대표적으로 `Program Files` 에 쓰는 자동 업데이트.
업데이트가 뜨면 사용자가 원래 바로가기로 한 번 띄워 받고 닫은 뒤 다시 `launch`.
이미 관리자로 떠 있는 것은 일반 권한에서 닫을 수도 없다(WM_CLOSE 도 막힌다) — 사용자가 닫는다.
Claude Code 를 관리자로 띄우는 것도 된다 — 다만 에이전트가 돌리는 모든 명령이 관리자 권한이 되니, 사용자가 고를 일이다.
실행 중에 설치 폴더에 쓰는 앱(아래)이면 현실적인 길이다.

**실제로 겪은 것**:
- 매니페스트를 정규식 첫 번째 `level="..."` 로 읽어 `asInvoker` 라고 잘못 판단했다. Visual Studio 매니페스트 템플릿은
  **주석 안에** `asInvoker`·`requireAdministrator`·`highestAvailable` 예시가 먼저 나온다. 주석 밖의 것을 봐야 한다.
  `CreateProcess` 가 `WinError 740`(권한 상승 필요)을 내면 그게 답이다.
- 같은 이름의 실행 파일이 설치본마다 달랐다(데모 설치본은 `asInvoker`, 사이트 설치본은 `requireAdministrator`).
  실제로 뜬 프로세스의 경로(`QueryFullProcessImageName`)로 확인할 것.
- 사이트 바로가기가 MSI 광고 바로가기라 대상이 `C:\Windows\Installer\{GUID}\...exe`(아이콘)로 보였다. 실행 파일 이름으로 창을 찾으면 못 찾는다.
- **RunAsInvoker 로 띄운 MES 가 로그인 직후 "Browser 환경 설정 중" 에서 `개체 참조가 개체의 인스턴스로 설정되지 않았습니다` 로 깨졌다.**
  이 MES 는 업데이트 때만이 아니라 **로그인할 때마다** 설치 폴더에 쓴다 — 서버에서 받은 화면 DLL 캐시(`BusinessApp\...`)와 `config.cfg`.
  일반 권한으로 내려 띄우기는 실행 중에 자기 설치 폴더에 안 쓰는 앱에만 통한다.
  확인법: 관리자로 한 번 정상 사용한 뒤 설치 폴더에서 방금 바뀐 파일을 본다(`Get-ChildItem -Recurse | sort LastWriteTime`).
  그런 앱이면 남는 길은 셋이다 — 앱을 사용자 폴더에 복사해 거기서 띄우기 / 사용자가 설치 폴더에 쓰기 권한 주기 / Claude 를 관리자로.
  `docs/design-background-control.md` 의 "권한 문제".

---

## 13. 되돌릴 수 없는 조작

파일 삭제, 설정 변경, 결제, 메일 전송, 서비스 재시작.
**먼저 물어라.** 특히 운영 서버라면.

가능하면 이렇게 한다:
- dry-run 을 먼저 돌려 무엇이 바뀔지 보여준다
- 백업을 남긴다 (`Copy-Item $p ($p + '.bak')`)
- 자동 검증 + 자동 롤백을 한 덩어리로 만든다
