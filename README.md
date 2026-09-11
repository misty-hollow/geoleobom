# 걸어봄 (geoleobom)

위치 하나를 넣으면 생활시설까지 **실제 보행망 기준** 예상 도보시간을 보여주고, 후보를 4곳까지 담아 비교·공유하는 웹앱.
제품 범위와 기술 스택은 `docs/걸어봄_확정설계_v2.2.md`가 기준이다.

- 확정 설계: `docs/걸어봄_확정설계_v2.2.md` (동결. 단일 기준)
- 확정 설계 v2.1: `docs/걸어봄_확정설계_v2.1.md` (동결 원본. 이력 문서)
- 개발 운영 가이드: `docs/걸어봄_개발운영가이드_v1.md` (검증·학습 참고. 현재 작업 규칙은 AGENTS.md)
- 프로젝트 안내와 승인된 결정: `PROJECT.md`
- 현재 상태: `STATUS.md`
- AI 공통 작업 규칙: `AGENTS.md`

## 현재 저장소 상태

기준 문서, 운영 파일, HTTPS 빈 페이지 배포 설정과 최소 CI가 있다. **제품 기능 코드는 아직 없다.**

```
docs/          확정설계 v2.1(이력)·v2.2(현재) + 개발운영가이드 v1
deploy/        HTTPS 빈 페이지의 Compose·Caddy·정적 파일
.github/       최소 CI·PR 양식·최초 보호 설정 요청 본문
PROJECT.md     안내 + 승인된 결정
AGENTS.md      AI 공통 작업 규칙
CLAUDE.md      AGENTS.md 연결
README.md      이 파일
STATUS.md      현재 상태와 다음 작업
.gitattributes 줄바꿈 규칙
.gitignore     제외 규칙
```

제품 코드 디렉터리는 해당 구현을 시작할 때 만든다 (`PROJECT.md` 5절).

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

`.github/workflows/ci.yml`의 `repository-baseline`은 변경 줄 공백 오류, Compose 설정, Caddy 설정, Git 이력 비밀값을 검사한다. 실제 실행 결과는 해당 PR의 Checks에 남긴다. 이것은 제품 계산·실제 OSRM·운영 배포 검증이 아니다. 제품 코드가 생길 때 타입·빌드·계산 검사를 함께 추가한다.

자동 병합 초기 설정과 미완료 조건은 [최초 검증 안내](docs/automation-bootstrap.md)에 있다. CI 성공과 GitHub 보호 설정·독립 검토 완료를 구분한다.

## 배포

HTTPS 빈 페이지 배포 완료 기록은 `STATUS.md`에 있다. **재현 가능한 자동 배포 명령은 아직 미확인**이다. 배포 규약은 v2.2 5절, 현재 실행 권한은 AGENTS.md 5절을 따른다. 실제로 실행해 확인한 뒤 명령을 적는다.

## Git 저장·복구 (2026-09-10 실제 실행해 확인)

아래 순서를 실제로 한 번 수행해 동작을 확인했다. 연습 대상은 `README.md` 한 줄이었다.

1. **작업 브랜치 생성·전환** — `main`이 `origin/main`과 같고 변경이 없는 상태에서 시작한다.

   ```
   git switch --create chore/git-recovery-practice
   ```

2. **변경 확인** — 무엇이 어떻게 바뀌었는지 커밋 전에 본다.

   ```
   git diff -- README.md
   git status --short
   ```

3. **특정 파일만 stage** — 커밋에 넣을 파일을 이름으로 지정한다.

   ```
   git add README.md
   git status --short
   ```

4. **커밋**

   ```
   git commit -m "chore: practice git recovery workflow"
   git log --oneline -2
   ```

5. **원격 브랜치 생성과 업로드** — 처음 올리는 브랜치는 `-u`로 연결까지 함께 한다.

   ```
   git push -u origin chore/git-recovery-practice
   ```

6. **되돌리기** — 이미 커밋하고 올린 변경은 `revert`로 되돌린다. 새 커밋이 하나 더 생기고 기존 이력은 남는다.

   ```
   git revert --no-edit 26e597c
   ```

7. **되돌린 결과 업로드**

   ```
   git push
   ```

**복구가 제대로 됐는지 확인하는 방법**

```
git diff <되돌리기 전 기준 커밋>..HEAD -- README.md
git status
```

첫 명령의 출력이 비어 있으면 파일 내용이 기준 시점과 같다. `git status`가 `working tree clean`이면 남은 변경이 없다.

**`main`이 손상되지 않았는지 확인하는 방법**

```
git rev-parse main
git rev-parse origin/main
git branch -vv
git ls-remote --heads origin
```

앞의 두 값이 서로 같고 작업 시작 전 기준 커밋과 같으면 `main`은 그대로다. `git ls-remote`는 GitHub 서버의 실제 상태를 직접 읽으므로 원격까지 확인할 수 있다.

확인된 사실: 위 연습은 작업 브랜치 안에서만 일어났고 `main`과 `origin/main`은 기준 커밋에서 움직이지 않았다.

`reset --hard`, `rebase`, 강제 push는 사용하지 않았고 확인하지도 않았다.

## 데이터 배포본 복구

**미확인.** v2.2 5절의 데이터 교체·롤백 절차와 개발 운영 가이드 7절이 기준이다. Week 8에 복구 실습을 수행한다.

---

이 파일에는 **실제 실행해 확인한 명령만** 적는다. 확인하지 못한 것은 `미확인`으로 남긴다.
