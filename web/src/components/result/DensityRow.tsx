/**
 * 카페·음식점 행 (UI/UX 설계 v1 D-2 화면 3, H-2). 탭 없음(경로 없음).
 *
 * `capped` → 20+ · `complete` → {count} + 곳 · `incomplete` → 집계 미완료(회색 + 아이콘).
 * 두 번째 줄은 `status`로만 고른다. "다시 분석하면 완료돼요" 류 문구는 두지 않는다 —
 * `incomplete` 결과도 서버 캐시에 30일 남는다.
 */

import type { Density } from '../../api/client'
import { ko } from '../../copy/ko'
import { DENSITY_CAPPED_LABEL, DENSITY_LABEL, DENSITY_SUBLABEL } from '../../format'
import { DENSITY_INCOMPLETE, densitySecondLine } from '../../status/labels'
import { Icon } from '../../ui/Icon'
import styles from './Result.module.css'

export function DensityRow({ density }: { density: Density }) {
  return (
    <li className={styles.rowItem}>
      <div className={styles.row}>
        <Icon name="food_cafe" className={styles.rowIcon} />
        <span className={styles.rowMain}>
          <span className={`${styles.rowName} ${styles.rowNameInline}`}>
            {DENSITY_LABEL}
            <span className={styles.rowSubInline}>{DENSITY_SUBLABEL}</span>
          </span>
          <span className={styles.rowSub}>{densitySecondLine(density)}</span>
        </span>
        <span className={styles.rowValue}>
          <DensityValue density={density} />
          <span className={styles.chevronSpacer} aria-hidden="true" />
        </span>
      </div>
    </li>
  )
}

function DensityValue({ density }: { density: Density }) {
  switch (density.status) {
    case 'capped':
      return <span className={styles.num}>{DENSITY_CAPPED_LABEL}</span>
    case 'complete':
      return (
        <span className={styles.num}>
          {density.count ?? 0}
          <span className={styles.numUnit}>{ko.density.unit}</span>
        </span>
      )
    case 'incomplete':
      return (
        <span className={`${styles.status} ${styles.muted}`}>
          <Icon name={DENSITY_INCOMPLETE.icon} />
          {DENSITY_INCOMPLETE.label}
        </span>
      )
  }
}
