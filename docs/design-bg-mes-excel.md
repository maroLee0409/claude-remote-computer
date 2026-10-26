# MES ↔ 엑셀을 뒤에서 오가기 — 설계 기록

`--bg` 로 MES 를 다루는 것까지는 됐는데, **MES 와 엑셀 사이에서 값을 옮기는 일**은 여전히 진짜 입력(`--focus` + `SendInput`)으로
돌아가고 있었다. 사용자 말: "내 마우스 키보드를 건드리지 않는 것까지는 테스트 했는데, MES 와 엑셀을 직접 작업할 때는 건드린다."
무엇이 막고 있었는지, 실험으로 무엇이 됐고 무엇이 안 됐는지, 그래서 어떻게 만들지를 남긴다.
`design-background-control.md` 를 먼저 읽을 것 — 그 위에 얹는 설계다.

## 요구

1. **사용자의 마우스·키보드·포커스·클립보드를 건드리지 않는다.** MES 와 엑셀 둘 다.
2. **옮길 수 있어야 한다.** MES 입력칸 값 읽기·쓰기, MES 그리드 여러 행 가져오기, 엑셀 범위 읽기·쓰기.
3. **못 하면 멈춘다.** 앞으로 가져와 누르는 것으로 넘어가지 않는다(원래 원칙).
4. 의존성은 그대로 Pillow 하나. 나머지는 ctypes 와 이미 쓰는 PowerShell 하위 프로세스.

## 왜 막혀 있었나

| 막힌 곳 | 원인 |
|---|---|
| 그리드 복사·붙이기 | Ctrl+C·Ctrl+V 가 `--bg`(PostMessage)로 안 먹는다. 앱이 `GetKeyState` 로 **진짜 키보드 상태**를 본다 |
| 입력칸 내용 바꾸기 | Ctrl+A 가 같은 이유로 안 된다 → 기존 글 뒤에 덧붙게 된다 |
| 엑셀 | `--bg` 경로가 아예 없다. `--focus` 로 앞으로 가져와 Ctrl+V 를 치고 있었다 |
| 클립보드 | 쓰면 사용자가 복사해 둔 것이 사라지고, 그사이 사용자가 복사하면 섞인다 |
| 최소화된 MES | 맨 뒤에 복원하는 변경(미커밋)이 `test_rc.py` 106행에서 "복원하면서 포커스를 가져왔다"로 깨진다 |

## 검토한 방법

