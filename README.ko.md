# agent-bus

[English](README.md)

> 여러 에이전트가 같은 로컬 기록을 보며 요청, 상태, 보고, 판단 재료를 이어가는 작업 공유 도구

프로젝트에서 `agentbus bus serve`를 실행하면 secure capsule channel과 대시보드가 열립니다. Codex, Claude, Gemini, 로컬 teammate는 이 channel에 메시지, task, ticket, 보고를 남기고 같은 기록을 읽습니다.

lead는 사용자가 남긴 요청을 읽어 task, ticket, stop, Key Context로 정리합니다. teammate가 남긴 판단은 lead가 다시 보고 다음 작업 방향과 종료 보고로 묶습니다.

## Dashboard

![agent-bus dashboard demo](agentbus/resources/demo-bus/dashboard-demo.png)

## Overview

- Message: 사용자가 남긴 요청과 에이전트 보고를 기록합니다.
- Task: 실제로 진행할 작업과 상태를 관리합니다.
- Ticket: 사용자 검토 뒤 작업으로 옮길 후보를 남깁니다.
- Key Context: 현재 작업을 어떤 관점에서 이어갈지 적습니다.
- Teammate: bus request가 들어오면 로컬 CLI 에이전트를 깨웁니다.
- Bridge: bus event를 watcher, webhook, model API, A2A 경계로 넘깁니다.
- Packet: AAS data packet과 A2A request/response를 만듭니다.
- Secure capsule: `.agent-bus/` 안에 암호화 저장소를 두고 token으로 원문 보기를 제어합니다.

## Lifecycle

목표와 경계만 정하면 바로 시작합니다. 설치된 skill이 있는 에이전트에게 `/agent-bus-loop` 또는 “agent-bus로 협업 루프를 시작해줘”라고 요청하면, 첫 에이전트가 lead를 맡아 요구사항 정리부터 종료 보고까지 진행합니다.

```text
/agent-bus-loop
이 프로젝트에서 agent-bus로 협업 루프를 시작해줘.
목표: <완료하고 싶은 일>
피할 범위: <건드리지 않을 것>
필요하면 요구사항을 먼저 정리하고, bus 준비부터 종료 보고까지 안내해줘.
```

Lead는 다음 일을 맡습니다.

- 목표, 범위, 민감 데이터 여부, 참여할 teammate, 완료 기준을 정리합니다.
- 작업의 의미와 판단 성격을 보고 task, ticket, request를 나눕니다.
- Key Context에 현재 작업을 해석하는 기준을 남깁니다.
- 각 teammate 요청에는 담당 범위, 확인할 자료, 보고 형식, 다음 cycle 조건을 담습니다.
- teammate 보고가 모이면 lead가 원자료와 산출물을 다시 보고 판단을 합칩니다.
- 사용자 결정이 필요하면 `input_required`나 user request로 올립니다.
- 종료 전 lead inbox를 다시 확인하고, 남은 일은 follow-up task나 ticket으로 남깁니다.
- 마지막 report로 종료 보고서를 남긴 뒤 task를 `completed`, agent를 `done`, bus를 `loop_closed`로 닫습니다.

사용자는 대시보드 메시지 작성 영역에서 `메모`, `요청`, `보고`, `작업`, `티켓`, `정지`를 남깁니다. 작업·티켓·정지는 lead에게 보내는 관리 요청입니다. lead는 그 요청을 현재 맥락에 맞게 실제 기록으로 옮깁니다.

## Key Context

Key Context는 사용자와 lead가 함께 다듬는 현재 작업의 핵심 맥락입니다. 상태와 메시지는 각각의 보기에서 확인합니다. Key Context에는 이어지는 판단에서 놓치면 안 되는 작업 의도와 해석 기준을 남깁니다.

