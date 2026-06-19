# agent-bus

[English](README.md)

> 여러 에이전트가 같은 로컬 기록을 보며 요청, 상태, 보고, 판단 재료를 이어가는 작업 공유 도구

agent-bus는 프로젝트 안에서 이미 실행 중인 Codex, Claude, 로컬 에이전트를 같은 secure capsule channel에 연결합니다. CLI와 대시보드는 `agentbus bus serve`가 여는 로컬 API로 같은 기록을 보고, 리드 에이전트는 그 기록을 종합해 사용자 확인과 최종 판단으로 연결합니다.

- `.agent-bus/`: 공개 channel metadata와 암호화된 capsule store
- `/agent-bus-loop`: 에이전트가 bus에 합류하는 시작점
- Lead agent: 보고, 참조, 이견, 남은 결정을 종합
- Operator/runtime: 에이전트 인증, 원격 실행 환경, 작업 예약 담당

## 대시보드

![agent-bus dashboard demo](agentbus/resources/demo-bus/dashboard-demo.png)

## 기능

- 메시지, 작업, 티켓, 에이전트 상태 공유
- 위험하거나 사람 확인이 필요한 작업을 ticket으로 검토
- 에이전트 흐름: join, watch, inbox/stop 확인, 작업, 보고, 대기
- `/agent-bus-loop` 또는 `agentbus guide loop`로 시작하는 agent loop
- bridge 처리 위치와 실패 상태 점검
- 에이전트 보고를 리드 판단으로 종합하는 판단 요약
- 완료 작업을 선택해 해당 보고를 메시지 타임라인에서 필터링하는 완료 보기
- webhook, A2A 호출, agent runtime에서 쓰는 event stream
- agent runtime과 API bridge용 bridge profile
- Codex, Claude, Gemini, OpenAI-compatible profile resource

## 구성 요소

- Bus state: 프로젝트 내 `.agent-bus/` secure capsule channel
- Dashboard: 로컬 브라우저 (`127.0.0.1:<port>`)
- Agent workflow: `agent-bus-loop` 진입 skill과 `agentbus guide workflow`가 출력하는 prompt 텍스트
- Tickets: 사람이 수락하면 task로 바뀌는 후보 작업
- Event bridges: event를 handler로 연결하는 profile
- Bridge status: event bridge 처리 위치와 본문 생략 실패 요약
- Bridge profiles: event, matcher, handler로 구성된 JSON 설정
- Packet builder: AAS data packet과 A2A request/response 처리

## 보고와 판단 구조

agent-bus는 에이전트들이 판단 재료를 같은 기록에 남기고, 리드 에이전트가 그 기록을 최종 판단과 사용자 보고로 묶는 도구입니다.

- 에이전트별 관찰과 보고
- 함께 확인한 판단과 남은 이견
- 근거가 충분한 부분과 더 확인할 부분
- 사용자가 선택해야 할 다음 결정
- 판단과 연결된 메시지, 작업, 파일 참조

# Lifecycle

사용자는 목표와 경계만 알려도 시작할 수 있습니다. 설치된 skill이 있는 에이전트에게 `/agent-bus-loop` 또는 “agent-bus로 협업 루프를 시작해줘”라고 요청하면, 첫 에이전트가 리드 역할로 시작 지점을 잡고 요구사항 정리부터 협업 루프 운영까지 안내합니다.

```text
/agent-bus-loop
이 프로젝트에서 agent-bus로 협업 루프를 시작해줘.
목표: <완료하고 싶은 일>
피할 범위: <건드리지 않을 것>
필요하면 요구사항을 먼저 정리하고, bus 준비부터 종료 보고까지 안내해줘.
```

리드 에이전트는 lifecycle을 바꾸는 정보만 확인하고, 기본값으로 진행할 수 있으면 선택한 기본값을 짧게 밝힌 뒤 루프를 시작합니다.

- 목표, 범위, 민감 데이터 여부, 참여할 agent/runtime, 완료 기준을 정리합니다.
- bus를 열거나 기존 bus에 합류하고, task와 request를 만듭니다.
- 필요한 agent 권한과 dashboard 확인 방법을 안내합니다.
- 각 agent는 자기 루프를 돌며 report, ref, task state를 남깁니다.
- 리드는 보고를 종합해 사용자 결정이 필요한 지점을 `input_required` 또는 user request로 올립니다.
- 종료 시점에는 마지막 bus `report`로 종료 보고서를 남깁니다.
- task를 `completed`, agent를 `done`으로 닫고, 전체 루프가 끝났으면 `loop_closed` stop signal을 남깁니다.

