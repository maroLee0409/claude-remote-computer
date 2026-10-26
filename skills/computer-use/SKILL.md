---
name: computer-use
description: Windows 컴퓨터를 눈으로 보고 직접 조작한다 — 화면을 캡처해 확인하고 마우스·키보드·클립보드로 아무 앱이나 다룬다. 두 가지로 쓴다. (1) 조작 — MES/ERP 같은 사내 프로그램, JDeveloper·Java·WinForms·Delphi 로 만든 레거시 데스크톱 앱, 설치 마법사, PowerShell, 탐색기, 장치 관리자, IIS 관리자처럼 API 나 명령줄이 없는 GUI 를 대신 눌러준다. (2) 진단 — PC 에 문제가 생겼는데 사용자가 원인을 모를 때 화면·오류창·이벤트뷰어·작업관리자를 직접 보고 무엇이 잘못됐는지 알아낸다. RDP 원격 데스크톱 너머의 서버도 같은 방식으로 다룬다. 사용자가 "내 컴퓨터 써서 해봐", "화면 보고 눌러줘", "이 프로그램 좀 조작해줘", "내 PC 가 이상한데 봐줘", "무슨 오류인지 직접 확인해봐", "원격 데스크톱", "GUI 자동화" 같은 말을 하거나, 명령줄로는 닿지 않아 화면을 봐야만 하는 작업일 때 사용한다.
model: sonnet
---

# 컴퓨터 조작 · 진단 (Windows)

화면 캡처 → 이미지로 확인 → 마우스·키보드 입력, 이 순환으로 컴퓨터를 다룬다.
브라우저 안에 갇히지 않는다. **화면에 뜨는 것이면 전부** 대상이다.

두 갈래로 쓴다.

**조작** — API 도 명령줄도 없는 GUI 를 대신 눌러준다.
사내 MES/ERP, JDeveloper·Java·WinForms·Delphi 로 만든 레거시 앱, 설치 마법사,
장치 관리자, IIS 관리자. 자동화 인터페이스가 없어도 사람이 누르는 것과 같은 방식이면 된다.

**진단** — 사용자가 원인을 모르는 문제를 직접 보고 알아낸다.
오류창을 읽고, 이벤트 뷰어를 열고, 작업 관리자를 확인한다.
"뭔가 이상한데 뭔지 모르겠다"는 상황에서 화면을 보는 눈이 되어 준다.

원격 서버(RDP)도 같은 방식으로 다룬다 — 특별한 모드가 아니라 대상이 하나 늘어난 것뿐이다.

도구는 `scripts/rc.py` 하나다(이름으로 누르기·RDP 도우미는 rc.py 가 `scripts/rc-agent.ps1` 을 부른다).
**Pillow 외에 설치할 것이 없고 관리자 권한도 필요 없다.**

## 모델 — Sonnet 으로 돌린다

화면 조작은 캡처 → 확인 → 클릭을 수십 번 반복한다. 큰 모델로 돌리면 한 바퀴마다 느려서
사용자가 기다리다 지친다. **본체가 Opus 면 `rc.py` 를 직접 부르지 마라.**
`computer-use` 에이전트(`subagent_type: "computer-use"`, `~/.claude/agents/computer-use.md` 에서 sonnet 고정)로 넘긴다.
그 에이전트가 목록에 없으면(만든 직후 세션 등) general-purpose 에 `model: "sonnet"` 으로 넘긴다.

- 클릭·입력·창 전환·값 읽기·설치 마법사·`ui`·`remote` 명령·진단 → 전부 **sonnet**
- 큰 모델(opus 등)은 화면 조작에 쓰지 않는다. 설계·결정은 본체가 하고 에이전트에는 손만 맡긴다.
- 에이전트에게는 목표·금지사항·멈출 조건을 짧게 주고, 결과는 "무엇을 바꿨고 무엇이 남았는지"만 받는다.
- 명령 몇 줄로 끝나는 원격 작업은 도우미가 떠 있으면 `remote run`, 아니면 **사용자에게 복붙용 명령**이 더 빠르다.

