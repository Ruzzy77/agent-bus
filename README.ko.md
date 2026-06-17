# agent-bus

[English](README.md)

> 멀티 에이전트 판단 공유를 위한 로컬 협업 도구

협업할 에이전트들을 `/agent-bus-loop`로 같은 bus에 연결해 요청과 상태, 근거와 판단을 공유하며 작업을 진행합니다.

- 에이전트 사이의 메시지, 작업 상태, 티켓, heartbeat 공유를 위한 메시징 허브
- 로컬 상태 저장소: JSON/JSONL 파일 기반 (`./.agent-bus/`)
- 로컬 대시보드 (`127.0.0.1`)

## Dashboard demo

![agent-bus dashboard demo](agentbus/examples/demo-bus/dashboard-demo.png)

## Features

- 메시지, 작업, 티켓, 에이전트 상태 공유
- 위험하거나 사람 확인이 필요한 작업의 optional ticket 검토
- 에이전트 lifecycle: join, watch, inbox/stop 확인, 작업, 보고, 대기
- `/agent-bus-loop` 또는 `agentbus loop` 기반 agent loop entry
- adapter cursor와 실패 상태 확인
- 공유 판단 기록용 assessment summary
- webhook, SDK runner, A2A 호출, 로컬 스크립트용 optional event stream
- 무인 agent runner와 event bridge용 optional wakeup profile
- 선택 기능으로 제공되는 Codex와 Claude runner 예제
- 외부 모델 호출용 OpenAI-compatible HTTP adapter 예제
- 외부 adapter용 NDA-aware 최소 보호장치
- 로컬 파일과 CLI 기반 동작
- localhost 대시보드

## Components

- Bus state: 프로젝트 내 bus 디렉터리(`.agent-bus/`)의 JSON/JSONL 파일
- Dashboard: 로컬 브라우저 (`127.0.0.1:<port>`)
- Agent workflow: `agent-bus-loop` entry skill과 `agentbus workflow` 프롬프트 텍스트
- Tickets: 사람 수락 후 task로 진행할 후보 작업
- Event bridges: event를 받은 뒤 bus를 다시 읽고 외부 동작을 실행하는 스크립트
- Adapter status: payload 본문 재출력 없는 event bridge cursor와 실패 요약
- Wakeup profiles: agent runner와 event bridge용 JSON 설정
- Packet builder: A2A/AAS JSON request, response 처리, packet 생성

## Quick start

- agent-bus CLI 설치
- 사용할 프로젝트 디렉터리에서 bus 생성
- 활성 에이전트 thread에서 `/agent-bus-loop` 시작 또는 `agentbus loop` 출력 붙여넣기
- Codex, Claude, peer agent에 같은 `AGENTBUS_BUS_DIR` 또는 `--bus-dir` 전달
- 요청, 상태, 보고, 참조, task state를 bus로 공유
- localhost 대시보드 실행 (사용자 모니터링 필요 시)
- 사람 수락 없이 진행 가능한 일은 직접 task와 request message로 전달
- 자율작업 흐름을 우선하고, 반복적인 다음 작업을 ticket으로 만들지 않음
- 사람 검토 없이는 안전하게 진행하기 어려운 새 제안이나 크리티컬한 검토 대상만 ticket으로 등록
- 무인 polling이나 event bridge가 필요할 때만 `watch-events` 또는 `wakeup` 실행

### 1. Install

```bash
uv tool install agent-bus              # 또는: pipx install agent-bus
python -m agentbus --help              # 소스 체크아웃에서 직접 실행
```

### 2. (Optional) Install skills

- `agent-bus-loop`: "start loop", "stop loop", slash-style `/agent-bus-loop` 요청용 작은 entry skill
- `agent-bus-workflow`: inbox, ack, task state, stop, ticket, bridge 처리를 위한 전체 workflow skill
- Skill을 불러오지 않는 런타임: `agentbus loop` 출력을 prompt에 삽입하고, 전체 규칙은 `agentbus workflow`로 확인
- 복사 후 에이전트 런타임 재시작 (필요 시)

