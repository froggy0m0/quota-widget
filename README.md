# Quota Widget — Python + Tkinter

Windows에서 Python으로 실행하는 128 px 사슴 위젯입니다. 우클릭으로 `Codex` / `Claude`, 사슴 모양, 128 / 160 px 크기를 선택하며 선택을 저장합니다. 드래그 이동, 항상 위, 작업 표시줄 숨김을 지원합니다. Pillow의 RGBA 합성과 Windows `UpdateLayeredWindow`를 사용해 반투명 영역과 픽셀 그림을 표시합니다.

## Python 실행

Windows용 Python 3.12 이상(Tkinter 포함)이 필요합니다. Windows 터미널에서 이 폴더로 이동하고 최초 한 번 실행합니다.

```powershell
py -3 -m pip install -r requirements.txt
```

`py`가 PATH에 없으면 설치된 Windows Python의 `python.exe`로 위 설치 명령을 실행하세요.

이후 `start-python.cmd`를 실행하거나 다음 명령을 사용합니다.

```powershell
py -3 src/main.py
py -3 src/main.py --provider claude
```

실행 스크립트는 폴더의 `.venv\Scripts\python.exe`, Windows Python Launcher(`py -3`), PATH의 `python`, `%LOCALAPPDATA%\Programs\Python`의 설치본 순서로 선택합니다. `.venv`를 사용하면 해당 Python에 Pillow를 설치하세요. WSL에 소스를 두었더라도 위젯은 **Windows Python**으로 실행해야 합니다. 경로를 코드에 고정하지 않고 스크립트가 있는 폴더에서 시작합니다.

설정은 `%LOCALAPPDATA%\QuotaWidget\settings.json`에 저장합니다. `--provider`는 이번 실행의 서비스를 지정하고, 우클릭으로 변경한 선택은 저장됩니다. `--demo --close-after-seconds 5`는 샘플 42% 화면을 띄웁니다.

## Claude 로컬 파일 연동 규격

Claude는 사용자 홈에서 다음 파일을 **읽기만** 합니다. 사용자 이름이나 드라이브 경로를 코드에 고정하지 않습니다.

```text
~/.claude/usage-widget/usage.json
Windows: %USERPROFILE%\.claude\usage-widget\usage.json
```

파일 형식:

```json
{"used_percentage": 43, "resets_at": 1791979800}
```

- `used_percentage`: 5시간 구독 한도에서 **사용한 비율**, 0~100 숫자. 소수 사용 가능.
- `resets_at`: 5시간 창이 리셋되는 시각, Unix epoch **초**.
- 파일이 없거나 읽을 수 없거나 형식이 잘못되면 `—`를 표시합니다. 이전 숫자도 지웁니다.
- 유효한 파일의 `resets_at`이 현재 시각보다 이르면 `0%`를 표시합니다.
- 그 외에는 `round(used_percentage)%`를 표시합니다. 숫자 패널에는 사용률만 표시합니다.
- Claude를 선택하면 즉시 읽고, 이후 **60초마다** 다시 읽습니다.

Claude 쪽에서 위 형식으로 파일을 저장하면 위젯이 읽어 표시합니다. 위젯의 상태는 두 가지입니다. 유효한 파일이 있으면 사용률, 없거나 읽을 수 없으면 `—`와 `Claude 연결 안됨` 툴팁을 표시합니다. 파일이 다시 정상적으로 저장되면 다음 조회에서 사용률 표시로 돌아갑니다.

## Codex 조회

Codex 앱을 설치하고 ChatGPT 계정으로 로그인하세요. 위젯은 `codex.exe app-server --listen stdio://`를 실행하며 `initialize`, `initialized`, `account/rateLimits/read`만 전송합니다. 300분 창의 `usedPercent`를 60초마다 조회합니다. 오류 시 마지막 숫자를 회색으로 유지합니다.

Codex 설치 경로를 자동으로 찾지 못하면 `--codex-path C:\path\codex.exe`를 지정합니다.

## 확인

```powershell
py -3 -m unittest discover -s tests -v
py -3 src/main.py --provider claude --probe
py -3 src/main.py --provider codex --probe
```

확인은 지정된 경로에 위 형식의 샘플 파일을 저장해 숫자가 표시되는지, 파일을 제거했을 때 `—`로 돌아가는지 확인하면 됩니다. 샘플 확인 후에는 테스트 파일을 제거하세요.

`build-windows.ps1`과 `requirements-build.txt`는 추후 EXE 패키징용입니다. 현재 실행은 Python을 사용합니다.