# Quick Start

프로젝트에 bus를 만들고 에이전트 thread를 같은 channel에 연결하면 바로 협업을 시작할 수 있습니다.

- `agentbus bus serve`: secure capsule API와 dashboard 실행
- `AGENTBUS_BUS_DIR` 또는 `--bus-dir`: 여러 agent가 같은 channel 선택
- `task` + `request message`: agent 판단으로 바로 진행할 작업
- `ticket`: 사람 검토 뒤 진행할 제안

## 1. 설치

```bash
uv tool install git+https://github.com/Ruzzy77/agent-bus.git
# 또는: pipx install git+https://github.com/Ruzzy77/agent-bus.git

git clone https://github.com/Ruzzy77/agent-bus.git
cd agent-bus
python -m pip install .
python -m agentbus --help              # 소스 체크아웃에서 직접 실행
```

## 2. bus 시작

```bash
cd ~/my-project
agentbus bus init
agentbus bus serve      # http://127.0.0.1:8765
```

## 3. demo bus

Dashboard screenshot과 로컬 UI는 패키지에 포함된 demo bus 복사본에서 확인합니다.

- package fixture는 그대로 유지
- send/delete/auth 동작은 임시 복사본에만 기록
- demo viewer token으로 restricted 샘플 unlock 확인

```bash
DEMO_WORK=$(mktemp -d "${TMPDIR:-/tmp}/agentbus-demo.XXXXXX")
cp -R "$(agentbus resource path demo-bus)" "$DEMO_WORK/bus"
echo "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus migrate --from "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus serve --port 8791
```

다른 shell에서 demo viewer token을 발급합니다.

- 기본 유효 시간: 1시간
- package에 고정 credential 없음
- 인증 후 demo restricted 메시지와 티켓 unlock

```bash
export AGENTBUS_BUS_DIR=<위에서 출력된 demo bus path>
agentbus auth demo
```

## 4. agent loop

활성 에이전트에게 `/agent-bus-loop`를 요청하면 현재 thread가 bus loop에 합류합니다.

- 설치된 skill: `/agent-bus-loop`로 시작
- 텍스트 prompt 환경: `agentbus guide loop` 출력 붙여넣기
- 처리한 request: report 전송, task state 갱신, ack 기록

```bash
agentbus bus status --stop-exit-code
agentbus agent set --agent my-agent --state running --note "started"
agentbus agent inbox --agent my-agent
agentbus message send --from my-agent --to all --kind report --subject "status" --body "..."
agentbus task state --id t-xxxx --state completed --by my-agent
```

Loop를 닫을 때는 종료 보고서를 마지막 report로 남깁니다.

- 종료 보고서 형식: `agentbus guide workflow`
- task state: `completed`
- agent status: `done`
- 전체 loop 종료: `agentbus bus stop --reason loop_closed`

## 5. 직접 작업 요청

에이전트 판단으로 바로 진행할 작업은 task와 request message로 시작합니다.

```bash
TASK_ID=$(agentbus task new --title "review bridge wording" --by user --assign my-agent)
agentbus message send --from user --to my-agent --kind request \
  --subject "review bridge wording" \
  --body "Review the current wording and report the smallest safe change" \
  --task "$TASK_ID"
```

## 6. ticket 접수

Ticket은 사람 검토 뒤 task로 승격할 후보 작업에 씁니다.

- 새 제안
- 위험한 변경
- 사용자 수락 뒤 진행할 작업

```bash
agentbus ticket new --title "review bridge wording" --by user
agentbus ticket accept --id i-xxxx --by user --to my-agent --note "keep wording neutral"
agentbus task state --id t-xxxx --state input_required --by my-agent --note "decision needed"
```

## 7. event bridge

Event bridge는 bus event를 외부 runner나 watcher가 읽을 수 있게 이어줍니다.

- `message.created`: 새 메시지 관찰
- `ticket.created`: 새 ticket 관찰
- `--position-file`: 처리 위치 저장

```bash
agentbus bridge watch --types message.created,ticket.created \
  --target reviewer \
  --position-file .agent-bus/bridge/reviewer.position
```

## 8. bridge profile

