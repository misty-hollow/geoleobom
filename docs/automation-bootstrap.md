# 최초 자동 병합 경로 검증

이 문서는 초기 설정이 끝날 때까지 사용하는 실행 안내다. 상시 행동 규칙은 `AGENTS.md`다.
사용자가 2026-09-11 승인한 운영 전환의 실행이며 같은 범위의 재승인은 요구하지 않는다.

## 현재 확인과 이번 완료 조건

- 기준: main `4528abcd253874d665c97d38a1cc0640811d2169`. 공개 저장소이며 열린 PR은 없었다.
- 2026-09-11 GitHub 조회: main `protected=false`, 저장소 ruleset `[]`.
- Work Mode GitHub 연결의 보호 상세 조회는 403(Administration 접근 없음). 저장소 소유자의 admin 권한과 연결에 위임된 권한은 다르다. 이 연결에는 보호·저장소 설정 변경 도구도 없다.
- 변경 파일 업로드(create-tree)도 GitHub 403으로 거부됐다. 원격 브랜치·커밋·PR은 만들지 못했고 GitHub CI도 실행하지 못했다. 제공된 패치를 사용자 PC의 Claude Code가 검토·적용하여 이어간다.
- 이번 추가: 현재 문서·Caddy 배포 설정을 검사하는 `repository-baseline` CI, PR 양식, 운영 규칙, 최초 보호 설정 요청 본문.
- 아직 증명하지 않은 것: 보호 규칙 활성화, 자동 병합·브랜치 정리 실동작, 독립 검토 자동 호출, 제품 계산, 실제 배포·복구.

완료는 **CI 성공 + 다른 담당의 현재 변경본 검토 + 보호 설정 확인 + 후속 A급 PR 자동 병합·브랜치 정리 확인**까지다. CI 파일만 추가하고 완료로 표시하지 않는다.

## Claude Code가 이어갈 순서

이 패치의 작성자는 Codex다. 먼저 Claude Code가 diff와 검사 증거를 독립 검토하고 PR을 만든다. 이후 Claude 작성 PR의 B·C 검토는 Codex가 맡는다. Claude가 이 패치를 실질적으로 수정하면 수정 범위에 대해 Codex 등 다른 담당의 재검토가 필요하다.

1. 현재 로컬 변경과 열린 PR을 확인하고 최신 origin/main에서 작업 브랜치를 만든다. 패치의 기준 SHA와 현재 main 차이를 비교한 뒤 적용한다. 사용자 작업을 덮어쓰지 않는다. PR의 기준·대상 SHA를 고정하고 실제 diff를 검토한다.
2. 설치된 `gh`와 로그인 상태를 확인한다. 없으면 승인된 도구 설치 범위에서 설치하고, 필요한 브라우저 인증만 사용자에게 넘긴다. 토큰 값을 채팅에 요청하지 않는다.
3. 현재 PR CI가 성공했는지 확인한다. 실패하면 실패 원인을 수정하고 변경분 재검토까지 한다.
4. 아래 보호 설정을 적용·재조회한다. 현재 보호가 이미 생겼으면 기존 규칙을 먼저 읽고 더 강한 조건을 보존한다. 아래 JSON으로 기존 보호를 무조건 덮어쓰지 않는다.
5. 최초 PR의 독립 검토 근거를 PR 본문에 남긴다. 중요 지적 해결과 보호 설정 확인 후 draft를 해제하고 확인한 HEAD를 지정해 squash merge한다.
6. 최초 PR이 병합된 뒤, CI·보호 설정의 실제 완료 사실을 STATUS.md에 기록하는 후속 A급 PR을 만든다. 이것으로 자동 병합과 원격 브랜치 삭제를 검증한다. 빈 변경이나 불필요한 연습 문서 PR을 만들지 않는다.
7. 이후 Claude → Codex 독립 검토 호출·결과 수집을 실제로 한 번 확인한다. 확장 설치 기록만으로 연결 완료로 표시하지 않는다. 이 연결이 안 되면 A는 계속 진행하고 B·C는 독립 검토 완료까지 draft로 남긴다.

## 관리 권한이 있는 환경에서 실행할 명령

다음 명령은 실행 안내이며, Work Mode에서 실제 실행해 확인한 명령이 아니다. 저장소 루트의 PowerShell에서 사용한다. gh 명령 실패 시 다음 변경 명령을 이어 실행하지 않는다.

```powershell
gh auth status
gh api repos/misty-hollow/geoleobom/branches/main --jq '{name, protected, head: .commit.sha}'
gh api 'repos/misty-hollow/geoleobom/rulesets?includes_parents=true'
```