- task 목록, agent 상태, message 요약은 각각의 보기에서 확인합니다.
- 일반 지침과 runner 설정은 skill과 profile에 둡니다.
- Key Context에는 지금 작업을 어떤 관점에서 이어갈지 남깁니다.
- 민감한 원문은 `restricted` message, task, ticket이나 파일 참조에 둡니다.
- lead는 teammate cycle 전에 Key Context를 확인해 다음 요청의 방향을 맞춥니다.
- `teammate run`은 Key Context를 cycle 입력에 넣고, prompt에는 `<agent-bus-system>` block으로 구분해 전달합니다.
- CLI에서는 `agentbus context show`와 `agentbus context set --stdin`으로 확인하거나 갱신합니다.

## Quick Start

### Install

```bash
uv tool install git+https://github.com/Ruzzy77/agent-bus.git
# 또는: pipx install git+https://github.com/Ruzzy77/agent-bus.git

git clone https://github.com/Ruzzy77/agent-bus.git
cd agent-bus
python -m pip install .
python -m agentbus --help
```

### Start a bus

```bash
cd ~/my-project
agentbus bus init
agentbus bus serve      # http://127.0.0.1:8765
```

- `AGENTBUS_BUS_DIR` 또는 `--bus-dir`로 여러 agent가 같은 channel을 선택합니다.
- `agentbus bus serve`가 secure capsule API와 대시보드를 함께 엽니다.
- daemon이 꺼져 있으면 agent가 쓰는 명령은 연결 오류를 반환합니다.

### Try the demo bus

패키지에 들어 있는 demo bus를 임시 디렉터리로 복사해 대시보드를 확인합니다. send, delete, auth 동작은 복사본에만 기록됩니다.

```bash
DEMO_WORK=$(mktemp -d "${TMPDIR:-/tmp}/agentbus-demo.XXXXXX")
cp -R "$(agentbus resource path demo-bus)" "$DEMO_WORK/bus"
echo "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus migrate --from "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus serve --port 8791
```

다른 shell에서 demo viewer token을 발급합니다.

```bash
export AGENTBUS_BUS_DIR=<위에서 출력된 demo bus path>
agentbus auth demo
```

- demo token은 1시간 동안 유효합니다.
- demo token은 실행할 때마다 새로 발급합니다.
- 인증 뒤 demo의 restricted 메시지와 티켓을 열어 봅니다.

### Join as an agent

활성 에이전트에게 `/agent-bus-loop`를 요청하면 현재 thread가 bus loop에 합류합니다.

```bash
agentbus bus status --stop-exit-code
agentbus agent set --name my-agent --state running --note "started"
agentbus agent inbox --name my-agent
agentbus message send --from my-agent --to all --kind report --subject "status" --body "..."
agentbus task state --id t-xxxx --state completed --by my-agent
agentbus agent ack --name my-agent m-xxxx
```

- 설치된 skill이 있으면 `/agent-bus-loop`로 시작합니다.
- 텍스트 prompt 환경에서는 `agentbus guide loop` 출력을 붙여 넣습니다.
- `agentbus agent create --name` 또는 첫 `agentbus agent set --name`에서 내부 `a-...` id가 등록됩니다.
- `teammate run`이 성공한 cycle을 기록하면, 그 cycle을 시작한 request를 자동 ack합니다.

### Request work directly

에이전트 판단으로 바로 진행할 작업은 task와 request message로 시작합니다.

```bash
TASK_ID=$(agentbus task new --title "dashboard composer alignment review" --by user --assign my-agent)
agentbus message send --from user --to my-agent --kind request \
  --subject "composer alignment review" \
  --body "판단 성격: interaction design. 대상: dashboard composer controls. 인접 영향: focus, dark mode, send button alignment. 1줄/여러 줄 입력 상태를 확인하고, 가장 작은 안전한 수정과 남은 위험을 report로 남겨줘." \
  --task "$TASK_ID"
```

### Use tickets

Ticket은 사람 검토 뒤 task로 옮길 후보 작업에 씁니다.

```bash
agentbus ticket new --title "dashboard composer follow-up" --by user
agentbus ticket accept --id i-xxxx --by user --to my-agent --note "keep wording neutral"
agentbus task state --id t-xxxx --state input_required --by my-agent --note "decision needed"
```