```bash
: "${AGENT_SKILLS_DIR:?set the agent runtime skills directory}"
mkdir -p "$AGENT_SKILLS_DIR"
skills_src="$(dirname "$(dirname "$(agentbus workflow --path)")")"
for src in "$skills_src"/agent-bus-*; do
  dst="$AGENT_SKILLS_DIR/$(basename "$src")"
  test ! -e "$dst" || { echo "already exists: $dst"; continue; }
  cp -R "$src" "$dst"
done
```

### 3. Start a bus

```bash
cd ~/my-project
agentbus init
agentbus serve      # http://127.0.0.1:8765
```

### 4. Demo bus

Dashboard screenshot이나 로컬 UI 확인에는 packaged demo bus를 씁니다. 수정이 필요하면 복사본에서 실행합니다.

```bash
DEMO=$(agentbus examples demo-bus)
AGENTBUS_BUS_DIR="$DEMO" agentbus serve --port 8791
```

### 5. Agent loop

활성 에이전트에게 `/agent-bus-loop`를 요청합니다. Skill을 설치했다면 해당 entry를 쓰고, 아니면 `agentbus loop` 출력을 thread에 붙여넣습니다.

```bash
agentbus check-stop
agentbus status --agent my-agent --state running --note "started"
agentbus inbox --agent my-agent
agentbus send --from my-agent --to all --kind report --subject "status" --body "..."
agentbus task-state --id t-xxxx --state completed --by my-agent
```

### 6. Direct work request

사람 수락 없이 진행 가능한 작업은 이 경로를 씁니다.

```bash
TASK_ID=$(agentbus task-new --title "review adapter wording" --by user --assign my-agent)
agentbus send --from user --to my-agent --kind request \
  --subject "review adapter wording" \
  --body "Review the current wording and report the smallest safe change" \
  --task "$TASK_ID"
```

### 7. Ticket intake

Ticket은 새로운 제안, 위험한 변경, 사람 검토 후 진행해야 하는 작업에만 씁니다. 안전하게 계속할 수 있는 작업이 있으면 ticket이 활성 loop를 멈추게 하지 않습니다.

```bash
agentbus ticket-new --title "review adapter wording" --by user
agentbus ticket-accept --id i-xxxx --by user --to my-agent --note "keep wording neutral"
agentbus task-state --id t-xxxx --state input_required --by my-agent --note "decision needed"
```

### 8. Event bridge

```bash
agentbus watch-events --types message.created,ticket.created \
  --target reviewer \
  --cursor-file .agent-bus/adapters/reviewer.cursor \
  --fail-log .agent-bus/adapters/reviewer.failures.jsonl \
  --exec agentbus/examples/adapters/a2a-outbound.sh
```

### 9. Wakeup profile

```bash
PROFILE=$(agentbus examples wakeup/claude-inbox.json)
agentbus wakeup-check --file "$PROFILE"
agentbus wakeup --profile "$PROFILE" --once
A2A_ENDPOINT=https://example.com/a2a/rpc \
  agentbus wakeup --profile "$(agentbus examples wakeup/a2a-events.json)"
```

Profile은 운영자나 에이전트 런타임이 실행할 command 입력이며, bus는 상태를 기록할 뿐 에이전트 프로세스를 소유하지 않습니다.

### 10. OpenAI-compatible adapter

```bash
export OPENAI_COMPAT_ENDPOINT=https://model-gateway.example/v1/chat/completions
export OPENAI_COMPAT_MODEL=assessment-router
export OPENAI_COMPAT_TOKEN_ENV=MODEL_GATEWAY_API_KEY
export OPENAI_COMPAT_RESPONSE_TO=operator
agentbus aas-packet --asset-id urn:example:asset:line-7-press-2 \
  --data agentbus/examples/aas/operational-data.sample.json \
  --assessment-summary agentbus/examples/aas/assessment-summary.sample.json |
  "$(agentbus examples adapters/openai-compatible.sh)"
```

### 11. Agent runner example

```bash
agentbus ticket-accept --id i-xxxx --by user --to my-agent --note "run"
export AGENT_RUNNER_COMMAND='your-agent-command --json'
agentbus wakeup --profile "$(agentbus examples wakeup/agent-runner-inbox.json)" --once
```

### 12. Codex CLI runner

Prerequisites

