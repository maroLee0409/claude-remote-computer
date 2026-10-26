# claude-remote-computer 개발 지침

Claude Code 가 Windows 데스크톱을 직접 조작하게 해주는 스킬. 여기가 개발 원본이다.

## 이 저장소의 규칙

**① 원본은 여기다. `~/.claude/skills/` 는 사본이다.**

수정은 **반드시 이 저장소의 `skills/` 안에서** 한다.
`~/.claude/skills/computer-use/` 를 직접 고치면 `install.ps1` 이 "사본이 더 새롭다"며 그 파일을 건너뛴다.
경고가 보이면 사본의 변경을 저장소로 옮긴 뒤 다시 돌린다(버려도 되면 `-Force`).

**② 고쳤으면 이 PC 의 다른 Claude 들에게도 반영한다.**

```powershell
.\scripts\install.ps1
```

`skills/`·`agents/` 를 `~/.claude/` 아래로 복사한다. 해시로 비교해서 바뀐 것만 옮긴다.
**이 저장소에서 작업을 마치면 `.claude/settings.json` 의 Stop 훅이 자동으로 실행한다.**
훅이 안 도는 상황(다른 도구로 편집 등)이면 손으로 한 번 돌려라.

반영은 **새 Claude Code 세션부터** 걸린다. 이미 떠 있는 세션은 재시작해야 한다.

**③ 기능이나 노하우가 늘면 문서에도 반영한다.**

이 스킬의 가치는 코드보다 **실패에서 배운 것**에 있다.
새 함정을 만나면 `references/pitfalls.md` 에 증상·원인·해법을 남긴다.
"이렇게 하면 된다"보다 **"이렇게 했다가 이렇게 깨졌다"** 가 훨씬 쓸모 있다.

**④ 커밋하고 푸시한다.** 공개 저장소이므로 아래를 지킨다.

## 공개 저장소 — 절대 넣지 말 것

- 실제 서버 IP·호스트명·도메인 → 예제는 `203.0.113.10` (RFC 5737 문서용 IP) 사용
- 계정명·비밀번호·토큰·자격증명 경로
- 회사명, 내부 시스템 이름, 프로젝트 코드명
- 사내 경로 (`D:\사내시스템\...` 등)

커밋 전 점검 — 패턴 자체에 실명을 적지 마라(그것도 유출이다). 형태로 잡는다:

```bash
# 공인 IP (문서용 203.0.113.x 는 제외)
grep -rnoE "\b([0-9]{1,3}\.){3}[0-9]{1,3}\b" . --exclude-dir=.git | grep -v "203\.0\.113"
# 도메인·자격증명·사내 경로 냄새
grep -rniE "\.co\.kr|\.com/|TERMSRV|password|token|[A-Z]:\\\\[가-힣]" . --exclude-dir=.git
```

걸린 게 있으면 문서용 값(`203.0.113.10`, `example.com`, `MYAPP`)으로 바꾼다.

## 구조

```
.claude-plugin/
  plugin.json          플러그인 매니페스트
  marketplace.json     이 저장소 자체가 마켓플레이스 (자기 자신을 등록)
skills/
  computer-use/
    SKILL.md           트리거 문구 · 핵심 순환 · 안전 규칙
    scripts/rc.py      툴킷 (Pillow 만 의존)
    scripts/rc-agent.ps1  이름으로 누르기(UI Automation)·RDP 도우미
    scripts/test_rc.py    자가 점검
    references/
      local-apps.md    로컬 앱 조작 · PC 진단
      rdp.md           RDP 원격 서버 플레이북
      pitfalls.md      실전 함정 모음
agents/
  computer-use.md      화면 조작 전담 하위 에이전트 (sonnet)
scripts/
  install.ps1          skills/ agents/ -> ~/.claude/ 동기화 (사본이 더 새로우면 건너뜀)
docs/
  design-*.md          왜 이렇게 만들었나 - 기능을 크게 바꾸기 전에 읽는다 (사본으로 안 나간다)
.claude/settings.json  Stop 훅 (자동 동기화)
```

## 설계 원칙 — 바꾸기 전에 읽어라

**의존성을 늘리지 마라.** Pillow 하나만 쓴다. pyautogui·pywin32 는 넣지 않는다.
설치 장벽이 낮은 게 이 도구의 장점이다. ctypes 로 해결되면 ctypes 로 한다.

**좌표는 스크린샷 픽셀 기준 하나로 통일한다.** 세 가지 좌표계가 공존하는 환경에서
이걸 흐트러뜨리면 아무도 못 쓴다. 변환은 `scale()` 한 군데서만.

**안전장치를 약화시키지 마라.** `--focus` 는 실패 시 **입력하지 않고 종료**해야 한다.
"일단 시도해보고 안 되면 넘어가기"로 바꾸면 키가 엉뚱한 앱으로 샌다. 실제로 겪은 사고다.
`--bg`(뒤에서)도 같다. 실패하면 멈춘다 — 앞으로 가져와 누르는 걸로 넘어가지 마라. `docs/design-background-control.md`.

**도구가 스스로 권한을 올리지 않는다.** UAC 를 건드리거나 넘으려 하지 마라. `launch` 는 rc.py 와 같은 권한으로만 띄운다.
관리자 앱을 다룰지는 사용자가 정한다 — 앱을 일반 권한으로 내려 띄우거나(실행 중 설치 폴더에 안 쓰는 앱만),
사용자가 Claude 를 관리자로 띄운다. 사내 MES 는 후자로 정했다. `docs/design-background-control.md`.

**한글 출력은 `_p()` 로.** cp949 콘솔에서 이모지 하나에 스크립트가 통째로 죽는다.

## 테스트

`python skills/computer-use/scripts/test_rc.py` — 캡처 좌표 환산·변화 감지를 먼저 보고,
시험 창을 띄워 `ui`·`--bg`(덮개 창으로 덮은 채)·`remote` 를 확인한다(클립보드를 덮어쓴다). 그 밖에는 손으로 확인한다:

```bash
RC="skills/computer-use/scripts/rc.py"
python "$RC" monitors                                   # 혼합 DPI 면 경고가 떠야 정상
python "$RC" windows | head                             # 이모지 창 제목에서 안 죽어야 함
python "$RC" windowrect "Chrome"
python "$RC" clip "test" && python "$RC" getclip        # 왕복
python "$RC" key enter --bg "없는창12345"                # 예외로 막혀야 정상
python "$RC" key enter --focus "없는창12345"             # 예외로 막혀야 정상
```

마지막 두 항목이 제일 중요하다. 여기서 입력이 나가면 안전장치가 깨진 것이다.
관리자 권한 앱이 떠 있으면 `shot out.png --bg "그 창"` 이 "관리자 권한으로 떠 있다"로 멈추는지도 본다.