## Skills

agent-bus의 skill은 에이전트가 시작 절차를 찾고, 프로젝트 안에서 다시 쓸 작업 흐름을 남길 때 씁니다.

### Agent loop skills

- `agent-bus-loop`: loop 시작, 중단, 종료 요청용 진입 skill
- `agent-bus-workflow`: inbox, ack, task state, stop, ticket, bridge 처리 workflow
- `lead-strategic-approach`: 예상 그림, 사용자 정렬, Key Context 조율, teammate fan-out, 인과 점검을 다루는 lead skill
- `agentbus guide loop`: prompt에 붙여 넣을 loop 시작 안내 출력
- `agentbus guide workflow`: 전체 workflow와 종료 보고 안내 출력

```bash
: "${AGENT_SKILLS_DIR:?set the agent skills directory}"
mkdir -p "$AGENT_SKILLS_DIR"
skills_src="$(dirname "$(dirname "$(agentbus guide workflow --path)")")"
for src in "$skills_src"/*; do
  test -d "$src" || continue
  dst="$AGENT_SKILLS_DIR/$(basename "$src")"
  test ! -e "$dst" || { echo "already exists: $dst"; continue; }
  cp -R "$src" "$dst"
done
```

### Local skills

로컬 스킬은 프로젝트 안에서 다시 쓸 작업 흐름을 남기는 기록입니다.

- 실제 작업 중 다시 쓸 흐름이나 고친 경로가 생기면 `.agent-bus/skills/<skill-id>/SKILL.md`에 남깁니다.
- 사용 근거는 `agentbus skill evidence`로 추가합니다.
- `agentbus guide loop`와 `agentbus guide workflow`는 시작 지점에서 로컬 스킬 요약을 함께 표시합니다.
- 종료 판단에서는 `agentbus skill review`로 유지, 보관, 설치 후보, 묶기, 줄이기를 결정합니다.
- 검수를 처리한 경계는 `agentbus skill state`로 남깁니다.

```bash
agentbus skill new loop-close --description "종료 보고를 짧고 추적 가능하게 남긴다"
agentbus skill list
agentbus skill show <skill-id>
agentbus skill evidence <skill-id> --type check --ref <message-or-file-ref> --note "재사용할 관찰"
agentbus skill review
agentbus skill state <skill-id> --state active
```

## Data Handling

### A2A/AAS packet

내부 협업은 `message`, `task`, `ticket`, `bridge`로 진행합니다. `packet`은 A2A나 AAS 같은 외부 protocol 경계에서 사용합니다.

- `packet data --protocol aas`: AAS-compatible data packet 생성 또는 검사
- `packet transport --protocol a2a`: A2A request/card 생성 또는 검사
- `packet send`/`packet receive`: 외부 A2A 경계 처리
- 공개 A2A hosting과 인증된 AAS conformance: 별도 통합 코드나 서비스 영역

```bash
MSG_ID=$(agentbus message send --from operator --to reviewer --kind request --subject "Pressure check" --body "Review the attached data")
agentbus packet data --protocol aas --asset-id urn:example:asset:line-7-press-2 \
  --data agentbus/resources/aas/operational-data.sample.json \
  --assessment-summary agentbus/resources/aas/assessment-summary.sample.json \
  --out packet.json
agentbus packet transport --protocol a2a --artifact message --message-id "$MSG_ID" --data packet.json --out request.json
agentbus packet send --protocol a2a --file request.json --endpoint https://example.com/a2a/rpc \
  --token-env A2A_TOKEN --record-response-to operator
```

### Sensitive data

민감 데이터는 sensitivity와 token 권한으로 다룹니다.

- `normal`: 로컬/외부 원문 사용 가능
- `internal`: 로컬 원문 공유, 외부에는 redacted view 전송
- `restricted`: 권한 있는 agent와 dashboard viewer만 원문 열람
- agent 원문 보기: `AGENTBUS_AGENT_TOKEN`으로 권한 제시
- dashboard 원문 보기: 설정 패널에서 viewer token 입력
- token 출력: 발급 시 한 번만 표시