- shell에서 `codex exec --help` 실행 가능
- Codex CLI login 완료
- `CODEX_RUNNER_CWD`는 에이전트가 확인할 프로젝트 경로

```bash
cd ~/my-project
agentbus init

TASK_ID=$(agentbus task-new --title "codex runner smoke" --by user --assign codex)
agentbus send --from user --to codex --kind request \
  --subject "runner smoke" \
  --body "Do not inspect files or run commands. Return exactly: agentbus-codex-ok" \
  --task "$TASK_ID"

PROFILE=$(agentbus examples wakeup/codex-runner-inbox.json)
agentbus wakeup --profile "$PROFILE" --once --dry-run
CODEX_RUNNER_MODE=cli \
  CODEX_RUNNER_CWD="$PWD" \
  CODEX_RUNNER_SANDBOX=read-only \
  CODEX_RUNNER_EXTRA_ARGS="--ephemeral" \
  agentbus wakeup --profile "$PROFILE" --once

agentbus inbox --agent codex
```

사람 검토가 필요한 작업은 `task-new`와 `send`를 직접 쓰지 않고 ticket 생성 후 `codex`로 accept합니다.

### 13. Codex SDK runner

`openai-codex`는 runner 환경의 선택 의존성이며, agent-bus가 설치하지 않습니다.

```bash
python -m venv .venv-codex-runner
. .venv-codex-runner/bin/activate
python -m pip install openai-codex

agentbus send --from user --to codex --kind request \
  --subject "sdk runner smoke" \
  --body "Do not inspect files or run commands. Return exactly: agentbus-codex-sdk-ok"

PROFILE=$(agentbus examples wakeup/codex-runner-inbox.json)
agentbus wakeup --profile "$PROFILE" --once --dry-run
CODEX_RUNNER_MODE=sdk \
  CODEX_RUNNER_CWD="$PWD" \
  CODEX_RUNNER_SANDBOX=read-only \
  agentbus wakeup --profile "$PROFILE" --once
```

### 14. Claude CLI runner

Prerequisites

- shell에서 `claude -p "hello"` 실행 가능
- Claude Code CLI login 완료
- `CLAUDE_RUNNER_CWD`는 에이전트가 확인할 프로젝트 경로

```bash
cd ~/my-project
agentbus init

TASK_ID=$(agentbus task-new --title "claude runner smoke" --by user --assign claude)
agentbus send --from user --to claude --kind request \
  --subject "runner smoke" \
  --body "Do not inspect files or run commands. Return exactly: agentbus-claude-ok" \
  --task "$TASK_ID"

PROFILE=$(agentbus examples wakeup/claude-runner-inbox.json)
agentbus wakeup --profile "$PROFILE" --once --dry-run
CLAUDE_RUNNER_MODE=cli \
  CLAUDE_RUNNER_CWD="$PWD" \
  CLAUDE_RUNNER_PERMISSION_MODE=plan \
  agentbus wakeup --profile "$PROFILE" --once

agentbus inbox --agent claude
```

### 15. Claude Agent SDK and Messages API runners

`claude-agent-sdk`와 `ANTHROPIC_API_KEY`는 runner 환경의 선택 입력이며, agent-bus가 설치하거나 저장하지 않습니다. `api` mode는 Messages API request 1개를 보내며, 자체로 로컬 파일이나 shell tool을 제공하지 않습니다.

```bash
python -m venv .venv-claude-runner
. .venv-claude-runner/bin/activate
python -m pip install claude-agent-sdk
export ANTHROPIC_API_KEY=...

agentbus send --from user --to claude --kind request \
  --subject "sdk runner smoke" \
  --body "Do not inspect files or run commands. Return exactly: agentbus-claude-sdk-ok"

PROFILE=$(agentbus examples wakeup/claude-runner-inbox.json)
agentbus wakeup --profile "$PROFILE" --once --dry-run
CLAUDE_RUNNER_MODE=sdk \
  CLAUDE_RUNNER_CWD="$PWD" \
  CLAUDE_RUNNER_PERMISSION_MODE=plan \
  agentbus wakeup --profile "$PROFILE" --once

CLAUDE_RUNNER_MODE=api \
  CLAUDE_RUNNER_MODEL=claude-sonnet-4-5 \
  agentbus wakeup --profile "$PROFILE" --once
```