| 작업 | 방법 | 결과 |
|---|---|---|
| 조합키 | `WM_KEYDOWN(VK_CONTROL)` 뒤 `WM_KEYDOWN('C')` 만 Post | **안 된다.** Post 한 키 메시지는 키 상태를 안 바꾼다. 게다가 Ctrl 없는 `C` 가 `WM_CHAR 'c'` 가 돼 **그리드 셀에 c 가 타이핑**됐다(편집 모드 진입). 조합키를 조용히 낱키로 떨어뜨리면 사고다 |
| 조합키 | `AttachThreadInput(내 스레드, 그 창 스레드)` + `SetKeyboardState(Ctrl=눌림)` + `WM_KEYDOWN('C')` Post, 끝나면 원복·Detach | **채택.** DataGridView 에서 Ctrl+C·Ctrl+A 가 먹었다. 내 쪽(=사용자 쪽) `GetAsyncKeyState`·`GetKeyState` 의 Ctrl 은 안 바뀌었고 포그라운드도 그대로 |
| 조합키 | `SendMessage` 로 동기 전송 | 안 쓴다. WinForms 의 `ProcessCmdKey`(단축키)는 메시지 루프가 **꺼낸** 메시지에만 돈다. Post 여야 한다 |
| 입력칸 바꿔 넣기 | `EM_SETSEL(0,-1)` 뒤 `WM_CHAR` | **채택.** 포커스 없이 EDIT 핸들에 직접 보내도 됐고 `TextChanged` 도 났다. Ctrl+A 가 필요 없다 |
| 입력칸 쓰기 | `WM_SETTEXT` (`SendMessageTimeout`) | 된다(프로세스 경계를 넘어 마샬링됨, `TextChanged` 남). 단 ctypes 버퍼의 참조를 쥐고 있어야 한다 — 임시 객체면 보내기 전에 해제돼 빈 글이 들어간다(실제로 당함). `EM_REPLACESEL` 은 마샬링이 안 돼 빈 글이 들어간다 |
| 입력칸 읽기 | `WM_GETTEXTLENGTH`+`WM_GETTEXT` (`SendMessageTimeout`) | **채택.** 포커스·클립보드 없이 읽힌다. `ui get`(UIA)도 되지만 PowerShell 한 번(≈1초)이 든다 |
| 입력칸 복사·붙이기 | `WM_COPY` / `WM_PASTE` | 된다, 포커스 없이도. 하지만 입력칸은 위 두 방법이면 충분해 클립보드를 안 쓴다 |
| 그리드 읽기 | UIA `ui controls` / `ui get "QTY 행 1"` | DataGridView 는 셀이 `Custom | QTY 행 1` 로 잡히고 `ui get` 이 `20` 을 돌려줬다. **클립보드 없이** 읽힌다. DevExpress GridControl 은 미확인 → 되면 이쪽을 먼저 쓴다 |
| 그리드 읽기 | 셀 클릭 → Ctrl+A → Ctrl+C(위 attach 방식) → 클립보드 | **채택(UIA 가 안 잡힐 때).** 3행이 `LOT-A\t10\r\nLOT-B\t20\r\n…` 로 왔다. 클립보드는 "빌려 쓰기"(아래) |
| 엑셀 읽기·쓰기 | COM `Range.Value2` (PowerShell) | **채택.** 떠 있는 엑셀에 `GetActiveObject` 로 붙고, 2차원 배열로 한 번에 읽고 쓴다. 읽기 3~5ms. 한글 왕복 OK. 숫자 문자열은 Excel 이 숫자로 바꿔 넣는다. **포그라운드가 안 바뀐다**(창이 보이는 채로 뒤에 있어도) |
| 엑셀 인스턴스 고르기 | 창 핸들 → `XLDESK` → `EXCEL7` → `AccessibleObjectFromWindow(OBJID_NATIVEOM)` → `.Application` | 된다(같은 프로세스·다른 프로세스 모두). 엑셀이 여럿일 때 **창 제목으로** 고르는 길이고, ROT 가 안 될 때(권한 다름) 대안 |
| 엑셀 새 창 | `Visible = $true` | **포그라운드를 뺏는다.** 대신 `ShowWindow(SW_SHOWNOACTIVATE)` 로 보이게 하면 안 뺏는다 — 다만 사용자 엑셀은 이미 떠 있으니 보통 필요 없다 |
| 최소화된 창 복원 | `SetWindowPos(HWND_BOTTOM)`+`SW_SHOWNOACTIVATE` 등 5가지 | **기각.** 복원하는 창이 그 스레드의 활성 창(`hwndActive`)이면 — `click --bg` 한 번 했으면 늘 그렇다 — 복원이 포그라운드를 가져온다. 아래 "한계 1" |
| 포그라운드 잠금 | `LockSetForegroundWindow(LSFW_LOCK)` 을 걸고 조작 | **기각.** rc.py 에서 오류 5(권한 없음). 포그라운드 프로세스만 걸 수 있다 |
| 엑셀 바쁠 때 | 모달 대화상자를 띄워 두고 다른 프로세스에서 호출 | `RPC_E_CALL_REJECTED (0x80010001)` 로 **즉시** 거절된다. 안 멈춘다. 셀 편집 중도 같을 것(추정) → 짧게 재시도하고 멈춘다 |

## 채택한 설계