## 시작하기

```bash
RC="$HOME/.claude/skills/computer-use/scripts/rc.py"     # 경로를 한 번 잡아두면 편하다
python "$RC" monitors      # 모니터 배치
python "$RC" windows        # 열려 있는 창 목록 (제목 + 좌표)
```

Pillow 가 없으면 `pip install pillow` 한 번만 하면 된다.

## 핵심 순환 — 이 순서를 지켜라

```
① 캡처   python "$RC" shot out.png --window "대상창"
② 확인   Read 툴로 out.png 를 열어 눈으로 본다
③ 입력   python "$RC" click X Y --img out.png --focus "대상창"
④ 검증   python "$RC" waitstable --window "대상창" 5  →  다시 캡처해서 의도한 일이 일어났는지 확인
```

**②를 건너뛰지 마라.** 좌표를 기억해두고 재사용하는 순간 사고가 난다.
창은 움직이고, 다른 창이 위로 올라오고, 대화상자가 뜬다.

## 좌표계

**캡처 이미지에서 읽은 좌표는 `--img 그파일.png` 를 붙여서 넘긴다.**
`shot` 은 자른 영역의 원점과 축소 배율을 PNG 에 적어 두고, `--img` 가 그걸 되돌린다.
그래서 `--window` 로 자른 이미지든 줄인 이미지든 **눈으로 읽은 좌표를 계산 없이 그대로** 넣는다.
`shot` 은 긴 변 1568px(약 115만 화소)를 넘으면 알아서 줄인다 — Claude 가 큰 이미지를 몰래 줄여 보면
좌표가 어긋나기 때문이다. 다중 모니터 전체 캡처는 많이 줄어드니 작업은 `--window` 로 찍는다.

`windows` / `windowrect` / `ui controls` 가 찍는 좌표는 원본 스크린샷 좌표라 `--img` 없이 쓴다.
`rc.py` 는 모니터별 DPI 인식으로 돌아서 모니터마다 배율이 달라도(150% + 100% 등),
주 모니터 왼쪽에 모니터가 있어도(가상 화면 원점이 음수) 창 좌표·캡처·클릭이 서로 맞는다.

```bash
python "$RC" windowrect "PowerShell"      # (x, y, w, h)
python "$RC" shot ps.png --window "PowerShell"
```

`monitors` 가 틈/겹침 경고를 찍으면 Windows 10 1703 이전 같은 구형 환경이다 —
그때는 `windows` / `windowrect` 로 창 좌표를 얻어 쓴다.

## 좌표 대신 이름으로 — `ui`

캡처해서 좌표를 읽기 전에 **이름으로 되는지 먼저 본다.** 되면 캡처·좌표 맞히기가 다 빠진다.

```bash
python "$RC" ui controls "MES" [필터]          # 종류 | 표시이름 | AutomationId | x,y,w,h
python "$RC" ui invoke "MES" btnSearch          # 버튼 누르기·체크 토글·항목 선택
python "$RC" ui set "MES" txtLot "LOT-001"      # 입력칸에 값 넣기
python "$RC" ui get "MES" lblResult             # 값·글자 읽기 - OCR 필요 없음
python "$RC" ui wait "저장" 10                  # 대화상자가 뜰 때까지
```

- **WinForms 는 AutomationId 가 소스의 컨트롤 이름(`btnSearch`)이다.** 소스를 알면 좌표 없이 바로 누른다.
- 잘 잡힘: WinForms·Win32(MES, IIS 관리자, 설치 마법사, MMC), WPF, UWP, 탐색기.
- 안 잡힘: Java Swing(JDeveloper), 직접 그린 그리드·캔버스 → 지금처럼 캡처해서 좌표로.
- `invoke` 는 마우스를 안 움직이고 포커스도 안 뺏는다(버튼 등 패턴이 있는 것). 패턴이 없는 것만
  창을 앞으로 가져와 가운데를 클릭하며, 그 자리를 다른 창이 가리고 있으면 누르지 않는다.