### 16. Codex app use

Codex app은 활성 thread 안에서 agent-bus를 도구로 사용합니다. 자동 app wakeup은 package 범위 밖입니다.

```bash
cd ~/my-project
agentbus init
agentbus workflow > /tmp/agentbus-workflow.md
```

Codex app thread에 넣을 prompt

```text
Use agent-bus for this thread.
You are codex.
Bus directory: /absolute/path/to/my-project/.agent-bus

Read the workflow from agentbus workflow or from the installed agent-bus-workflow skill.
Start by running:
agentbus check-stop
agentbus status --agent codex --state running --note "joined"
agentbus inbox --agent codex

Handle request messages, ack only handled messages, update task-state when a task id exists, and report with agentbus send.
```

### 17. Claude Code use

Claude Code는 활성 thread 안에서 agent-bus를 도구로 사용합니다. 자동 app wakeup은 package 범위 밖입니다.

```bash
cd ~/my-project
agentbus init
agentbus loop > /tmp/agentbus-loop.md
```

Claude thread에 넣을 prompt

```text
Use agent-bus for this thread.
You are claude.
Bus directory: /absolute/path/to/my-project/.agent-bus

Start /agent-bus-loop if the skill is installed. Otherwise read the loop text from agentbus loop and the full workflow from agentbus workflow.
Start by running:
agentbus check-stop
agentbus status --agent claude --state running --note "joined"
agentbus inbox --agent claude

Handle request messages, ack only handled messages, update task-state when a task id exists, and report with agentbus send.
```

Command contract

- Input: `agent-runner-work.v1` JSON 1개를 stdin으로 전달
- Output: stdout을 report body로 기록
- Success: report message, task completion, source-message ack
- Failure: task failure, ack 없음, pending message 재시도 가능
- Runtime-specific command: `AGENT_RUNNER_COMMAND`에 운영자 script 또는 CLI wrapper 지정

### 18. A2A and AAS packet

```bash
MSG_ID=$(agentbus send --from operator --to reviewer --kind request --subject "Pressure check" --body "Review the attached data")
agentbus aas-packet --asset-id urn:example:asset:line-7-press-2 \
  --data agentbus/examples/aas/operational-data.sample.json \
  --assessment-summary agentbus/examples/aas/assessment-summary.sample.json \
  --out packet.json
agentbus a2a-rpc --message-id "$MSG_ID" --data packet.json --out request.json
agentbus a2a-post --file request.json --endpoint https://example.com/a2a/rpc \
  --token-env A2A_TOKEN --record-response-to operator
```

### 19. Sensitive data

```bash
MSG_ID=$(agentbus send --from operator --to reviewer --kind request \
  --subject "NDA review" --body "Review local NDA data" \
  --sensitivity confidential --retention no_archive)
agentbus a2a-rpc --message-id "$MSG_ID" --out request.json
agentbus a2a-post --file request.json --endpoint https://example.com/a2a/rpc --allow-sensitive
agentbus security-check
```

## Reference

### States

- Task states: `submitted`, `working`, `input_required`, `completed`, `failed`, `canceled`
- Agent states: `running`, `waiting`, `done`, `error`

### Local endpoints

- Dashboard bind: `127.0.0.1`
- Dashboard views: 메시지 타임라인, 작업, 티켓, 에이전트 상태, 정지 요청, 메시지 보관/비우기
- Local testing endpoints: `/.well-known/agent-card.json?agent=<id>`, `/a2a/rpc`
- External hosting, discovery, authentication, streaming, SDK wakeup: adapter 범위

### Security guardrails

- Local store: plain JSON/JSONL, 파일 권한과 데이터 거버넌스는 운영자 관리
- `sensitivity`: `public`, `internal`, `confidential`, `restricted`
- `retention`: `normal`, `session`, `no_archive`
- Outbound `a2a-post`, `watch-events`, `wakeup`: `confidential`, `restricted`는 명시적 허용 없으면 차단
- Blocked `watch-events`, `wakeup` output: payload 본문이 아닌 redacted notice 출력
- `no_archive`: `rotate` 시 archive로 옮기지 않고 active message log에 유지
- Dashboard write APIs: local origin과 JSON POST만 허용
- Token handling: `--token-env` 우선 사용, shell history와 bus message에 직접 토큰 기록 금지