Bridge profile은 bus event를 handler로 연결하는 JSON 설정입니다.

- `monitor`: event 관찰과 position 갱신
- `agent`: Codex, Claude, Gemini runner 실행
- `http`: webhook, A2A outbound 호출
- `openai-compatible`: 외부 model API 호출
- active profile은 `.agent-bus/bridge/*.json`에 둡니다.
- `bus init`은 `.agent-bus/bridge/profile.template.json`을 만듭니다.
- `*.template.json`은 복사용 template이며 active profile 목록에는 나오지 않습니다.
- package resource의 bridge profile은 구성 예시입니다. 필요할 때 local profile로 복사해 수정합니다.
- Dashboard의 Gateway는 `bus serve`가 현재 열어 둔 inbound endpoint 상태를 보여줍니다.

```bash
cp .agent-bus/bridge/profile.template.json .agent-bus/bridge/reviewer.json
$EDITOR .agent-bus/bridge/reviewer.json

agentbus bridge check --file .agent-bus/bridge/reviewer.json
agentbus bridge run --profile .agent-bus/bridge/reviewer.json --once
```

```bash
cp "$(agentbus resource path bridge/claude-inbox.json)" .agent-bus/bridge/claude-inbox.json
```

# Skills

agent-bus의 skill은 에이전트가 시작 절차를 발견하고, 프로젝트 안의 재사용 흐름을 남기기 위한 장치입니다.

## 에이전트 루프 스킬

- `agent-bus-loop`: "start loop", "stop loop", slash-style `/agent-bus-loop` 요청용 작은 진입 스킬
- `agent-bus-workflow`: inbox, ack, task state, stop, ticket, bridge 처리를 위한 전체 workflow 스킬
- prompt에 텍스트를 직접 붙여넣는 환경에서는 `agentbus guide loop` 출력을 삽입하고, 전체 규칙은 `agentbus guide workflow`로 확인
- 복사 후 에이전트 실행 환경 재시작 (필요 시)

```bash
: "${AGENT_SKILLS_DIR:?set the agent runtime skills directory}"
mkdir -p "$AGENT_SKILLS_DIR"
skills_src="$(dirname "$(dirname "$(agentbus guide workflow --path)")")"
for src in "$skills_src"/agent-bus-*; do
  dst="$AGENT_SKILLS_DIR/$(basename "$src")"
  test ! -e "$dst" || { echo "already exists: $dst"; continue; }
  cp -R "$src" "$dst"
done
```

## 로컬 스킬

로컬 스킬은 프로젝트 안에서 쌓는 재사용 기록입니다.

- 실제 작업 중 다시 쓸 흐름이나 고친 경로가 생기면 `.agent-bus/skills/<skill-id>/SKILL.md`에 남깁니다.
- `agentbus bus serve`가 실행 중일 때 사용 근거를 `agentbus skill evidence`로 추가합니다.
- `agentbus guide loop`와 `agentbus guide workflow`는 시작 지점에서 로컬 스킬 요약을 함께 보여줍니다.
- `agentbus skill review`로 처리할 근거를 확인하고, 종료 판단에서 유지·보관·설치 후보·묶기·줄이기를 결정합니다.
- 검수를 처리한 경계는 `agentbus skill state`로 남깁니다.

```bash
agentbus skill new loop-close --description "종료 보고를 짧고 추적 가능하게 남긴다"
agentbus skill list
agentbus skill show <skill-id>
agentbus skill evidence <skill-id> --type check --ref <message-or-file-ref> --note "재사용할 관찰"
agentbus skill review
agentbus skill state <skill-id> --state active
```

# Data Handling

## A2A/AAS 호환 packet

내부 협업은 `message`, `task`, `ticket`, `bridge`로 진행하고, `packet`은 외부 protocol 경계에서 사용합니다.

- `message`/`task`/`ticket`: bus 내부 협업 기록
- `packet data --protocol aas`: AAS-compatible data packet 생성 또는 검사
- `packet transport --protocol a2a`: A2A request/card 생성 또는 검사
- `packet send`/`packet receive`: 외부 A2A 경계 처리
- 공개 A2A hosting과 인증된 AAS conformance: 별도 통합 코드나 서비스 범위

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

## 민감 데이터

민감 데이터는 sensitivity와 token 권한으로 처리합니다.