| 작업 | 방법 | 확인 |
|---|---|---|
| MES 입력칸 읽기 | `ui get` (UIA). `WM_GETTEXT` 로도 된다(확인) - 따로 명령은 안 만들었다 | WinForms TextBox 확인. DevExpress TextEdit 안쪽 EDIT — 추정 |
| MES 입력칸 쓰기 | `key ctrl a --bg` 뒤 `type --bg`, 또는 `ui set`(Win32 입력칸은 `WM_SETTEXT`) | 확인. DevExpress `EditValue` 반영(포커스가 빠질 때 확정)은 추정 → 넣은 뒤 `key tab --bg` |
| MES 조합키 | `key ctrl c --bg "MES"` (attach + SetKeyboardState) | DataGridView 확인. DevExpress 는 같은 `Control.ModifierKeys`(=GetKeyState) 를 쓰니 될 것 — 추정 |
| MES 그리드 복사 | ① `ui controls "MES" 행` 으로 셀이 잡히면 `ui get` ② 아니면 셀 `click --bg` → (`key ctrl a --bg`) → `copy --bg "MES"` (클립보드 빌려 Ctrl+C → 내용 반환 → 복원) | ① DataGridView 확인, DevExpress 미확인 ② DataGridView 확인 |
| MES 그리드 붙이기 | `paste "TSV" --bg "MES"` (클립보드 빌려 Ctrl+V → 복원). 그리드가 붙이기를 지원 안 하면 셀마다 `click --bg` → `type --bg --replace` → `key tab --bg` | DataGridView 는 기본 붙이기가 없어 미확인. DevExpress 는 버전에 따라 다름 — MES 에서 확인 |
| 엑셀 읽기 | `xl get "A1:C10" [--book "제목일부"] [--sheet "이름"]` → TSV 표준출력 | 확인 (새 인스턴스·새 통합 문서) |
| 엑셀 쓰기 | `xl set "A1" "a\tb\nc\td"` / `xl set "A1" @file.tsv` → `Resize(행,열).Value2 = 배열` | 확인 |
| 엑셀 고르기 | 늘 창 경로: 창 제목(`--book`, 하나면 생략) → `EXCEL7` → `AccessibleObjectFromWindow`. ROT 는 안 쓴다 | 확인(같은 권한). Claude 관리자 + 엑셀 일반 권한은 추정 — ROT 는 이때 갈린다고 알려져 있어 안 쓴다 |
| 엑셀 바쁨 | `0x80010001` 이면 1초 간격 3번 재시도 뒤 "엑셀이 바쁘다(셀 편집 중·대화상자)" 로 멈춘다 | 대화상자 확인, 셀 편집 추정 |
| 최소화된 창 | **복원하지 않는다.** "최소화된 창이다 — 사용자가 복원해 둘 것" 으로 멈춘다 | 복원이 뺏는 것 확인. `SetWindowPos(NOACTIVATE)` 이동은 안 뺏는다(확인) - `move` 명령은 안 만들었다 |
| 녹화 중 최소화 | 복원하지 않고 "최소화됐다" 로 거기까지 저장 | — |
| 클립보드 | 빌려 쓴다: 글이면 저장 → 쓰기 → `GetClipboardSequenceNumber` 로 그사이 사용자가 바꿨는지 확인 → 안 바꿨으면 복원. 글이 아닌 것(파일·그림)이 들어 있으면 복원 못 하니 **시작하지 않고 묻는다** | 순번 비교 확인 |

좌표는 그대로 스크린샷 기준(`--img`). `gettext X Y` 도 `click --bg` 와 같은 "그 창의 자식만 따라 내려가기"로 컨트롤을 찾는다.

## 해 보고 알게 된 한계

