/**
 * 모바일 플로팅 상단 바 (UI/UX 설계 v1 D-1). 검색 트리거(→ /search) + 후보 버튼 [☆ n].
 * 첫 진입에서 검색을 자동 포커스하지 않는다 — 키보드가 지도를 덮고 핀 입력 경로를 가린다.
 */

import { ko } from '../copy/ko'
import { Icon } from '../ui/Icon'
import styles from './Layout.module.css'

export interface TopBarProps {
  onOpenSearch: () => void
  candidateCount: number
  onOpenCandidates: () => void
}

export function TopBar({ onOpenSearch, candidateCount, onOpenCandidates }: TopBarProps) {
  return (
    <header className={styles.topBar}>
      <button type="button" className={styles.searchTrigger} onClick={onOpenSearch} aria-label={ko.topBar.openSearch}>
        <Icon name="search" />
        <span>{ko.topBar.searchPlaceholder}</span>
      </button>
      <button
        type="button"
        className={styles.candidatesButton}
        onClick={onOpenCandidates}
        aria-label={`${ko.topBar.openCandidates} ${ko.topBar.candidates(candidateCount)}`}
      >
        <Icon name={candidateCount > 0 ? 'starFilled' : 'star'} />
        <span aria-hidden="true">{candidateCount}</span>
      </button>
    </header>
  )
}