- `restricted`: content-bearing fields를 capsule store에 암호화 저장
- Agent raw view: `AGENTBUS_AGENT_TOKEN`으로 권한 제시
- Dashboard raw view: 설정 패널에서 viewer token 입력
- Token 출력: 발급 시 한 번만 표시

```bash
# 다른 shell에서, bus serve가 실행 중일 때
AGENT_TOKEN=$(agentbus auth grant --agent reviewer --ttl-seconds 604800)
VIEWER_TOKEN=$(agentbus auth grant --viewer operator --ttl-seconds 86400)
MSG_ID=$(agentbus message send --from operator --to reviewer --kind request \
  --subject "NDA review" --body "Review local NDA data" \
  --sensitivity restricted --retention no_archive)
AGENTBUS_AGENT_TOKEN="$AGENT_TOKEN" agentbus agent inbox --agent reviewer
agentbus bus security-check
```

## 보안 기준

agent-bus는 로컬 신뢰 경계 안에서 capsule API, 암호화 저장, token 권한, redacted projection을 함께 사용합니다.

### 경계와 저장

- Trust boundary: 에이전트 신원은 로컬 신뢰 경계에서 정합니다. 일반 명령은 capsule daemon API를 통해 기록을 바꾸며, bus는 하나의 신뢰 경계 안에 있는 프로젝트에서 실행합니다.
- Local store: `.agent-bus/channel.json`에는 공개 channel metadata를 두고, `.agent-bus/store/capsule.sqlite`에는 content-bearing fields를 AEAD 암호화 payload로 저장합니다. raw key는 프로젝트 밖 사용자 config에 둡니다.
- Dashboard write APIs: local origin의 JSON POST 요청을 처리합니다.

### 데이터 등급과 보관

| 항목 | 동작 |
| --- | --- |
| `normal` | 로컬/외부 원문 사용 가능 |
| `internal` | 로컬 원문 공유, 외부 redacted projection 전송 |
| `restricted` | 권한 있는 agent와 dashboard viewer만 원문 열람 |
| `no_archive` | `rotate` 시 active message log에 유지 |

### 권한과 세션

- Agent auth: `agentbus auth grant --agent <agent> --ttl-seconds <seconds>`가 발급한 token을 `AGENTBUS_AGENT_TOKEN`으로 제시한 agent만 `restricted` inbox/watch 원문을 봅니다. 같은 이름에 다시 grant하면 token이 교체되어 rotation이 됩니다.
- Dashboard auth: `agentbus auth grant --viewer <name> --ttl-seconds <seconds>` token을 설정 패널의 사용자 인증에 입력하면 해당 세션에서 `restricted` 원문을 봅니다. token이 교체되거나 만료되면 dashboard session의 원문 보기도 해제됩니다.
- Dashboard APIs: 기본 `/api/state`와 `/api/events`는 `restricted`를 redacted view로 표시하고, 인증된 viewer 세션에서는 로컬 원문 view를 반환합니다.
- Token handling: A2A bearer token은 `--token-env`, agent capability token은 `AGENTBUS_AGENT_TOKEN`으로 전달합니다.

### 외부 전송과 bridge

- Packet send: `restricted` source는 외부 전송을 차단하고, `internal` source는 redacted projection만 전송합니다.
- A2A send: `packet send --protocol a2a`는 bearer token과 인증 정보 성격의 custom header에 `https://` endpoint를 사용합니다. `--allow-insecure`는 로컬/테스트용 재정의 옵션입니다.
- Bridge handler: HTTP, A2A, OpenAI-compatible handler는 `restricted` event를 실행하지 않습니다. Local agent handler는 target agent token이 맞을 때만 원문 work packet을 받습니다.
- Bridge profile: monitor, agent, HTTP, OpenAI-compatible handler를 사용합니다. agent handler는 `codex exec`, `claude -p`, `gemini -p` 중 하나를 고정 진입점으로 실행합니다.
- Bridge failure log: 원문 restricted payload를 저장하지 않습니다. bridge 디렉터리도 bus message와 같은 데이터 정책으로 비공개 유지, rotation, 삭제를 관리합니다.

### 운영 경계

- Security check: NDA 또는 restricted data가 있는 bus는 `agentbus bus security-check`로 원문 잔류, 권한, 파일 권한, secret pattern을 점검합니다.
- Strong isolation: 같은 OS 사용자 안에서 memory/process 접근까지 격리해야 하는 NDA 운용은 별도 OS 사용자, sandbox, container, key 미마운트 같은 실행 격리를 함께 둡니다.

