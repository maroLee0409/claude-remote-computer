# RDP 원격 서버 조작

WinRM·SSH·SMB 가 다 막혀 있고 3389 만 열린 서버도 이 방법으로 다룰 수 있다.
사람이 RDP 로 붙어 있기만 하면 된다.

## 왜 조심해야 하나

**RDP 세션 안은 로컬에서 보면 창 하나다.**
`windows` / `window_at` / `foreground` 는 전부 "203.0.113.10 - 원격 데스크톱 연결" 하나만 알려준다.
세션 **안에서** 어떤 창이 앞에 있는지는 밖에서 알 방법이 없다.

그래서 로컬에서 통하던 안전장치가 세션 안에서는 반쪽만 듣는다:

- `--focus "RDP창제목"` → RDP 클라이언트가 포그라운드인 것까지만 보장한다.
- 세션 **안**에서 어떤 앱이 키를 받는지는 **캡처해서 눈으로 봐야만** 알 수 있다.

실제 사고: PowerShell 창 좌표를 기억해두고 그대로 클릭했는데, 그 사이 IIS 관리자가 앞으로
나와 있어서 Enter 가 거기로 들어갔다. 운영 중인 **다른 앱의 앱풀 편집 대화상자**가 열렸다.
(값은 안 바뀌었지만 한 끗 차이였다.)

## (사용 안 함) 세션 안 도우미 (rc-agent) — RDP 에서는 쓰지 말고 아래 "도우미 없이" 방식을 따른다

밖에서 못 보면 **안에서 보게 한다.** 세션 안 PowerShell 에 `rc-agent.ps1` 을 띄워 두면
클립보드(RDP 가 양방향 동기화)를 통로로 명령을 받아 세션 안에서 실행하고 결과를 클립보드로 돌려준다.

- 키보드·마우스를 안 쓴다 → 아래 "IIS 앱풀 대화상자에 엔터" 같은 사고가 구조적으로 안 난다.
- 세션 안 창 목록·맨 앞 창이 텍스트로 보인다. 컨트롤도 이름으로 누른다(IIS 관리자·MMC·설치 마법사).
- PowerShell 은 `run` 한 번에 결과까지 온다 — 붙여넣기→캡처→엔터→Transcript→클립보드가 다 빠진다.
- 길이 제한(콘솔 한 줄 8000자)·조각 이어붙이기도 없다. 긴 스크립트는 `runfile x.ps1`.

### 띄우기 (서버마다 처음 한 번, 1분)

세션 안에 PowerShell 창이 하나 떠 있어야 한다(없으면 아래 "관리자 PowerShell 띄우기").

```bash
python "$RC" remote boot                          # 클립보드 = 시작 한 줄
python "$RC" key ctrl v --focus "203.0.113"       # 세션 안 PowerShell 에 붙여넣기
python "$RC" shot b.png --window "203.0.113"      # ← 한 줄이 PowerShell 프롬프트에 들어갔는지 눈으로 확인
python "$RC" remote push                          # 클립보드 = rc-agent.ps1 본문 (엔터 치기 전에!)
python "$RC" key enter --focus "203.0.113"        # 엔터 순간 클립보드를 %TEMP%/rc-agent.ps1 로 저장하고 실행
python "$RC" remote hello                         # READY 를 받아 토큰 저장 → "연결됨: 서버명"
```

시작 한 줄은 평문이다(base64·압축 없음) — AMSI 에 걸리는 패턴이 아니다.
두 번째부터는 파일이 이미 있으니 세션 안 PowerShell 에서
`powershell -NoProfile -ExecutionPolicy Bypass -File $env:TEMP/rc-agent.ps1` 만 하면 된다.

### 쓰기

```bash
python "$RC" remote ping                          # 살아 있나
python "$RC" remote windows                       # 세션 안 창 목록, * = 맨 앞
python "$RC" remote fg                            # 세션 안 맨 앞 창
python "$RC" remote focus "IIS"                   # 세션 안에서 창 앞으로
python "$RC" remote run "Get-Service W3SVC; hostname"
python "$RC" remote runfile deploy.ps1 --timeout 600
python "$RC" remote controls "IIS" "풀"            # 세션 안 컨트롤 목록 (필터)
python "$RC" remote invoke "IIS" "응용 프로그램 풀"
python "$RC" remote wait "확인" 10                 # 세션 안 대화상자가 뜰 때까지
python "$RC" remote stop                          # 도우미 끝내기
```

`run` 은 Write-Host·오류까지 전부 담아 돌려준다. 실패(예외)면 종료코드 1.

### 안전장치와 주의

- **토큰**: 도우미는 띄울 때마다 새 토큰을 만들고 그 토큰이 붙은 명령만 실행한다.
  사용자가 복사한 다른 글이나, 클립보드에 남은 예전 명령은 무시된다.
- 도우미 창에 받은 명령이 한 줄씩 찍힌다 — 사용자가 세션 화면에서 무엇이 실행되는지 볼 수 있다.
- 도는 동안 **클립보드를 덮어쓴다.** 작업이 끝나면 `remote stop`.
- 응답이 안 오면(시간 초과): 도우미 창이 죽었거나, RDP 창이 닫혔거나, 클립보드 리디렉션이 꺼진 서버다.
  세션 화면을 캡처해서 도우미 창의 오류를 본다. 안 되는 서버면 아래 예전 방식으로.