1. **최소화된 창을 복원하면 포그라운드를 가져온다.** 그 창이 그 스레드의 활성 창일 때 — `click --bg` 로 입력칸을 한 번이라도
   눌렀으면 그 상태다. `SW_SHOWNOACTIVATE`·`ShowWindowAsync`·`SetWindowPlacement`, 맨 뒤로 먼저 보내기, 전부 같았다(WinForms).
   한 번도 활성화된 적 없는 창(순수 Win32 시험 창, 활성 창이 NULL)은 안 뺏었다 — 그래서 처음엔 되는 줄 알았다.
   되돌리려고 `SW_MINIMIZE` 를 하면 이전 창으로 돌아가기도 하고, **최소화된 채 포그라운드를 쥔 채로 남기도 한다**(시험 3번 중 2번).
   그 상태에선 사용자 키가 안 보이는 창으로 들어간다. → 복원 자체를 안 한다. `show_behind`·`_minimize_again` 은 지운다.
2. **`click --bg` 도 창을 앞으로 가져올 때가 있다.** 입력칸을 누르면 EDIT 가 `SetFocus` → 창 활성화인데, Windows 가 그 프로세스에
   포그라운드 권리를 주는 조건이면 포그라운드까지 간다. 같은 시험 창·같은 클릭이 어떤 때는 뺏고(사용자가 Chrome 을 읽고 있을 때 2/8),
   어떤 때는 안 뺏었다(사용자가 Claude 에 입력 중일 때 0/6). rc.py 자신의 창에선 매번 뺏었다(Claude 의 자식 프로세스라 권리가 있는 듯).
   실제 MES 에서 지금까지 안 뺏긴 건 운이 섞여 있다. 조건을 정확히 못 밝혔다 → **막지 못하니 감지한다**(안전 원칙 1).
   피할 수 있는 곳은 피한다: 글 읽기·쓰기는 포커스 없이 컨트롤에 직접 보낸다(`gettext`, `type X Y --bg`, `WM_SETTEXT`). 클릭은 그리드 셀·버튼에만.
3. **`SetKeyboardState` 는 붙인 스레드가 보는 상태만 바꾼다.** 그래서 안전한데, 거꾸로 **대상 창이 포그라운드면**(사용자가 MES 를 쓰는 중)
   붙이는 순간 사용자의 키가 Ctrl 눌린 것으로 보인다 → `--bg` 는 대상이 포그라운드일 때 아예 거부한다.
4. **클립보드에 넣은 직후 `WM_PASTE` 가 빈 글을 붙인다.** 클립보드 기록(Win+V) 서비스가 바뀐 직후 잠깐 쥐고 있어서 앱의 `OpenClipboard` 가
   실패하고, 선택 영역만 지워진다. `paste()` 에 이미 있는 0.25초 대기가 그 이유였다. 붙이기 전엔 반드시 기다린다.
5. **엑셀 `Visible = $true` 는 포그라운드를 뺏는다.** 사용자 엑셀에 붙을 땐 상관없고, Claude 가 새 인스턴스를 띄워야 하면 `ShowWindow(SW_SHOWNOACTIVATE)`.
   `Workbooks.Add` 로 새 통합 문서 창을 여는 게 뺏는지는 못 봤다 — 새 통합 문서는 사용자가 연다.
6. **숨긴 엑셀엔 `EXCEL7` 창이 없다.** 창 핸들 경로(`--book`)는 보이는 엑셀에만 통한다. `FindWindowEx` 로 바로 못 찾을 때가 있어 자식을 훑는다.
7. **엑셀이 바쁘면 호출이 거절된다(`0x80010001`).** 멈추진 않는다. 주의: 그때 `Quit` 도 거절돼 Claude 가 띄운 인스턴스가 남는다 → 띄웠으면 끝에 반드시 확인.
8. 클립보드는 **사용자 것을 건드리는 게 맞다.** 전역 자원이라 피할 수 없다. 그래서 (a) 다른 길이 있으면 안 쓴다(입력칸·엑셀은 안 쓴다)
   (b) 쓰면 1초 안에 돌려놓는다 (c) 그사이 사용자가 복사했으면 사용자 것을 남긴다 (d) 글이 아닌 것이 있으면 시작 안 한다.

