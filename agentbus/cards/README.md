# A2A 테스트 카드

A2A 테스트 카드는 local agent 정보를 A2A Agent Card로 변환할 때 쓰는 입력 파일입니다. 프로젝트 카드는 기본적으로 `./agent-cards/*.json`에 둡니다.

| 필드 | 의미 |
| --- | --- |
| `idShort` | agent key. 기본값은 파일명 |
| `name` | 표시 이름 |
| `description` | 역할 한 줄 |
| `capabilities` | 로컬 실행 특성 |
| `skills` | 맡을 수 있는 작업 |
| `submodelElements` | 프로젝트별 속성 |

패키지 예시 `example-agent.json`을 복사해 `my-agent.json`, `reviewer.json`처럼 이름을 나눕니다. `--cards-dir`는 이 테스트 카드 디렉터리를 가리킵니다.

`agentbus packet transport --protocol a2a --artifact card --agent <id>`는 이 파일을 A2A Agent Card JSON으로 변환합니다.
