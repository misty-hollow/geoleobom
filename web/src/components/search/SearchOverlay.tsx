/**
 * 모바일 검색 오버레이 `/search` (UI/UX 설계 v1 D-2 화면 2).
 *
 * 키보드가 떠 있는 동안 지도와 싸우지 않게 검색만 한다. 전면 흰 화면. 지도는 뒤에 그대로
 * 남아 있다(MapPage가 이 오버레이를 조건부로 얹는다). 검색어는 URL에 넣지 않는다.
 */

import type { SearchResult } from '../../api/client'
import { ko } from '../../copy/ko'
import styles from './Search.module.css'
import { SearchBox } from './SearchBox'

export interface SearchOverlayProps {
  onSelect: (result: SearchResult) => void
  onBack: () => void
}

export function SearchOverlay({ onSelect, onBack }: SearchOverlayProps) {
  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label={ko.search.inputLabel}>
      <SearchBox variant="overlay" onSelect={onSelect} onBack={onBack} autoFocus />
    </div>
  )
}