## 안전 원칙

- **창이 앞으로 왔으면 멈춘다.** `--bg` 입력(click·type·key·copy·paste) 전후로 `GetForegroundWindow` 를 비교해, 대상 창이 포그라운드가 됐으면
  종료코드 1 과 "창이 앞으로 왔다 — 사용자 키가 이 창으로 간다. 사용자가 자기 창을 다시 누르면 계속" 을 찍는다. 되돌리려 하지 않는다(`SW_MINIMIZE` 가 더 나쁘게 만든다, 한계 1).
- **대상이 포그라운드면 `--bg` 를 거부한다.** 사용자가 지금 그 창을 쓰고 있다. 키 상태를 건드리면 안 된다(한계 3).
- **조합키는 키 상태 원복·Detach 를 `finally` 로.** 예외가 나도 Ctrl 이 눌린 채로 남지 않게. Attach 가 실패하면(권한 다름) 아무것도 보내지 않는다.
- **최소화면 멈춘다.** 복원하지 않는다. `move` 는 활성화 없이 자리만 옮긴다.
- **클립보드는 빌리고 돌려준다.** 순번(`GetClipboardSequenceNumber`)이 내가 올린 만큼만 올라 있어야 복원한다. 아니면 사용자 것이 더 새것이니 두고, 보고한다.
- **엑셀은 `Value2` 만.** `Select`·`Activate`·`Copy`·`Visible` 처럼 창·선택을 건드리는 멤버는 쓰지 않는다. 바쁘면 3번 재시도 뒤 멈춘다. 저장(`Save`)은 사용자가 시킬 때만.
- **권한 비교는 그대로.** `require_same_level` 뒤에만 보낸다. Claude 가 관리자면 엑셀(일반)은 ROT 가 아니라 `--book` 경로로.

## 만든 것 (설계안에서 줄인 것 포함)

```
python rc.py key ctrl c --bg "MES"                 # ctrl·shift + 키 하나. alt·win 은 안 된다
python rc.py copy --bg "MES" [out.tsv]             # 클립보드 빌려 Ctrl+C -> 글 -> 돌려놓기. 여러 행은 먼저 key ctrl a --bg
python rc.py paste "TSV|@file" --bg "MES"          # 클립보드 빌려 Ctrl+V -> 돌려놓기 (예전 paste --bg 는 type 과 같았다)
python rc.py xl get "A1:C10" [--book "제목 일부"] [--sheet "시트"]   # TSV 표준출력
python rc.py xl set "A1" "TSV|@file" [--book] [--sheet]             # 넣은 범위 주소를 찍는다. 저장 안 함
```

- rc.py: `_fg_guard`(보내기 전·후 포그라운드), `_held`(AttachThreadInput + SetKeyboardState, finally 로 원복),
  `_sync`(WM_NULL 왕복 - 앱이 키를 다 꺼낼 때까지 Ctrl 을 쥔다), `bg_key`(조합), `bg_copy`·`bg_paste`(`_clip_save`·`_clip_restore`),
  `xl_window`(XLMAIN 제목 → EXCEL7), `xl_get`·`xl_set`. 최소화 복원(`show_behind`)은 지웠다.
- rc-agent.ps1: `xlget`·`xlset`(창 → `AccessibleObjectFromWindow` → `Value2`, `0x80010001` 3번 재시도). 결과는 파일로 주고받는다 —
  표준출력은 `Out-String`·`TrimEnd` 를 거쳐 줄 끝 빈 칸이 잘린다.
- 엑셀은 ROT(`GetActiveObject`)를 안 쓰고 늘 창 경로로 간다. 길이 하나면 관리자 Claude 에서도 같은 코드가 돈다.
  `--book` 이 없으면 엑셀 창이 하나일 때만 — 여럿이면 엉뚱한 통합 문서에 쓰지 않게 멈춘다.