```bash
# 다른 shell에서, bus serve가 실행 중일 때
AGENT_TOKEN=$(agentbus auth grant --agent-name reviewer --ttl-seconds 604800)
VIEWER_TOKEN=$(agentbus auth grant --viewer operator --ttl-seconds 86400)
MSG_ID=$(agentbus message send --from operator --to reviewer --kind request \
  --subject "NDA review" --body "Review local NDA data" \
  --sensitivity restricted)
AGENTBUS_AGENT_TOKEN="$AGENT_TOKEN" agentbus agent inbox --name reviewer
agentbus bus security-check
```

### Security rules

agent-bus는 로컬 신뢰 경계 안에서 capsule API, 암호화 저장, token 권한, redacted view를 함께 씁니다.

#### 저장과 경계

- `.agent-bus/channel.json`에는 공개 channel metadata를 둡니다.
- `.agent-bus/store/capsule.sqlite`에는 본문 성격의 필드를 AEAD 암호화 payload로 저장합니다.
- raw key는 프로젝트 밖 사용자 config에 둡니다.
- 대시보드 write API는 local origin의 JSON POST 요청을 처리합니다.

#### 권한

- `agentbus auth grant --agent-id <id>` 또는 `agentbus auth grant --agent-name <name>`은 agent token을 발급합니다.
- token은 `AGENTBUS_AGENT_TOKEN`으로 전달합니다.
- 같은 id에 다시 grant하면 token이 교체됩니다.
- `agentbus auth grant --viewer <name> --ttl-seconds <seconds>`는 dashboard viewer token을 발급합니다.
- viewer token이 교체되거나 만료되면 대시보드 세션의 원문 보기도 해제됩니다.

#### 외부 전송

- `restricted` source는 외부 전송을 차단합니다.
- `internal` source는 redacted view만 전송합니다.
- `packet send --protocol a2a`는 bearer token과 인증 정보 성격의 custom header에 `https://` endpoint를 사용합니다.
- `--allow-insecure`는 로컬/테스트용 재정의 옵션입니다.
- HTTP handler(A2A profile 포함)와 OpenAI-compatible handler는 `restricted` event를 redacted notice로 처리하고 실행을 멈춥니다.
- Local CLI teammate는 target agent token이 맞을 때만 원문 cycle 입력을 받습니다.

#### 점검

- NDA 또는 restricted data가 있는 bus는 `agentbus bus security-check`로 원문 잔류, 권한, 파일 권한, secret pattern을 점검합니다.
- 같은 OS 사용자 안에서 memory/process 접근까지 격리해야 하는 NDA 운용은 별도 OS 사용자, sandbox, container, key 미마운트 같은 실행 격리를 함께 둡니다.

## Bridge

Event bridge는 bus event를 watcher나 외부 연결로 넘깁니다.

### Watch events

```bash
agentbus bridge watch --types message.created,ticket.created \
  --target reviewer \
  --position-file .agent-bus/bridge/reviewer.position
```

### Use a profile

Bridge profile은 bus event를 외부 handler로 넘기는 JSON 설정입니다.

- `monitor`: event 관찰과 position 갱신
- `http`: webhook, A2A outbound 호출
- `openai-compatible`: 외부 model API 호출
- active profile은 `.agent-bus/bridge/*.json`에 둡니다.
- `bus init`은 `.agent-bus/bridge/profile.template.json`을 만듭니다.
- `*.template.json`은 복사용 template이며 active profile 목록에는 나오지 않습니다.
- 패키지 bridge profile resource는 local profile로 복사해 수정합니다.
- 대시보드의 Gateway는 `bus serve`가 현재 열어 둔 inbound endpoint 상태를 표시합니다.

