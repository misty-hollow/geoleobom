/**
 * 검색 필드 + 결과 listbox (UI/UX 설계 v1 D-2 화면 2, H-6, DESIGN.md 10절).
 *
 * `variant`
 *   - `overlay`: 모바일 전면 화면. [←] + 입력(autofocus) + [×].
 *   - `inline`: 데스크톱 패널 상단. 입력 아래로 같은 listbox가 펼쳐진다. URL은 바뀌지 않는다.
 *
 * 접근성: `role="combobox"` + `aria-controls` + `aria-activedescendant`, ↑↓ Enter Esc.
 * 검색 실패는 이 컴포넌트 안에만 표시한다 — 분석 화면을 망가뜨리지 않는다(v2.4 4-5).
 * 선택 순간이 좌표 정규화의 "입력 시점"이다(4-2). 장소명·주소는 어디에도 저장하지 않는다.
 */

import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import type { SearchResult } from '../../api/client'
import { ko } from '../../copy/ko'
import { useSearch } from '../../hooks/useSearch'
import { Button, Spinner } from '../../ui/Button'
import { Icon } from '../../ui/Icon'
import styles from './Search.module.css'

export interface SearchBoxProps {
  variant: 'overlay' | 'inline'
  onSelect: (result: SearchResult) => void
  onBack?: () => void
  autoFocus?: boolean
}

export function SearchBox({ variant, onSelect, onBack, autoFocus = false }: SearchBoxProps) {
  const { query, setQuery, state, retry, reset } = useSearch()
  const [active, setActive] = useState<number>(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()

  const results: SearchResult[] =
    state.kind === 'results' ? state.results : state.kind === 'loading' ? state.previous : []
  const expanded = results.length > 0

  useEffect(() => {
    setActive(-1)
  }, [state])

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus()
  }, [autoFocus])

  function choose(result: SearchResult) {
    reset()
    onSelect(result)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' && results.length > 0) {
      event.preventDefault()
      setActive((index) => (index + 1) % results.length)
    } else if (event.key === 'ArrowUp' && results.length > 0) {
      event.preventDefault()
      setActive((index) => (index <= 0 ? results.length - 1 : index - 1))
    } else if (event.key === 'Enter') {
      if (active >= 0 && active < results.length) {
        event.preventDefault()
        choose(results[active])
      } else if (results.length === 1) {
        event.preventDefault()
        choose(results[0])
      }
    } else if (event.key === 'Escape') {
      if (query !== '') {
        event.preventDefault()
        reset()
      } else if (onBack !== undefined) {
        event.preventDefault()
        onBack()
      }
    }
  }

  const optionId = (index: number) => `${listId}-option-${index}`

  return (
    <div className={[styles.box, variant === 'overlay' ? styles.overlayBox : styles.inlineBox].join(' ')}>
      <div className={styles.fieldRow}>
        {variant === 'overlay' && onBack !== undefined && (
          <Button variant="icon" aria-label={ko.search.back} onClick={onBack}>
            <Icon name="back" />
          </Button>
        )}
        <div className={styles.field}>
          {variant === 'inline' && <Icon name="search" className={styles.fieldIcon} />}
          <input
            ref={inputRef}
            className={styles.input}
            type="search"
            role="combobox"
            aria-label={ko.search.inputLabel}
            aria-expanded={expanded}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={active >= 0 ? optionId(active) : undefined}
            autoComplete="off"
            enterKeyHint="search"
            maxLength={100}
            placeholder={ko.topBar.searchPlaceholder}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
          />
          {state.kind === 'loading' && <Spinner className={styles.fieldSpinner} />}
          {query !== '' && state.kind !== 'loading' && (
            <button
              type="button"
              className={styles.clear}
              aria-label={ko.search.clear}
              onClick={() => {
                reset()
                inputRef.current?.focus()
              }}
            >
              <Icon name="close" />
            </button>
          )}
        </div>
      </div>

      <div className={styles.below}>
        {state.kind === 'idle' && variant === 'overlay' && <p className={styles.hint}>{ko.search.hint}</p>}
        {state.kind === 'empty' && (
          <p className={styles.hint} role="status">
            {ko.search.empty(state.query)}
          </p>
        )}
        {state.kind === 'failed' && (
          <div className={styles.failed} role="status">
            <p className={styles.hint}>{ko.search.failed}</p>
            <Button variant="secondary" onClick={retry}>
              {ko.search.retry}
            </Button>
          </div>
        )}
        <ul
          id={listId}
          role="listbox"
          aria-label={ko.search.resultsLabel}
          className={styles.list}
          hidden={!expanded}
        >
          {results.map((result, index) => (
            <li
              key={`${result.lon},${result.lat},${index}`}
              id={optionId(index)}
              role="option"
              aria-selected={index === active}
              className={[styles.option, index === active ? styles.optionActive : ''].join(' ')}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(result)}
            >
              <span className={styles.optionName}>{result.name}</span>
              {result.address !== '' && <span className={styles.optionAddress}>{result.address}</span>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