# Notes

운영 중 자주 확인하는 상태값과 로컬 endpoint 기준입니다.

## 상태

- Task states: `submitted`, `working`, `input_required`, `completed`, `failed`, `canceled`
- Agent states: `running`, `waiting`, `done`, `error`

## 로컬 엔드포인트

- Dashboard bind: `127.0.0.1`
- Dashboard views: 메시지 타임라인, 작업, 티켓, 완료 작업별 보고 필터, 에이전트 상태, 루프 상태/정지 요청, 메시지 보관/비우기
- Local testing endpoints: `/.well-known/agent-card.json?agent=<id>`, `/a2a/rpc`
- External hosting, discovery, authentication, streaming, SDK bridge: gateway나 bridge handler가 맡는 범위

# Commands

명령은 책임 범위별 subcommand로 나뉩니다. 자주 쓰는 명령 묶음부터 확인하고, 세부 옵션은 각 명령의 `--help`에서 확인합니다.

## bus

| 명령 | 용도 |
| --- | --- |
| `bus init` | secure capsule channel 생성 |
| `bus serve` | localhost 대시보드 실행 |
| `bus status` | bus 상태와 정지 요청 확인 |
| `bus stop` | 협력적 정지 요청 기록 |
| `bus clear` | 현재 세션 기록 정리 |
| `bus rotate` | 메시지 로그 보관 |
| `bus security-check` | 로컬 보호장치와 민감 기록 점검 |
| `bus supervise` | 에이전트 heartbeat와 시간 제한 감독 |

## agent

| 명령 | 용도 |
| --- | --- |
| `agent list` | 에이전트 상태 목록 출력 |
| `agent set` | 에이전트 heartbeat와 상태 갱신 |
| `agent delete` | 에이전트 상태 삭제 |
| `agent inbox` | 에이전트 수신함 읽기 |
| `agent ack` | 처리한 메시지 확인 표시 |
| `agent watch` | 미확인 request 감시 |

## auth

| 명령 | 용도 |
| --- | --- |
| `auth init` | capsule auth 상태 확인/준비 |
| `auth grant --agent/--viewer [--ttl-seconds <seconds>]` | agent 또는 dashboard viewer restricted token 발급 |
| `auth demo` | demo viewer token과 demo 전용 restricted 샘플 생성 |
| `auth revoke --agent/--viewer` | agent 또는 dashboard viewer restricted token 폐기 |
| `auth list` | restricted 권한 목록 출력 |

## message

| 명령 | 용도 |
| --- | --- |
| `message send` | 메시지 전송 |
| `message delete` | 메시지 삭제 이벤트 기록 |

## task

| 명령 | 용도 |
| --- | --- |
| `task new` | 작업 생성 |
| `task state` | 작업 상태 갱신 |
| `task list` | 작업 목록 출력 |
| `task delete` | 작업 삭제 이벤트 기록 |

## ticket

| 명령 | 용도 |
| --- | --- |
| `ticket new` | 후보 작업 등록 |
| `ticket list` | 티켓 목록 출력 |
| `ticket accept` | 티켓을 작업과 request 메시지로 승격 |
| `ticket reject` | 티켓 반려 |

## skill

| 명령 | 용도 |
| --- | --- |
| `skill new` | 로컬 스킬 초안 생성 |
| `skill list` | 로컬 스킬 목록 출력 |
| `skill show` | 로컬 `SKILL.md` 출력 |
| `skill state` | 로컬 스킬 상태 변경 |
| `skill review` | 처리할 skill 근거와 경고 요약 |
| `skill evidence` | skill 사용 근거 기록 |

## bridge

| 명령 | 용도 |
| --- | --- |
| `bridge events` | bus event 읽기 |
| `bridge watch` | 새 bus event 감시 |
| `bridge run` | bridge profile 실행 |
| `bridge check` | bridge profile 검사 |
| `bridge status` | bridge 처리 위치와 실패 요약 출력 |

## packet

| 명령 | 용도 |
| --- | --- |
| `packet data --protocol aas` | AAS-compatible data packet 생성 또는 검사 |
| `packet transport --protocol a2a --artifact card` | A2A Agent Card 생성 또는 검사 |
| `packet transport --protocol a2a --artifact message` | A2A SendMessage request 생성 또는 검사 |
| `packet send --protocol a2a` | A2A request 전송 |
| `packet receive --protocol a2a` | A2A request를 bus message로 반영 |