- 운영 서버 원칙(dry-run, 백업, 되돌리기 준비, 되돌릴 수 없는 건 먼저 묻기)은 그대로다.

## 도우미 없이 — 지켜야 할 순서

```
① 캡처해서 세션 안 상태를 눈으로 확인
② --focus 로 RDP 창을 포그라운드로
③ 붙여넣기
④ 엔터 누르기 전에 다시 캡처해서 명령이 제대로 들어갔는지 확인   ← 이걸 하면 사고가 안 난다
⑤ 엔터
⑥ 결과 캡처 또는 클립보드 회수
```

④가 핵심이다. 붙여넣은 텍스트가 프롬프트에 보이는지 눈으로 확인하고 엔터를 친다.

## 명령 보내고 결과 받기

RDP 는 클립보드를 양방향 동기화한다. 파일 전송 설정이 없어도 이걸로 왕복이 된다.

**보내기**
```bash
python "$RC" clipfile 명령.txt
python "$RC" key ctrl v --focus "203.0.113"
# 여기서 캡처해서 확인
python "$RC" key enter --focus "203.0.113"
```

**받기** — 원격에서 결과를 클립보드에 담게 한다.
```powershell
Start-Transcript -Path 'C:/temp/out.txt' -Force | Out-Null
& '내가 실행할 것'
Stop-Transcript | Out-Null
Set-Clipboard -Value (Get-Content 'C:/temp/out.txt' -Raw)
```
```bash
python "$RC" getclip 결과.txt
```

`Write-Host` 출력은 파이프로 안 잡힌다. **`Start-Transcript` 를 써야** 다 잡힌다.

클립보드가 아직 안 왔으면 내가 보낸 명령 텍스트가 그대로 들어 있다.
그걸로 "아직 실행 중"인지 판별할 수 있다.

## 긴 스크립트 보내기

콘솔 한 줄에는 길이 제한이 있다(레거시 콘솔 약 8000자).
4000자 정도로 잘라서 변수에 이어 붙인 뒤 마지막에 실행한다.

```
$acc='...조각1...'
$acc=$acc+'...조각2...'
$acc=$acc+'...조각3...'
# 마지막 줄에서 파일로 쓰고 실행
```

### AMSI 에 막히는 패턴 — 중요

**gzip+base64 를 디코드해서 실행하는 부트스트랩은 Windows Defender 가 차단한다.**

```
이 스크립트에 악성 콘텐츠가 있어서 바이러스 백신 소프트웨어에 의해 차단되었습니다.
ScriptContainedMaliciousContent
```

악성코드가 쓰는 난독화 패턴과 똑같아서 그렇다. 타당한 탐지다.
**평문 명령을 그대로 보내라.** 압축해서 줄이고 싶은 유혹을 참는 게 낫다.

평문이면 길이가 늘어나니, 위의 조각 이어붙이기로 해결한다.

## 관리자 PowerShell 띄우기

작업표시줄의 PowerShell 아이콘에 **Ctrl+Shift+클릭**.

```bash
python "$RC" shot tb.png 4480 1040 700 40 --scale 3   # 작업표시줄 확대해서 아이콘 위치 확인
```

`rc.py` 에 조합키+클릭 전용 명령은 없으니 파이썬으로 부른다:

```python
import rc, time
rc.require_focus('203.0.113')
rc.move(X, Y); time.sleep(0.3)
rc._kd(rc.VK['ctrl']); rc._kd(rc.VK['shift']); time.sleep(0.15)
rc.click()
time.sleep(0.15)
rc._ku(rc.VK['shift']); rc._ku(rc.VK['ctrl'])
```

## 창이 여러 개일 때

작업표시줄 아이콘을 누르면 썸네일이 뜬다. 썸네일을 캡처해서 내용으로 구분한 뒤 클릭한다.
콘솔 창이 여러 개면 마지막 출력 내용으로 어느 세션인지 알아볼 수 있다.

## 세션이 끊겼을 때

`find_window` 가 못 찾으면 사용자가 RDP 를 닫은 것이다.
`--focus` 가 예외를 던지고 멈추므로 엉뚱한 데로 입력이 새지는 않는다.
사용자에게 다시 열어달라고 하면 된다.

## 운영 서버에서의 원칙

- 대상이 여러 개 있는 서버라면(웹앱 여러 개 등) **내 대상만 건드리는지** 먼저 확인한다.
- 설정 변경은 **dry-run 을 먼저** 돌려 무엇이 바뀔지 보여주고 적용한다.
- 되돌리는 명령을 **미리 준비**해 둔다. 자동 검증 + 자동 롤백을 한 줄에 넣으면 좋다:
  ```powershell
  <변경>; Restart-...; Start-Sleep 15;
  if (<정상 확인>) { 'OK' } else { <되돌리기>; 'FAILED - 롤백함' }
  ```
- 파일을 덮어쓰기 전에 `Copy-Item $p ($p + '.bak')` 로 백업을 남긴다.
