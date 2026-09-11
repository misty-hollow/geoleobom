import { useEffect, useState } from 'react'

// v2.2 4-4에는 없는 운영용 엔드포인트. api/app/schemas.py HealthResponse와 같다.
type Health = {
  status: string
  time_model_version: string
  data_version: string | null
}

type HealthState = { kind: 'loading' } | { kind: 'ok'; health: Health } | { kind: 'error'; message: string }

export default function App() {
  const [state, setState] = useState<HealthState>({ kind: 'loading' })

  useEffect(() => {
    fetch('/api/health')
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return (await r.json()) as Health
      })
      .then((health) => setState({ kind: 'ok', health }))
      .catch((e: unknown) => setState({ kind: 'error', message: e instanceof Error ? e.message : String(e) }))
  }, [])

  return (
    <main>
      <h1>걸어봄</h1>
      <p>위치 하나를 넣으면 생활시설까지 실제 보행망 기준 예상 도보시간을 보여주는 웹앱. 아직 골격 단계다.</p>
      <section aria-label="api-health">
        <h2>API 상태</h2>
        {state.kind === 'loading' && <p>확인 중…</p>}
        {state.kind === 'ok' && (
          <dl>
            <dt>status</dt>
            <dd>{state.health.status}</dd>
            <dt>time_model_version</dt>
            <dd>{state.health.time_model_version}</dd>
            <dt>data_version</dt>
            <dd>{state.health.data_version ?? '없음 (데이터 배포본 미탑재)'}</dd>
          </dl>
        )}
        {state.kind === 'error' && <p>API 연결 실패: {state.message}</p>}
      </section>
    </main>
  )
}