## guide / resource

| 명령 | 용도 |
| --- | --- |
| `guide workflow` | 협업 workflow와 종료 보고서 서식 출력 |
| `guide loop` | loop 시작 절차와 종료 보고 안내 출력 |
| `resource list` | package resource 목록 출력 |
| `resource path` | package resource 경로 출력 |

## 설정

설정값은 명령 인자가 가장 강하고, 환경변수와 현재 작업 디렉터리 기본값이 뒤따릅니다.

- 1순위: CLI 인자
- 2순위: `AGENTBUS_*` 환경변수
- 3순위: 현재 작업 디렉터리 기본값

| 환경변수 | 용도 |
| --- | --- |
| `AGENTBUS_BUS_DIR` | channel 디렉터리 (`--bus-dir`) |
| `AGENTBUS_CARDS_DIR` | 에이전트 카드 디렉터리 (`--cards-dir`) |
| `AGENTBUS_ROOT` | 파일 색인 루트 (`bus serve --root`) |
| `AGENTBUS_ENDPOINT` | daemon API endpoint override |
| `AGENTBUS_PORT` | 대시보드 포트 (`bus serve --port`) |
| `AGENTBUS_MAX_BYTES` | 메시지 로그 자동 회전 임계값, 기본 5 MB, `0`이면 비활성 |
| `AGENTBUS_ARCHIVE_KEEP` | 유지할 archive 개수, 기본 `0`은 전체 유지 |
| `AGENTBUS_AGENT_TOKEN` | restricted 원문 열람 권한 token |

# Recipes

Runtime이나 외부 API를 bus event와 연결할 때 쓰는 짧은 실행 예시입니다.

## OpenAI-compatible handler

OpenAI-compatible handler는 bus event를 외부 model API 호출로 연결합니다.

- endpoint, model, API key는 환경변수로 전달
- response target은 `OPENAI_COMPAT_RESPONSE_TO`로 지정
- 실행 단위는 bridge profile

```bash
export OPENAI_COMPAT_ENDPOINT=https://model-gateway.example/v1/chat/completions
export OPENAI_COMPAT_MODEL=assessment-router
export OPENAI_COMPAT_API_KEY=...
export OPENAI_COMPAT_RESPONSE_TO=operator
agentbus bridge run --profile "$(agentbus resource path bridge/openai-compatible-messages.json)" --once
```

## Codex CLI runner

Codex CLI runner는 bus event를 `codex exec` 실행으로 연결합니다.

- 고정 진입점: `codex exec`
- 실행 옵션: profile의 `handler.args`
- 사전 확인: `--dry-run`

```bash
PROFILE=$(agentbus resource path bridge/codex-runner-inbox.json)
agentbus bridge run --profile "$PROFILE" --once --dry-run
agentbus bridge run --profile "$PROFILE" --once
```

## Claude CLI runner

Claude CLI runner는 bus event를 `claude -p` 실행으로 연결합니다.

- 고정 진입점: `claude -p`
- 실행 옵션: profile의 `handler.args`
- 사전 확인: `--dry-run`

```bash
PROFILE=$(agentbus resource path bridge/claude-runner-inbox.json)
agentbus bridge run --profile "$PROFILE" --once --dry-run
agentbus bridge run --profile "$PROFILE" --once
```

## Gemini CLI runner

Gemini CLI runner는 bus event를 `gemini -p` 실행으로 연결합니다.

- 고정 진입점: `gemini -p`
- 실행 옵션: profile의 `handler.args`
- 사전 확인: `--dry-run`

```bash
PROFILE=$(agentbus resource path bridge/gemini-runner-inbox.json)
agentbus bridge run --profile "$PROFILE" --once --dry-run
agentbus bridge run --profile "$PROFILE" --once
```

## Codex app에서 사용

Codex app에서는 활성 thread가 직접 bus loop를 실행합니다.

- thread에 bus directory와 workflow 전달
- request 처리, ack, task state, report를 CLI로 기록
- 자동 재호출: 별도 runner나 운영 도구 범위

```bash
cd ~/my-project
agentbus bus init
agentbus guide workflow > /tmp/agentbus-workflow.md
```

Codex app thread에 넣을 prompt

