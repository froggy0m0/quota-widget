# Quota Widget — Python + Tkinter

기존 Windows 사슴 위젯을 Python으로 옮긴 별도 시험용 앱입니다. 정면 16×16 사슴 픽셀 그림, 5시간 사용률(남은 양이 아님), 1분 간격 조회, 첫 조회 전 `--`, 오류 때 마지막 숫자와 회색 사슴, 드래그 이동, 항상 위, 우클릭 메뉴, 크기·모양 저장을 유지합니다. 첫 실행 크기는 요청에 따라 128 px이며, 메뉴에서 160 px도 고를 수 있습니다. 사용 이미지의 픽셀 경계를 보존하기 위해 Pillow의 최근접 보간을 씁니다.

Codex 앱이 ChatGPT 계정으로 로그인되어 있어야 합니다. 위젯은 `codex.exe app-server --listen stdio://`를 실행하고 `initialize`, `initialized`, `account/rateLimits/read`만 전송합니다. 자격 증명 파일을 읽거나 복사하지 않고 모델 요청도 하지 않습니다. 서버 응답에서 `rateLimitsByLimitId.codex`를 먼저 보고, 없으면 기존 `rateLimits` 형식을 확인한 뒤 300분 창의 `usedPercent`를 표시합니다. 요청은 단일 대기열로 처리하며 응답 제한 시간은 20초입니다.

반투명 회색 사슴과 숫자 패널은 Pillow에서 RGBA로 합성하고 Windows `UpdateLayeredWindow`로 표시합니다. Tkinter는 창·메뉴·드래그를 담당합니다. 분홍색 투명 키를 사용하지 않아 반투명 영역이 분홍색으로 물들지 않습니다.

우클릭 메뉴 맨 위에서 `Codex` 또는 `Claude`를 선택하며 선택은 저장됩니다. Claude는 Claude Code 구독 계정의 5시간 **사용한 비율**을 표시합니다. 설치·로그인 전에는 `--`와 로그인 안내가 표시됩니다. 로그인 후 기존 `.claude/.credentials.json`의 OAuth 인증으로 한도만 조회하며, 인증 정보를 복사하거나 모델을 호출하지 않습니다. `CLAUDE_CONFIG_DIR`도 지원합니다. 조회 연결은 [Claude Code에서 사용하는 usage endpoint](https://github.com/anthropics/claude-code/issues/31021)를 기준으로 하며 공개 SDK API와 구분됩니다.

## Windows 포터블 빌드

Windows PowerShell에서 이 폴더로 이동해 다음을 실행합니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

빌드 스크립트는 Pillow와 PyInstaller를 설치하고 `%LOCALAPPDATA%\QuotaWidget\app\QuotaWidget`에 폴더형 무설치 실행본을 만듭니다. Python, Tcl/Tk, Pillow를 실행 폴더에 포함합니다. Codex 앱은 별도로 설치되어 있어야 합니다. 배포 전 인터넷이 끊긴 Windows 사용자 계정에서 실행해 보는 것을 권장합니다.

```text
%LOCALAPPDATA%\QuotaWidget\app\QuotaWidget\Start-Widget.cmd
```

개발 실행은 Python 3.12 이상과 Pillow가 있는 환경에서 `python src/main.py`로 할 수 있습니다. `--demo --close-after-seconds 5`는 42% 화면을 띄웁니다. `--probe`는 숫자를 출력하지 않고 실제 한도 조회 성공 여부만 보여줍니다. Codex 설치 경로가 다르면 `--codex-path C:\path\codex.exe`를 지정합니다. Python 시험 설정은 기존 PowerShell 앱 설정과 분리된 `%LOCALAPPDATA%\QuotaWidget\settings.json`에 저장됩니다.

## 검사와 메모리 측정

```powershell
python -m unittest discover -s tests -v
python src/main.py --probe
```

출시 실행본의 메모리를 포함한 실제 조회 과정을 측정하려면 먼저 위젯을 종료하고 다음을 실행합니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\measure-memory.ps1
```

기본값은 125초 동안 5초 간격으로 샘플링합니다. 위젯과 자식 프로세스(한도 조회용 Codex app-server)의 Windows 작업 집합과 Private Bytes를 각각 더해 CSV에 기록합니다. 이 수치는 작업 집합 합계의 공유 페이지 중복 가능성, 시작 구간, 앱-server 실행 여부에 따라 달라집니다. GUI 단독과 app-server 포함 값을 구분해 해석해야 하며, 특정 메모리 상한을 보장하지 않습니다.

`measure-memory.ps1`의 기본값은 조회 프로세스를 포함한 측정을 목표로 합니다. 조회 로그인 상태와 Codex 버전에 따라 프로세스가 늦게 시작되거나 거부될 수 있습니다. 측정 중에는 위젯을 종료하지 마세요.

## 현재 구현 범위

- 메뉴: `Codex`·`Claude` 선택, `사슴 모양`의 동글 사슴·작은 뿔 사슴, `크기`의 128 px·160 px, `종료`
- 시작 위치: 주 화면 오른쪽 위에서 24 px 안쪽
- 작업 표시줄 숨김 및 항상 위: Windows Tk 창을 테두리 없는 tool window로 표시
- 실패 시: 현재 숫자와 채움 높이 유지, 회색으로 바꾸고 오류 원인을 툴팁에 표시, 1분 뒤 재시도
- 자동 시작, 주간 사용률, 추가 표정·애니메이션은 포함하지 않음