- 안 만든 것: `gettext`(→ `ui get`), `type --replace`(→ `key ctrl a --bg` 뒤 `type --bg`), `type X Y`(클릭 없는 입력), `move`, `xl books`
  (→ `xl` 이 창이 여럿이면 제목 목록을 찍는다). 실제 MES 에서 필요해지면 그때.

## 구현하며 더 알게 된 것

시험을 사용자가 채팅을 치는 동안 돌렸더니 **사용자가 친 글자가 시험 창에 들어갔다.** 원인을 하나씩 잡았다(`pitfalls.md` 15):

| 앞으로 오게 한 것 | 얼마나 | 한 일 |
|---|---|---|
| `ui set`(`ValuePattern.SetValue`) | 매번 | Win32 입력칸이면 `WM_SETTEXT` 로 바꿨다 - 포커스를 안 옮긴다 |
| `ui invoke`(`InvokePattern`) | 매번 | 뒤에서는 `click --bg` 를 쓰라고 문서에. rc.py 가 뒤에 앞으로 왔는지 보고 종료코드 1 |
| `TopMost` 속성 WinForms 폼이 뜰 때 | 매번 | 보일 때 첫 컨트롤에 포커스를 준다(`Form.SetVisibleCore`). 시험 창은 `ShowWithoutActivation` + 창 스타일 `WS_EX_TOPMOST` |
| `click --bg` 로 입력칸 | 가끔 | 막지 못한다. `_fg_guard` 가 보낸 뒤 감지하고 멈춘다 |

| 막 띄운 프로세스(시험 창·시험용 엑셀) | 사용자가 손을 놓고 있을 때 첫 활성화에 | 띄운 쪽이 준 권리를 한 번 쥐고 있다. 지금 앞 창에 포그라운드를 '주면' 권리만 쓴다. 한 번 써 본 MES 는 해당 없다 |

사용자가 "자꾸 화면에 뭐가 떠서 가린다, 뒤로 돌릴 수 없나"고 했다. 그래서 **모니터 밖**을 시험했다:
시험 창을 가상 화면 오른쪽 밖에 두고 `click --bg`(WinForms 버튼 포함)·`type --bg`·`shot --bg`·`copy --bg`·`ui` 를 돌렸더니 **전부 됐다.**
그 자리엔 덮을 창이 없으니 WinForms 의 `WindowFromPoint(그 자리) == 자기` 검사도 통과한다 — 한계 1(덮인 버튼)이 같이 풀린다.
→ `rc.py park "창"`(활성화 없이 모니터 밖으로, `park "창" back` 으로 되돌리기). 실제 MES 에선 아직 안 해 봤다.

시험(`test_rc.py`)은 이제 창을 전부 모니터 밖에 띄우고(엑셀도), PowerShell 콘솔도 안 띄우고, 포그라운드를 사용자 것 그대로 둔다.
시험 창이 20ms 마다 한 번이라도 앞으로 왔는지 본다. `ui invoke` 시험만 `RC_TEST_FOCUS=1` 일 때 맨 끝에 돈다.

## 확인한 것 / 아직 못 한 것

`test_rc.py` 연속 3번 통과(2026-10-26, 일반 권한, 시험 창 전부 모니터 밖, 시험 중 사용자 포그라운드 그대로).