```bash
cp .agent-bus/bridge/profile.template.json .agent-bus/bridge/reviewer.json
$EDITOR .agent-bus/bridge/reviewer.json

agentbus bridge check --profile .agent-bus/bridge/reviewer.json
agentbus bridge run --profile .agent-bus/bridge/reviewer.json
```

```bash
cp "$(agentbus resource path bridge/claude-inbox.json)" .agent-bus/bridge/claude-inbox.json
```

## Teammate runners

Runner profile은 어떤 local CLI를 어떤 agent 이름으로 깨울지 정합니다. profile 파일은 `.agent-bus/bridge/<profile>.json`에 둡니다.

### Codex CLI teammate

```bash
cp "$(agentbus resource path bridge/codex-runner-inbox.json)" .agent-bus/bridge/codex-runner-inbox.json
agentbus teammate run --profile codex-runner-inbox --once --dry-run
agentbus teammate run --profile codex-runner-inbox
```

### Claude CLI teammate

```bash
cp "$(agentbus resource path bridge/claude-runner-inbox.json)" .agent-bus/bridge/claude-runner-inbox.json
agentbus teammate run --profile claude-runner-inbox --once --dry-run
agentbus teammate run --profile claude-runner-inbox
```

### Gemini CLI teammate

```bash
cp "$(agentbus resource path bridge/gemini-runner-inbox.json)" .agent-bus/bridge/gemini-runner-inbox.json
agentbus teammate run --profile gemini-runner-inbox --once --dry-run
agentbus teammate run --profile gemini-runner-inbox
```

Profile에는 다음 값을 둡니다.

- target agent
- provider 실행 옵션
- 감시 주기
- timeout 정책
- profile 소유 runner의 위치 기록

## Commands

자주 쓰는 묶음부터 보고, 세부 옵션은 각 명령의 `--help`에서 확인합니다.

### bus

| 명령 | 용도 |
| --- | --- |
| `bus init` | secure capsule channel 생성 |
| `bus serve` | localhost 대시보드 실행 |
| `bus status` | bus 상태와 정지 요청 확인 |
| `bus stop` | 협력적 정지 요청 기록 |
| `bus clear` | 현재 세션 기록 정리 |
| `bus rotate` | 메시지 로그 보관 |
| `bus archive list/show/restore` | capsule archive 조회와 복구 |
| `bus security-check` | 로컬 보호장치와 민감 기록 점검 |
| `bus supervise` | 에이전트 heartbeat와 시간 제한 감독 |

### agent

| 명령 | 용도 |
| --- | --- |
| `agent create` | 표시명으로 내부 agent id 생성 |
| `agent list` | 에이전트 상태 목록 출력 |
| `agent set` | 에이전트 heartbeat와 상태 갱신 |
| `agent delete` | 에이전트 상태 삭제 |
| `agent inbox` | 에이전트 수신함 읽기 |
| `agent ack` | 처리한 메시지 확인 표시 |
| `agent watch` | 미확인 request 감시 |

### teammate

| 명령 | 용도 |
| --- | --- |
| `teammate run` | 로컬 CLI teammate loop 실행 |

### context

| 명령 | 용도 |
| --- | --- |
| `context show` | 현재 Key Context 출력 |
| `context set --stdin/--file/--body` | Key Context 저장 |

### auth

| 명령 | 용도 |
| --- | --- |
| `auth init` | capsule auth 상태 확인/준비 |
| `auth grant --agent-id/--agent-name/--viewer [--ttl-seconds <seconds>]` | agent 또는 dashboard viewer token 발급 |
| `auth demo` | demo viewer token과 demo 전용 restricted 샘플 생성 |
| `auth revoke --agent-id/--agent-name/--viewer` | agent 또는 dashboard viewer token 폐기 |
| `auth list` | 원문 열람 권한 목록 출력 |

### message

| 명령 | 용도 |
| --- | --- |
| `message send` | 메시지 전송 |
| `message delete` | 메시지 삭제 이벤트 기록 |

### task

