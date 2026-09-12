/**
 * `/about` 골격 (v2.4 3절 "방법론·정책", UI/UX 설계 v1 D-2 화면 7). 문안은 C 담당(F7).
 *
 * 여기에는 확정 문장만 놓는다. 나머지 절은 문안이 오기 전까지 비워 둔다 — 임의로 채우지
 * 않는다.
 */

import { Link, useNavigate } from 'react-router-dom'
import { ko } from '../copy/ko'
import { METHOD_NOTICE, REGION_NOTICE } from '../format'
import { Button } from '../ui/Button'
import { Icon } from '../ui/Icon'
import styles from './Page.module.css'

export function AboutPage() {
  const navigate = useNavigate()
  return (
    <main className={styles.page}>
      <div className={styles.prose}>
        <header className={styles.header}>
          <Button variant="icon" aria-label={ko.search.back} onClick={() => navigate('/')}>
            <Icon name="back" />
          </Button>
          <h1 className={styles.title}>{ko.about.title}</h1>
        </header>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{ko.about.sections.method}</h2>
          <p className={styles.body}>{METHOD_NOTICE}</p>
          <p className={styles.body}>{ko.trust.estimate}</p>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{ko.about.sections.sources}</h2>
          <p className={styles.body}>{REGION_NOTICE}</p>
          <p className={styles.body}>{ko.about.poiDateFallback}</p>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{ko.about.sections.survey}</h2>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{ko.about.sections.privacy}</h2>
          <p className={styles.body}>{ko.share.notice}</p>
        </section>

        <p className={styles.section}>
          <Link to="/" className={styles.link}>
            {ko.compare.toMap}
          </Link>
        </p>
      </div>
    </main>
  )
}