확인(이 PC, 일반 권한, PowerShell WinForms 시험 창·새 엑셀 인스턴스):
- 조합키: AttachThreadInput + SetKeyboardState + PostMessage 로 DataGridView Ctrl+C·Ctrl+A. 사용자 쪽 키 상태·포그라운드 그대로.
- Ctrl 없이 Post 한 `C` 는 셀에 `c` 를 타이핑했다(편집 모드). 조합키 실패를 낱키로 떨어뜨리면 안 된다.
- EDIT: `EM_SETSEL(0,-1)`+`WM_CHAR`, `WM_SETTEXT`, `WM_GETTEXT`, `WM_COPY`, `WM_PASTE` 전부 포커스 없이 됨. `EM_REPLACESEL` 은 마샬링 안 됨.
- UIA: DataGridView 셀이 `Custom | QTY 행 1` 로 잡히고 `ui get` 으로 값이 읽힌다.
- 엑셀: `Value2` 2차원 배열 읽기·쓰기, 한글, 다른 프로세스에서 `GetActiveObject`, 창 핸들→`EXCEL7`→`AccessibleObjectFromWindow` 로 `Application`. 모두 포그라운드 그대로.
- 엑셀: `Visible=$true` 는 뺏는다. `ShowWindow(SW_SHOWNOACTIVATE)` 는 안 뺏는다. 모달 대화상자 중 호출은 `0x80010001`.
- 최소화 복원은 뺏는다(WinForms, 활성 창일 때). `SetWindowPos(NOACTIVATE)` 이동은 안 뺏는다. `LockSetForegroundWindow` 는 오류 5.
- `click --bg` 가 가끔 창을 앞으로 가져온다(한계 2). 되돌리기(`SW_MINIMIZE`)는 믿을 수 없다.
- 클립보드 순번(`GetClipboardSequenceNumber`)으로 내 변경과 남의 변경이 구분된다. 넣은 직후 `WM_PASTE` 는 빈 글(한계 4).

추정(MES 가 이 PC 에 없어 못 봄 — 실제 MES 에서 먼저 확인할 것):
- `park` 로 모니터 밖에 둔 MES 에서 직접 그린(DevExpress) 버튼이 `click --bg` 로 눌리는지. WinForms 버튼은 됐다.
- DevExpress GridControl 이 UIA 로 셀을 내놓는지(`ui controls "MES" 행`). 안 내놓으면 `copy --bg`.
- DevExpress 그리드가 Ctrl+C 로 선택 행을 TSV 로 복사하는지(`OptionsClipboard.AllowCopy`), Ctrl+V 붙이기를 지원하는지(버전에 따라 없음).
- DevExpress TextEdit 안쪽이 EDIT 라 `gettext`·`type --replace` 가 통하는지, `EditValue` 가 포커스 이동(`key tab --bg`) 때 확정되는지.
- `launch` 로 띄운 MES 의 첫 `click --bg` 가 앞으로 오는지(한계 2). rc.py 의 자식이라 권리가 있을 수 있다.
- Claude 관리자 + 엑셀 일반 권한: ROT 실패(알려진 사실), `--book` 경로는 될 것(상위 → 하위 권한은 UIPI 가 안 막는다).
- 셀 편집 중 엑셀 호출이 `0x80010001` 인 것(대화상자와 같을 것).

아직:
- 사용자 엑셀에서 `Workbooks.Add` 가 포그라운드를 뺏는지.
- `_check_fg` 를 시험으로 강제하는 법(언제 뺏는지 조건을 못 밝혀서).

## 관련 코드·문서

- `skills/computer-use/scripts/rc.py` — `_fg_guard`·`_held`·`_sync`·`bg_key`(조합키)·`bg_copy`·`bg_paste`·`_clip_save`·`_clip_restore`·`xl_window`·`xl_get`·`xl_set`
- `skills/computer-use/scripts/rc-agent.ps1` — `xlget`·`xlset`, `set`(Win32 입력칸은 `WM_SETTEXT`)
- `skills/computer-use/scripts/test_rc.py` — 위 시험
- `skills/computer-use/references/pitfalls.md` — 14(최소화 복원), 15(앞으로 와서 사용자 키를 가져간다), 16(엑셀 COM)
- `docs/design-background-control.md` — 한계 3(조합키)·4(최소화)는 이 문서로 갱신됐다