- 모달 창을 띄우는 버튼도 3초 뒤 돌아온다. 이어서 `ui wait "창제목"` → `ui invoke "창제목" "확인"`.

## 뒤에서 — `--bg` (사용자가 마우스·키보드를 계속 써도 된다)

이름이 안 잡히는 앱(직접 그린 버튼)도 **창을 앞으로 안 가져오고** 다룬다. 실제 마우스·키보드를 안 쓰고 그 창에 메시지만 보낸다.

```bash
python "$RC" shot out.png --bg "MES"                  # 가려져 있어도 그 창만 찍힌다
python "$RC" click X Y --bg "MES" --img out.png       # 그 자리 컨트롤에 클릭 메시지 (dblclick·rclick 도)
python "$RC" type "LOT-001" --bg "MES"                # 포커스 칸에 글자 (한글 OK). 먼저 입력칸을 click --bg
python "$RC" key enter --bg "MES"                     # 키 하나만. ctrl+s 같은 조합은 안 된다 -> 버튼을 click --bg
python "$RC" waitstable --bg "MES" 10                 # 확인·대기도 뒤에서
```

- **버튼 자리가 다른 창에 덮여 있으면 버튼은 안 눌린다**(입력은 된다). 앞으로 올 필요는 없고 보이기만 하면 된다 → 다른 모니터에 둔다. `pitfalls.md` 11.
- 안 눌려도 오류가 없다. 누를 때마다 `shot --bg` 로 확인한다.
- 최소화된 창은 안 된다. 대상이 관리자 권한이면 rc.py 가 보내기 전에 멈춘다 → `pitfalls.md` 12.
- 그럴 땐 사용자가 그 앱을 닫고 `launch` 로 일반 권한으로 다시 띄운다. 로그인 창은 사용자가 직접 입력한다.
  ```bash
  python "$RC" windows                                # 이미 떠 있는지 먼저 본다 - launch 는 안 본다
  python "$RC" launch "바로가기 이름"                 # 시작 메뉴·바탕화면 바로가기 실행 -> 새로 뜬 창 제목을 찍는다
  ```
  관리자를 요구하는 앱도 일반 권한으로 띄운다(RunAsInvoker). 그 앱의 자동 업데이트는 안 된다 → `pitfalls.md` 12.
- 같은 제목 창이 둘이면(관리자로 뜬 것 + launch 한 것) `--bg` 는 다룰 수 있는 쪽을 고른다. 헷갈리니 관리자 것은 사용자가 닫게 한다.
- `--focus` 와 같이 못 쓴다. `--bg` 가 안 되면 앞으로 가져와 누르는 걸로 넘어가지 말고 멈춰서 보고한다.
- 왜 이렇게 만들었는지: 저장소 `docs/design-background-control.md`.

## 기다리기

`sleep` 대신 조건이 될 때까지 짧게 반복 확인한다. 시간 초과면 종료코드 1.

```bash
python "$RC" waitwin  "저장" 10      # 창이 뜰 때까지
python "$RC" waitgone "저장" 10      # 창이 닫힐 때까지
python "$RC" waitclip "완료" 180     # 클립보드에 그 글자가 들어올 때까지
python "$RC" waitstable --window "MES" 10   # 화면이 1초 동안 안 바뀔 때까지 (로딩·렌더 끝)
python "$RC" waitchange X Y W H 10          # 그 영역이 바뀔 때까지 - 바뀐 자리 좌표를 찍는다
```

`waitstable` / `waitchange` 는 `--window` 나 영역으로 좁혀 쓴다. 전체 화면은 다른 모니터의
터미널·시계가 계속 바뀌어서 안 멈춘다. 깜빡이는 입력 커서(폭 3px 이하)는 변화로 치지 않는다.

## 반드시 지킬 것

**1. 입력 전에 포커스를 강제하고, 실패하면 입력하지 마라.**

```bash
python "$RC" click 500 300 --focus "메모장"
python "$RC" key ctrl v --focus "메모장"
```

