/**
 * 현위치 한 번 얻기 (DESIGN.md 24절, v2.5 3절).
 *
 * v2.5 3절이 확정한 것: "사용자가 버튼을 눌렀을 때만 브라우저 위치 API로 **1회** 획득해
 * pending 핀으로 보이고, 사용자가 보정해 `여기 분석`으로 확정한다. 진입 시 권한 요청·지속
 * 추적·IP 추정·획득 좌표 저장은 하지 않는다."
 *
 * ## 이 훅이 하지 않는 것
 *
 *   - **`watchPosition`을 쓰지 않는다.** 지속 추적이며 3절이 금지했다. 한 번 부르고 끝이다.
 *   - **마운트에서 아무것도 부르지 않는다.** `request()`는 버튼 클릭에서만 불린다.
 *     `getCurrentPosition`을 부르는 순간이 브라우저가 권한을 묻는 순간이므로, 진입만으로
 *     권한 프롬프트가 뜨면 그 자체가 규약 위반이다.
 *   - **좌표를 들고 있지 않는다.** 성공하면 `onSuccess`로 **넘기고 잊는다.** 확정 전
 *     좌표의 유일한 자리는 화면의 pending 상태 하나이며(24절), 여기에 사본을 두면
 *     "어디에 남았나"를 세는 자리가 둘이 된다.
 *
 * ## 실패는 두 갈래뿐이다
 *
 * 24절의 상태표대로 `PERMISSION_DENIED`는 `denied`(권한 안내), 그 밖(`POSITION_UNAVAILABLE`·
 * timeout)은 `unavailable`이다. 새 오류 코드나 상세 설명을 만들지 않는다 — 사용자가 할 일이
 * 두 가지(권한을 켜거나, 검색·지도로 고르거나)뿐이기 때문이다.
 */

import { useCallback, useRef, useState } from 'react'

/** 24절: `accuracy > 200m`면 경고 줄을 띄운다. 실사용 뒤 조정 가능한 파라미터다. */
export const ACCURACY_WARN_M = 200

/** 위치 요청 한 번의 상한. 넘으면 `unavailable`이다(24절 timeout). */
const TIMEOUT_MS = 10_000

export type LocationStatus = 'idle' | 'loading' | 'denied' | 'unavailable'

export interface CurrentLocationFix {
  lon: number
  lat: number
  /** 브라우저가 말한 반경(m). 24절 경고 줄의 `{거리}`가 이 값이다. */
  accuracyM: number
}

export interface UseCurrentLocation {
  /** `navigator.geolocation`이 없으면 false — 화면은 버튼 자체를 숨긴다(24절). */
  supported: boolean
  status: LocationStatus
  /** 버튼 클릭에서만 부른다. */
  request: () => void
}

export interface UseCurrentLocationOptions {
  /** 성공. 훅은 좌표를 들고 있지 않고 여기로 넘긴다. */
  onSuccess: (fix: CurrentLocationFix) => void
  /** 실패 안내(24절 토스트). 문구는 화면이 고른다. */
  onDenied: () => void
  onUnavailable: () => void
}

export function useCurrentLocation({
  onSuccess,
  onDenied,
  onUnavailable,
}: UseCurrentLocationOptions): UseCurrentLocation {
  const [status, setStatus] = useState<LocationStatus>('idle')
  // 콜백이 매 렌더 바뀌어도 `request`가 다시 만들어지지 않게 한다.
  const handlers = useRef({ onSuccess, onDenied, onUnavailable })
  handlers.current = { onSuccess, onDenied, onUnavailable }
  const inFlight = useRef(false)

  // 키가 아니라 **값**을 본다. `'geolocation' in navigator`는 값이 undefined여도 참이라
  // API가 없는 환경에서 버튼을 남긴다(24절: 없으면 버튼 자체를 숨긴다).
  const supported = typeof navigator !== 'undefined' && navigator.geolocation != null

  const request = useCallback(() => {
    if (!supported || inFlight.current) return
    inFlight.current = true
    setStatus('loading')
    navigator.geolocation.getCurrentPosition(
      (position) => {
        inFlight.current = false
        setStatus('idle')
        handlers.current.onSuccess({
          lon: position.coords.longitude,
          lat: position.coords.latitude,
          // 브라우저가 정확도를 주지 않는 경우가 있다. 모르면 경고를 띄우지 않는다.
          accuracyM: Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : 0,
        })
      },
      (error) => {
        inFlight.current = false
        // 거부는 "권한을 켜 주세요"가 아니라 **다른 방법 안내**로 끝난다(24절).
        const denied = error.code === error.PERMISSION_DENIED
        setStatus(denied ? 'denied' : 'unavailable')
        if (denied) handlers.current.onDenied()
        else handlers.current.onUnavailable()
      },
      // `enableHighAccuracy`를 켜지 않는다. 24절이 경고로 다루는 오차(데스크톱·Wi-Fi 추정
      // 2~5km)는 이 옵션으로 사라지지 않고, 켜면 기기가 GPS를 깨워 더 오래 기다린다.
      { enableHighAccuracy: false, timeout: TIMEOUT_MS, maximumAge: 0 },
    )
  }, [supported])

  return { supported, status, request }
}