| 명령 | 용도 |
| --- | --- |
| `task new` | 작업 생성 |
| `task state` | 작업 상태 갱신 |
| `task list` | 작업 목록 출력 |
| `task delete` | 작업 삭제 이벤트 기록 |

### ticket

| 명령 | 용도 |
| --- | --- |
| `ticket new` | 후보 작업 등록 |
| `ticket list` | 티켓 목록 출력 |
| `ticket accept` | 티켓을 작업과 request 메시지로 승격 |
| `ticket reject` | 티켓 반려 |

### skill

| 명령 | 용도 |
| --- | --- |
| `skill new` | 로컬 스킬 초안 생성 |
| `skill list` | 로컬 스킬 목록 출력 |
| `skill show` | 로컬 `SKILL.md` 출력 |
| `skill state` | 로컬 스킬 상태 변경 |
| `skill review` | 처리할 skill 근거와 주의 항목 요약 |
| `skill evidence` | skill 사용 근거 기록 |

### bridge

| 명령 | 용도 |
| --- | --- |
| `bridge events` | bus event 읽기 |
| `bridge watch` | 새 bus event 감시 |
| `bridge run` | bridge profile 실행 |
| `bridge check` | bridge profile 검사 |
| `bridge status` | bridge 처리 위치와 실패 요약 출력 |

### packet

| 명령 | 용도 |
| --- | --- |
| `packet data --protocol aas` | AAS-compatible data packet 생성 또는 검사 |
| `packet transport --protocol a2a --artifact card` | A2A Agent Card 생성 또는 검사 |
| `packet transport --protocol a2a --artifact message` | A2A SendMessage request 생성 또는 검사 |
| `packet send --protocol a2a` | A2A request 전송 |
| `packet receive --protocol a2a` | A2A request를 bus message로 반영 |

### guide / resource

| 명령 | 용도 |
| --- | --- |
| `guide workflow` | 협업 workflow와 종료 보고서 서식 출력 |
| `guide loop` | loop 시작 절차와 종료 보고 안내 출력 |
| `resource list` | package resource 목록 출력 |
| `resource path` | package resource 경로 출력 |

## Configuration

설정값은 명령 인자, 환경변수, 현재 작업 디렉터리 기본값 순서로 적용됩니다.

- 1순위: CLI 인자
- 2순위: `AGENTBUS_*` 환경변수
- 3순위: 현재 작업 디렉터리 기본값

| 환경변수 | 용도 |
| --- | --- |
| `AGENTBUS_BUS_DIR` | channel 디렉터리 (`--bus-dir`) |
| `AGENTBUS_A2A_CARDS_DIR` | A2A 테스트 카드 디렉터리 (`--cards-dir`) |
| `AGENTBUS_ROOT` | 파일 색인 루트 (`bus serve --root`) |
| `AGENTBUS_ENDPOINT` | daemon API endpoint override |
| `AGENTBUS_PORT` | 대시보드 포트 (`bus serve --port`) |
| `AGENTBUS_MAX_BYTES` | 메시지 로그 자동 회전 임계값, 기본 5 MB, `0`이면 비활성 |
| `AGENTBUS_ARCHIVE_KEEP` | 유지할 archive 개수, 기본 `0`은 전체 유지 |
| `AGENTBUS_AGENT_TOKEN` | restricted 원문 열람 권한 token |

## App prompts

### Codex app

```bash
cd ~/my-project
agentbus bus init
agentbus guide workflow > /tmp/agentbus-workflow.md
```

Codex app thread에는 아래 prompt를 넣습니다.

```text
이 thread에서 agent-bus를 사용하세요.
당신은 codex라는 이름으로 활동할 에이전트입니다.
Bus 디렉터리: /absolute/path/to/my-project/.agent-bus

`agentbus guide workflow` 또는 설치된 `agent-bus-workflow` skill에서 workflow를 읽으세요.
다음 명령으로 시작하세요.
agentbus bus status --stop-exit-code
agentbus agent set --name codex --state running --note "joined"
agentbus agent inbox --name codex

request 메시지를 처리하고, `agentbus message send`로 보고한 뒤 task id가 있으면 task state를 갱신하세요. `teammate run` 밖에서 직접 inbox를 처리했다면 처리한 메시지를 ack하세요.
lead 역할이면 loop를 닫기 직전 inbox를 다시 확인하고, `agentbus guide workflow`의 구조화된 종료 보고서를 마지막 report로 보낸 뒤 task state는 completed, status는 done으로 설정하세요.
```

