import { Link } from 'react-router-dom'
import { ko } from '../copy/ko'
import styles from './Page.module.css'

export function NotFoundPage() {
  return (
    <main className={styles.page}>
      <div className={styles.inner}>
        <div className={styles.empty}>
          <h1 className={styles.emptyTitle}>{ko.notFound.title}</h1>
          <Link to="/" className={styles.link}>
            {ko.notFound.toMap}
          </Link>
        </div>
      </div>
    </main>
  )
}
