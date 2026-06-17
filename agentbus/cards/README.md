# 에이전트 카드

에이전트 카드는 로컬 대시보드가 읽는 선택 메타데이터다. 프로젝트 카드는 기본적으로 `./agent-cards/*.json`에 둔다.

| 필드 | 의미 |
| --- | --- |
| `idShort` | 에이전트 키. 기본값은 파일명이다. |
| `name` | 표시 이름 |
| `description` | 역할 한 줄 |
| `capabilities` | 로컬 실행 특성 |
| `skills` | 맡을 수 있는 작업 |
| `submodelElements` | 프로젝트별 속성 |

패키지 예시 `example-agent.json`을 복사해 `my-agent.json`, `reviewer.json`처럼 이름을 나눈다. 대시보드는 `--cards-dir`의 카드를 수신처 후보로 읽는다.

`agentbus a2a-card --agent <id>`는 이 로컬 카드를 A2A Agent Card JSON으로 변환한다. 원본 카드는 로컬 대시보드용 형식을 유지한다.