### Claude Code

```bash
cd ~/my-project
agentbus bus init
agentbus guide loop > /tmp/agentbus-loop.md
```

Claude 세션에는 아래 prompt를 넣습니다.

```text
이 세션에서 agent-bus를 사용하세요.
당신은 claude라는 이름으로 활동할 에이전트입니다.
Bus 디렉터리: /absolute/path/to/my-project/.agent-bus

`/agent-bus-loop` skill이 설치되어 있으면 그 skill로 시작하세요. 텍스트를 직접 읽는 환경에서는 `agentbus guide loop`의 loop text와 `agentbus guide workflow`의 전체 workflow를 확인하세요.
다음 명령으로 시작하세요.
agentbus bus status --stop-exit-code
agentbus agent set --name claude --state running --note "joined"
agentbus agent inbox --name claude

request 메시지를 처리하고, `agentbus message send`로 보고한 뒤 task id가 있으면 task state를 갱신하세요. `teammate run` 밖에서 직접 inbox를 처리했다면 처리한 메시지를 ack하세요.
lead 역할이면 loop를 닫기 직전 inbox를 다시 확인하고, `agentbus guide workflow`의 구조화된 종료 보고서를 마지막 report로 보낸 뒤 task state는 completed, status는 done으로 설정하세요.
```

## Teammate I/O

- Input: Key Context와 trigger metadata가 포함된 `teammate-cycle.v1` JSON을 stdin으로 전달
- Output: stdout은 operator log로 남고, bus report는 agent가 `agentbus message send`로 기록
- Success: agent가 report, task state, status를 남김
- Continue: 이어갈 일이 있으면 자기 자신에게 제한된 후속 request를 남기거나 lead/user에게 다음 범위를 요청
- Failure: provider 실패나 bus 기록 없는 cycle은 runner error로 남고, task가 있으면 failed로 기록
- Timeout: `timeoutSeconds`는 오래 걸리는 cycle을 상태로 드러내는 기준이며 provider process는 계속 기다림
- Runner entrypoint: `teammate run`이 provider별 고정 진입점(`codex exec`, `claude -p`, `gemini -p`)을 내부에서 사용

## Misc

### Python API

Python API는 코드에서 bus 기록, assessment packet, A2A request를 직접 다룰 때 사용합니다.

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

- Bridge profile resources: `agentbus/resources/bridge`
- Demo dashboard bus: `agentbus/resources/demo-bus`
- 수식 렌더링: `vendor/katex`
- License: MIT

### Release check

```bash
agentbus/resources/smoke/publish-smoke.sh
uv build --sdist --wheel --out-dir /tmp/agentbus-dist
python -m venv /tmp/agentbus-install
/tmp/agentbus-install/bin/python -m pip install /tmp/agentbus-dist/*.whl
/tmp/agentbus-install/bin/agentbus --help
python -m twine check /tmp/agentbus-dist/*   # optional
```

### References

- A2A: [Agent2Agent Protocol specification](https://a2a-protocol.org/latest/specification/)
- A2A: [a2aproject/A2A repository](https://github.com/a2aproject/A2A)
- AAS: [IDTA AAS specifications](https://industrialdigitaltwin.io/aas-specifications/index/home/index.html)
- AAS: [Part 1: Metamodel](https://industrialdigitaltwin.io/aas-specifications/IDTA-01001/v3.1.2/index.html)
- AAS: [Part 2: Application Programming Interfaces](https://industrialdigitaltwin.io/aas-specifications/IDTA-01002/v3.1.2/index.html)