`--focus` 는 대상 창을 포그라운드로 만들고, 실패하면 **입력을 아예 하지 않고 종료**한다.
이걸 빼면 키 입력이 브라우저 주소창이나 남의 문서로 들어간다. 실제로 겪은 사고다.

**2. 클릭 좌표는 매번 새로 캡처해서 확인한다.**
`click` 은 실행 전에 그 좌표에 있는 창 제목을 찍어준다. 예상과 다르면 멈춰라.
`--focus` 를 붙이면 그 자리를 **다른 프로그램의 창**이 가리고 있을 때 누르지 않고 종료한다
(같은 프로그램의 대화상자·드롭다운은 통과). 작업표시줄처럼 다른 프로그램을 누를 땐 `--focus` 를 뺀다.

**3. 긴 텍스트는 타이핑하지 말고 클립보드로 넣는다.**

```bash
python "$RC" clipfile 명령.txt        # 파일 내용을 클립보드로
python "$RC" key ctrl v --focus "대상창"
```

`type` 은 한 글자씩 주입해서 느리다. 짧은 것에만 쓴다(한글·이모지는 IME 없이 들어간다).

**4. 되돌리기 어려운 조작은 먼저 확인을 받아라.**
파일 삭제, 설정 변경, 결제, 메일 전송 같은 것. 특히 운영 중인 서버라면 더욱.
가능하면 dry-run 이나 백업을 먼저 만들어 두고 한다.

## 잘 듣는 조합

| 하고 싶은 것 | 방법 |
|---|---|
| 관리자 권한 앱 띄우기 | 작업표시줄 아이콘에 **Ctrl+Shift+클릭** |
| 창 목록에서 찾기 | `windows "일부제목"` |
| 버튼·입력칸을 이름으로 | `ui controls "창"` → `ui invoke` / `ui set` / `ui get` |
| 사용자 방해 없이 뒤에서 | `shot --bg "창"` → `click X Y --bg "창" --img` → `type --bg` → `shot --bg` 로 확인 |
| 대화상자 뜰 때까지 | `waitwin "제목" 10` |
| 로딩·렌더 끝날 때까지 | `waitstable --window "제목" 10` |
| 특정 창만 캡처 | `shot out.png --window "제목"` |
| 크게 보기 | `shot zoom.png X Y W H --img out.png --scale 3` (out.png 에서 읽은 영역 확대) |
| 전체를 한눈에 | `shot out.png --scale 0.4` |
| 결과를 텍스트로 회수 | 대상 앱에서 복사 → `getclip` |

## 상황별 안내

| 하려는 것 | 읽을 문서 |
|---|---|
| 사내 프로그램·레거시 앱 조작, PC 문제 진단 | `references/local-apps.md` |
| RDP 원격 서버 | `references/rdp.md` |
| 막혔을 때 | `references/pitfalls.md` |

RDP 창 안은 **로컬에서 보면 창 하나**라 컨트롤 이름이 안 보인다.
**RDP 에서는 도우미(rc-agent)·`remote` 명령을 쓰지 않는다**(운영 서버에 파일을 남기지 않기로 함).
예전 방식대로 붙여넣기 → 캡처로 눈 확인 → 엔터를 쓰고, 클릭·입력 직전에 **매번 캡처해서 눈으로 확인**한다.
순서는 `references/rdp.md` 의 "도우미 없이 — 지켜야 할 순서". `ui`(이름으로 누르기) 등 새 기능은 RDP 밖 로컬 앱에서만 쓴다.

## 막혔을 때

`references/pitfalls.md` 에 실제로 당한 함정과 해법이 정리돼 있다.
포커스 유실, 혼합 DPI, 콘솔 인코딩, AMSI 차단, 백슬래시 접힘 같은 것들이다.

2~3회 시도해도 안 되면 혼자 더 밀어붙이지 말고, 무엇을 시도했고 무엇이 막혔는지
사용자에게 설명하고 어떻게 할지 물어라.