### Commands

| 명령 | 용도 |
| --- | --- |
| `init`, `show-status`, `check-stop` | bus 생성, 상태 확인, 정지 요청 확인 |
| `send`, `inbox`, `ack`, `message-delete` | 메시지 교환과 관리 |
| `status` | 에이전트 heartbeat와 상태 갱신 |
| `task-new`, `task-state`, `task-list`, `task-delete` | 작업 수명주기 관리 |
| `ticket-new`, `ticket-list`, `ticket-accept`, `ticket-reject` | 사람 검토가 필요한 후보 작업 |
| `events`, `watch-events`, `wakeup`, `wakeup-check` | bus event 읽기, adapter 실행, wakeup profile 실행 |
| `adapter-status` | adapter cursor와 실패 요약 출력 |
| `serve` | localhost 대시보드 실행 |
| `clear`, `rotate` | 현재 메시지 비우기와 메시지 로그 보관 |
| `security-check` | 로컬 보호장치와 민감 기록 개수 점검 |
| `workflow` | 에이전트 협업 절차 출력 |
| `examples` | 패키지 예제 경로 출력 |
| `aas-packet`, `aas-packet-check` | AAS 형식 packet 생성과 검사 |
| `a2a-card`, `a2a-rpc`, `a2a-rpc-check`, `a2a-post` | A2A용 JSON 생성, 검사, 전송, 응답 기록 |

### Configuration

우선순위: CLI 인자, `AGENTBUS_*` 환경변수, 현재 작업 디렉터리 기본값

| 환경변수 | 용도 |
| --- | --- |
| `AGENTBUS_BUS_DIR` | bus 디렉터리 (`--bus-dir`) |
| `AGENTBUS_CARDS_DIR` | 에이전트 카드 디렉터리 (`--cards-dir`) |
| `AGENTBUS_ROOT` | 파일 색인 루트 (`serve --root`) |
| `AGENTBUS_PORT` | 대시보드 포트 (`serve --port`) |
| `AGENTBUS_MAX_BYTES` | 메시지 로그 자동 회전 임계값, 기본 5 MB, `0`이면 비활성 |
| `AGENTBUS_ARCHIVE_KEEP` | 유지할 archive 개수, 기본 `0`은 전체 유지 |

### Python API

사용 가능한 Python 모듈: `agentbus.bus`, `agentbus.assessment`, `agentbus.a2a`

```python
from pathlib import Path
from agentbus import a2a, assessment, bus

bd = Path(".agent-bus")
msg = bus.make_message("my-agent", "all", "note", "subject", "body")
bus.append_message(bd, msg)
events = bus.bus_events(bd, types={"message.created"})
packet = assessment.assessment_packet(bd, {"value": 1}, "urn:asset:1")
request = a2a.send_message_request(msg)
```

### Package contents

- Wakeup profile 예제: `agentbus/examples/wakeup`
- Adapter 예제: `agentbus/examples/adapters`
- Demo dashboard bus: `agentbus/examples/demo-bus`
- 수식 렌더링: `vendor/katex`
- License: MIT

### Release check

소스 체크아웃에서 배포 전 실행

```bash
agentbus/examples/smoke/publish-smoke.sh
uv build --sdist --wheel --out-dir /tmp/agentbus-dist
python -m twine check /tmp/agentbus-dist/*   # optional
```

### Related standards

- A2A: [Agent2Agent Protocol specification](https://a2a-protocol.org/latest/specification/)
- A2A: [a2aproject/A2A repository](https://github.com/a2aproject/A2A)
- AAS: [IDTA AAS specifications](https://industrialdigitaltwin.io/aas-specifications/index/home/index.html)
- AAS: [Part 1: Metamodel](https://industrialdigitaltwin.io/aas-specifications/IDTA-01001/v3.1.2/index.html)
- AAS: [Part 2: Application Programming Interfaces](https://industrialdigitaltwin.io/aas-specifications/IDTA-01002/v3.1.2/index.html)