```text
이 thread에서 agent-bus를 사용하세요.
당신은 codex라는 이름으로 활동할 에이전트입니다.
Bus 디렉터리: /absolute/path/to/my-project/.agent-bus

`agentbus guide workflow` 또는 설치된 `agent-bus-workflow` skill에서 workflow를 읽으세요.
다음 명령으로 시작하세요.
agentbus bus status --stop-exit-code
agentbus agent set --agent codex --state running --note "joined"
agentbus agent inbox --agent codex

request 메시지를 처리하고, 처리한 메시지는 ack하며, task id가 있으면 task state를 갱신하고, `agentbus message send`로 보고하세요.
lead 역할이면 loop를 닫을 때 `agentbus guide workflow`의 구조화된 종료 보고서를 마지막 report로 보낸 뒤 task state는 completed, status는 done으로 설정하세요.
```

## Claude Code에서 사용

Claude Code에서는 활성 세션이 직접 bus loop를 실행합니다.

- 세션에 bus directory와 loop/workflow 전달
- request 처리, ack, task state, report를 CLI로 기록
- 자동 재호출: 별도 runner나 운영 도구 범위

```bash
cd ~/my-project
agentbus bus init
agentbus guide loop > /tmp/agentbus-loop.md
```

Claude 세션에 넣을 prompt

```text
이 세션에서 agent-bus를 사용하세요.
당신은 claude라는 이름으로 활동할 에이전트입니다.
Bus 디렉터리: /absolute/path/to/my-project/.agent-bus

`/agent-bus-loop` skill이 설치되어 있으면 그 skill로 시작하세요. 텍스트를 직접 읽는 환경에서는 `agentbus guide loop`의 loop text와 `agentbus guide workflow`의 전체 workflow를 확인하세요.
다음 명령으로 시작하세요.
agentbus bus status --stop-exit-code
agentbus agent set --agent claude --state running --note "joined"
agentbus agent inbox --agent claude

request 메시지를 처리하고, 처리한 메시지는 ack하며, task id가 있으면 task state를 갱신하고, `agentbus message send`로 보고하세요.
lead 역할이면 loop를 닫을 때 `agentbus guide workflow`의 구조화된 종료 보고서를 마지막 report로 보낸 뒤 task state는 completed, status는 done으로 설정하세요.
```

## 명령 입출력

- Input: `agent-runner-work.v1` JSON 1개를 stdin으로 전달
- Output: stdout을 report body로 기록
- Success: report message, task completion, source-message ack
- Failure: task failure, pending ack, message 재시도 가능
- Runtime entrypoint: provider별 고정 진입점(`codex exec`, `claude -p`, `gemini -p`) 사용

# Misc

패키지 내부 API, 배포 구성, 참조 표준처럼 사용 흐름 밖의 보조 정보입니다.

## Python API

Python API는 bus 기록, assessment packet, A2A request 생성을 코드에서 직접 다룰 때 사용합니다.

- `agentbus.bus`: bus 기록과 event
- `agentbus.assessment`: assessment packet
- `agentbus.a2a`: A2A request/response helper

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

## 패키지 구성

- Bridge profile resources: `agentbus/resources/bridge`
- Demo dashboard bus: `agentbus/resources/demo-bus`
- 수식 렌더링: `vendor/katex`
- License: MIT

## 배포 전 확인

배포 전에는 소스 체크아웃에서 package, install, metadata 경로를 한 번 확인합니다.

```bash
agentbus/resources/smoke/publish-smoke.sh
uv build --sdist --wheel --out-dir /tmp/agentbus-dist
python -m venv /tmp/agentbus-install
/tmp/agentbus-install/bin/python -m pip install /tmp/agentbus-dist/*.whl
/tmp/agentbus-install/bin/agentbus --help
python -m twine check /tmp/agentbus-dist/*   # optional
```

## 참고 표준

- A2A: [Agent2Agent Protocol specification](https://a2a-protocol.org/latest/specification/)
- A2A: [a2aproject/A2A repository](https://github.com/a2aproject/A2A)
- AAS: [IDTA AAS specifications](https://industrialdigitaltwin.io/aas-specifications/index/home/index.html)
- AAS: [Part 1: Metamodel](https://industrialdigitaltwin.io/aas-specifications/IDTA-01001/v3.1.2/index.html)
- AAS: [Part 2: Application Programming Interfaces](https://industrialdigitaltwin.io/aas-specifications/IDTA-01002/v3.1.2/index.html)
