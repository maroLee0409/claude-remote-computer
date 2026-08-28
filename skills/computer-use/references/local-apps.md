# 로컬 앱 조작 · PC 진단

RDP 가 아니라 **이 PC 에서 돌아가는 것**을 다룰 때. 실제로는 이쪽이 더 자주 쓰인다.

---

# 1부 — 사내 프로그램 / 레거시 앱 조작

MES·ERP 같은 업무 프로그램, JDeveloper·Java Swing·WinForms·Delphi·VB6 로 만든 것들.
공통점은 **자동화 인터페이스가 없다**는 것이다. API 도 CLI 도 없고, 접근성 트리도 부실하다.

그래서 사람이 하는 것과 똑같이 한다 — 보고, 누른다.

## 기본 순서

```bash
RC="$HOME/.claude/skills/computer-use/scripts/rc.py"

python "$RC" windows                              # 창 제목으로 대상 찾기
python "$RC" shot app.png --window "프로그램명"    # 그 창만 캡처
# Read 툴로 app.png 를 열어 눈으로 본다
python "$RC" click X Y --focus "프로그램명"
python "$RC" shot after.png --window "프로그램명"  # 눌린 결과 확인
```

## 이런 앱에서 특히 조심할 것

**창 제목이 자주 바뀐다.** 문서를 열면 `MES - 생산실적[2026-08]` 처럼 바뀐다.
`--focus` 에는 **안 바뀌는 부분만** 넣는다. `"MES"` 정도.

**모달 대화상자가 부모와 제목이 다르다.** 저장 확인창이 뜨면 포커스가 그쪽으로 간다.
클릭이 안 먹으면 **전체 화면을 캡처**해서 가리는 창이 있는지 본다.

**Java/Swing 은 렌더가 느리다.** 클릭하고 바로 캡처하면 이전 화면이 찍힌다.
`0.5~1초` 두고 캡처하거나, 화면이 바뀔 때까지 반복 확인한다.

**그리드·표는 좌표로 세지 말고 확대해서 읽는다.**
```bash
python "$RC" shot grid.png X Y W H --scale 3
```
행 높이를 계산해서 "5번째 행" 을 클릭하려 들면 스크롤 위치 때문에 어긋난다.
캡처해서 **눈으로 그 행을 찾아** 좌표를 읽는 게 정확하다.

**입력은 클립보드로.** 긴 값을 `type` 으로 넣으면 느리고, 앱이 입력을 놓치기도 한다.
```bash
python "$RC" clip "넣을 값"
python "$RC" click X Y --focus "MES"      # 입력칸 클릭
python "$RC" key ctrl a --focus "MES"     # 기존 값 선택
python "$RC" key ctrl v --focus "MES"     # 덮어쓰기
```

**단축키가 있으면 클릭보다 낫다.** 좌표에 의존하지 않아서 훨씬 안정적이다.
메뉴에 `파일(F)` 처럼 밑줄이 있으면 `Alt+F` 가 먹는다.

## 설치 마법사 / 반복 대화상자

「다음」 버튼 위치가 화면마다 조금씩 다르다. 매번 캡처해서 확인한다.
같은 좌표를 반복해서 누르면 엉뚱한 것(「취소」나 「동의 안 함」)을 누르게 된다.

라이선스 동의 체크박스, 설치 경로 같은 건 **사용자에게 먼저 확인**한다.

---

# 2부 — PC 문제 진단

"뭔가 이상한데 뭔지 모르겠다" 는 상황. 화면을 보는 눈이 되어 준다.

## 먼저 볼 것

```bash
python "$RC" shot screen.png --scale 0.5     # 전체 상황
python "$RC" windows                          # 떠 있는 창 (오류창이 숨어 있을 수 있다)
```

오류 대화상자는 다른 창 뒤에 숨어 있는 경우가 많다. `windows` 목록에 제목이 남는다.

## 오류창을 만나면

메시지를 **그대로 옮겨야** 검색·판단이 된다. 요약하지 마라.

```bash
python "$RC" shot err.png --window "오류"
python "$RC" shot err.png X Y W H --scale 3   # 글씨가 작으면 확대
```

Windows 오류창은 대부분 `Ctrl+C` 로 **본문 전체가 클립보드에 복사된다.**
```bash
python "$RC" key ctrl c --focus "오류"
python "$RC" getclip err.txt
```
이게 캡처를 눈으로 읽는 것보다 정확하다. 먼저 시도해볼 것.

## 명령으로 얻을 수 있으면 그게 낫다

GUI 를 여는 것보다 빠르고 정확하다. 화면 조작은 **GUI 밖에 없을 때** 쓴다.

```powershell
Get-WinEvent -LogName System -MaxEvents 30 | Where-Object LevelDisplayName -ne '정보'
Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 10
Get-Service | Where-Object { $_.StartType -eq 'Automatic' -and $_.Status -ne 'Running' }
Get-PnpDevice | Where-Object Status -ne 'OK'
Get-Volume | Where-Object { $_.SizeRemaining -lt 5GB -and $_.DriveLetter }
```

## GUI 를 열어야 하는 것

| 대상 | 실행 |
|---|---|
| 이벤트 뷰어 | `eventvwr.msc` |
| 작업 관리자 | `taskmgr` |
| 장치 관리자 | `devmgmt.msc` |
| 서비스 | `services.msc` |
| 디스크 관리 | `diskmgmt.msc` |
| 리소스 모니터 | `resmon` |
| 시스템 정보 | `msinfo32` |

`Win+R` 로 실행창을 열어 입력한다.
```bash
python "$RC" key win r
python "$RC" clip "eventvwr.msc"
python "$RC" key ctrl v
python "$RC" key enter
```

## 진단할 때의 태도

**추측을 사실처럼 말하지 마라.** 화면에서 읽은 것과 추론을 구분해서 전달한다.

- 봤다: "이벤트 뷰어에 오늘 03:59 에 오류 5076 이 있다"
- 추론이다: "그것 때문일 가능성이 높다"

**고치기 전에 물어라.** 진단은 마음껏 해도 되지만, 서비스 재시작·설정 변경·드라이버 삭제는
사용자 확인을 받는다. 원인이 확실해 보여도 마찬가지다.

**못 찾으면 못 찾았다고 하라.** 그럴듯한 원인을 지어내는 것보다,
무엇을 확인했고 무엇이 정상이었는지 알려주는 게 낫다. 다음 단계를 좁혀준다.
