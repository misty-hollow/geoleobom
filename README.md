# 걸어봄 (geoleobom)

위치 하나를 넣으면 생활시설까지 **실제 보행망 기준** 예상 도보시간을 보여주고, 후보를 4곳까지 담아 비교·공유하는 웹앱.
제품 범위와 기술 스택은 `docs/걸어봄_확정설계_v2.1.md`가 기준이다.

- 확정 설계: `docs/걸어봄_확정설계_v2.1.md` (동결. 단일 기준)
- 개발 운영 가이드: `docs/걸어봄_개발운영가이드_v1.md`
- 프로젝트 안내와 승인된 결정: `PROJECT.md`
- 현재 상태: `STATUS.md`
- AI 공통 작업 규칙: `AGENTS.md`

## 현재 저장소 상태

기준 문서와 운영 파일만 있다. 제품 코드는 아직 없다.

```
docs/          기준 문서 2종
PROJECT.md     안내 + 승인된 결정
AGENTS.md      AI 공통 작업 규칙
CLAUDE.md      AGENTS.md 연결
README.md      이 파일
STATUS.md      현재 상태와 다음 작업
.gitattributes 줄바꿈 규칙
.gitignore     제외 규칙
```

제품 코드 디렉터리 구조는 아직 결정하지 않았다 (`PROJECT.md` 5절).

## 확인된 개발 도구 (2026-09-10, 읽기 전용 확인)

| 도구 | 버전 | 경로 |
|---|---|---|
| Git | 2.53.0 | `C:\Program Files\Git\cmd\git.exe` |
| Node | 24.14.1 | `C:\Program Files\nodejs\node.exe` |
| npm | 11.11.0 | `C:\Program Files\nodejs\npm.ps1` |
| Python | 3.14.4 | `C:\Users\sdsdo\AppData\Local\Python\pythoncore-3.14-64\python.exe` |
| pip | 26.0.1 | `C:\Users\sdsdo\AppData\Local\Python\bin\pip.exe` |
| Docker | 미설치 | — |
| WSL | 미설치 | — |

프로젝트용 Python은 3.12로 고정할 예정이다 (`PROJECT.md` 3절). **아직 설치하지 않았다.**

## 설치

**미확인.** 아직 실행해 확인한 설치 절차가 없다.
확정된 계획은 `PROJECT.md` 3절에 있다 (Python 3.12 추가, Docker Desktop 설치).

## 실행

**미확인.** 제품 코드가 없다.

## 기본 검사

**미확인.** 타입 검사·프론트 빌드·계산 검사는 아직 구성하지 않았다.

## 배포

**미확인.** v2.1 5절과 개발 운영 가이드 7절이 절차의 기준이다. 실제로 실행해 확인한 뒤 여기에 적는다.

## 이전 버전 복구

**미확인.** v2.1 5절의 데이터 교체·롤백 절차와 개발 운영 가이드 7절이 기준이다. Week 8에 복구 실습을 수행한다.

---

이 파일에는 **실제 실행해 확인한 명령만** 적는다. 확인하지 못한 것은 `미확인`으로 남긴다.