보호가 활성화된 경우에는 상세도 읽어 기존 필수 검사·리뷰·우회 제한을 보존한다. 403은 보호가 없다는 뜻이 아니므로 권한 문제를 해결하기 전까지 변경하지 않는다.

```powershell
gh api repos/misty-hollow/geoleobom/branches/main/protection
```

**처음 보호를 만드는 경우** 아래 요청 본문을 사용한다. `repository-baseline` 검사 출처가 GitHub Actions(`app.id=15368`)인지 현재 PR의 check-runs 응답에서 먼저 확인한다. 다른 앱의 성공 상태로 대체하지 않는다.

```powershell
gh api --method PUT repos/misty-hollow/geoleobom/branches/main/protection --input .github/main-protection.json
gh api repos/misty-hollow/geoleobom/branches/main/protection
gh api --method PATCH repos/misty-hollow/geoleobom -F allow_auto_merge=true -F allow_squash_merge=true -F delete_branch_on_merge=true
gh api repos/misty-hollow/geoleobom --jq '{allow_auto_merge, allow_squash_merge, delete_branch_on_merge}'
```

적용 후 PR 경유, `repository-baseline` 필수·strict, 관리자 적용, force push·삭제 차단을 확인한다. 리뷰 수 0은 1인 저장소의 자기 승인 문제를 피하기 위한 설정이며 **B·C 독립 검토를 기계적으로 강제하는 설정은 아니다.** 현재는 AGENTS의 실행 조건이며, 별도 검토 결과를 병합 게이트로 연결할 때 그 검사를 추가해야 한다.

병합 대상 번호와 검토한 HEAD는 실제 조회 결과로 채운다. 아래는 템플릿이다. `--admin` 또는 main 직접 push로 우회하지 않는다.

```powershell
gh pr view <PR번호> --repo misty-hollow/geoleobom --json headRefOid,baseRefName,isDraft,url
gh pr checks <PR번호> --repo misty-hollow/geoleobom --required
gh pr ready <PR번호> --repo misty-hollow/geoleobom
gh pr merge <PR번호> --repo misty-hollow/geoleobom --squash --auto --match-head-commit <검토한HEAD> --delete-branch
```

자동 병합 대기 중 새 커밋이 올라오면 기존 B·C 검토를 그대로 사용하지 않는다. 검토가 완료되지 않은 PR에 자동 병합을 미리 예약하지 않는다. 병합 뒤 PR 상태·병합 SHA·원격 브랜치 삭제를 조회해 결과를 남긴다.

직접 main push 차단 확인을 위해 실제 main에 시험 커밋을 보내지 않는다. 먼저 설정 API로 강제를 확인한다. 부정 시험이 필요하면 별도의 시험 브랜치에 동등한 보호를 적용하여 유효한 새 커밋의 push가 거부되는지 확인한다. 변경 없는 push 또는 dry-run 성공만으로 보호를 검증하지 않는다.

## 검사와 되돌리기

- 최소 CI는 변경 줄 공백 오류, Compose 설정, Caddy 설정, Git 이력 비밀값 탐지만 검사한다. 비밀값 출력은 마스킹한다. 배포 키·운영 서버·제품 API를 사용하지 않는다.
- 최초 CI와 운영 규칙 변경은 B급이다. 이 PR의 자기 검토와 GitHub CI 성공을 독립 검토로 바꿔 적지 않는다.
- CI 파일 수정은 실제 workflow와 테스트를 변경할 수 있으므로 별도 검토 대상이다. 제품 코드가 생기는 PR에서 해당 계산·타입·빌드 검사를 추가한다.
- 초기 설정 실패 시 현재 PR을 draft로 유지하고 오류와 다음 행동을 기록한다. 실패를 피하려고 검사를 끄거나 관리자 우회로 병합하지 않는다.
- 병합 후 코드 변경을 되돌릴 때에는 squash 커밋의 revert PR을 만든다. 필수 CI를 삭제하는 revert라면 대체 검사를 먼저 마련하고 검사 약화에 필요한 결정을 받는다. Git revert가 GitHub 보호 설정까지 되돌리는 것은 아니다.

후속 작업은 API·프론트 골격 → 배포·복구 자동화 순서다. 카카오·위치정보법 문의 등 외부 대기 작업과 기존 게이트 미결 사항은 STATUS에서 계속 관리한다. 게이트 2 성능·한국 응답시간 측정을 임의로 완료 처리하거나 일정상 자동 유예하지 않는다.

참고: [보호 규칙](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), [gh pr merge](https://cli.github.com/manual/gh_pr_merge), [GitHub Actions 권한](https://docs.github.com/en/actions/reference/security/secure-use).
