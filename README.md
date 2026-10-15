# Quota Widget

Codex · Claude의 5시간 사용률을 보여주는 Windows용 위젯입니다.

**[릴리즈 · EXE 다운로드](https://github.com/froggy0m0/quota-widget/releases/latest)**

무설치 EXE를 실행하고, 우클릭으로 Codex / Claude를 선택하세요.

- **Codex:** 해당 PC에 Codex를 설치하고 로그인해야 합니다.
- **Claude:** Claude Code 사용률을 아래 파일에 저장하는 별도 설정이 필요합니다. 위젯은 이 파일을 읽기만 합니다.

```text
%USERPROFILE%\.claude\usage-widget\usage.json
```

사용률 파일의 JSON 형식 (`resets_at`은 리셋 시각의 Unix 초):

```json
{"used_percentage": 43, "resets_at": 1791979800}
```

파일이 없거나 읽을 수 없으면 사용률에 `—`가 표시됩니다.
