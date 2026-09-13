/**
 * 자체 SVG 아이콘 (DESIGN.md 6절). 20px 그리드, 1.75px 스트로크, 둥근 끝. 외부 아이콘
 * 라이브러리 없음. 브랜드 마크 모사 없음.
 *
 * 의미를 전달하는 아이콘은 `aria-hidden`이고 옆 텍스트가 의미를 갖는다. 아이콘 단독
 * 버튼은 버튼에 `aria-label`을 단다.
 */

export type IconName =
  // 카테고리 6
  | 'convenience'
  | 'grocery'
  | 'pharmacy'
  | 'medical'
  | 'park'
  | 'food_cafe'
  // 상태 5
  | 'uncertain'
  | 'unreachable'
  | 'none'
  | 'incomplete'
  | 'snap'
  // UI
  | 'search'
  | 'close'
  | 'back'
  | 'pin'
  | 'star'
  | 'starFilled'
  | 'share'
  | 'chevron'
  | 'plus'
  | 'minus'
  | 'recenter'
  | 'route'
  | 'check'
  | 'copy'

const PATHS: Record<IconName, React.ReactNode> = {
  convenience: (
    <>
      <rect x="3" y="6" width="14" height="11" rx="1.5" />
      <path d="M3 9h14M7 6V4.5h6V6M8 12.5h4" />
    </>
  ),
  grocery: (
    <>
      <path d="M3 6h2.2l1.6 8.5h8.4L17 8H6" />
      <circle cx="8" cy="17" r="1" />
      <circle cx="14" cy="17" r="1" />
    </>
  ),
  pharmacy: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6.5v7M6.5 10h7" />
    </>
  ),
  medical: (
    <>
      <rect x="3.5" y="4.5" width="13" height="12" rx="1.5" />
      <path d="M10 7.5v6M7 10.5h6" />
    </>
  ),
  park: (
    <>
      <path d="M10 3.5 5.5 10h2.2L4.5 14.5h11L12.3 10h2.2Z" />
      <path d="M10 14.5V17" />
    </>
  ),
  food_cafe: (
    <>
      <path d="M4 7h9v5.5A3.5 3.5 0 0 1 9.5 16h-2A3.5 3.5 0 0 1 4 12.5Z" />
      <path d="M13 8.5h1.5a2 2 0 0 1 0 4H13M3.5 18h11" />
    </>
  ),
  uncertain: (
    <>
      <path d="M10 3.5 17 16H3Z" />
      <path d="M10 8v4M10 14.2v.3" />
    </>
  ),
  unreachable: (
    <>
      <path d="M3 15c3-4 5-4 7-2M12 9.5c2-1.5 3.5-1.5 5-.5" />
      <path d="M4.5 4.5l11 11" />
    </>
  ),
  none: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M6.5 10h7" />
    </>
  ),
  incomplete: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 3a7 7 0 0 1 0 14Z" fill="currentColor" stroke="none" />
    </>
  ),
  snap: (
    <>
      <path d="M7 17s-4-4.5-4-8a4 4 0 0 1 8 0c0 3.5-4 8-4 8Z" />
      <path d="M12.5 12c1-1 2-1 3 0s2 1 3 0" />
    </>
  ),
  search: (
    <>
      <circle cx="9" cy="9" r="5.5" />
      <path d="m13.2 13.2 3.8 3.8" />
    </>
  ),
  close: <path d="m5 5 10 10M15 5 5 15" />,
  back: <path d="M12.5 4 6.5 10l6 6" />,
  pin: (
    <>
      <path d="M10 17.5s-5.5-5.5-5.5-9.5a5.5 5.5 0 0 1 11 0c0 4-5.5 9.5-5.5 9.5Z" />
      <circle cx="10" cy="8" r="1.8" />
    </>
  ),
  star: <path d="m10 3 2.1 4.6 5 .6-3.7 3.4 1 5L10 14.1l-4.4 2.5 1-5L2.9 8.2l5-.6Z" />,
  starFilled: (
    <path
      d="m10 3 2.1 4.6 5 .6-3.7 3.4 1 5L10 14.1l-4.4 2.5 1-5L2.9 8.2l5-.6Z"
      fill="currentColor"
    />
  ),
  share: (
    <>
      <path d="M10 3v10M6.5 6.5 10 3l3.5 3.5" />
      <path d="M4.5 10.5v5a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-5" />
    </>
  ),
  chevron: <path d="m7.5 4.5 5.5 5.5-5.5 5.5" />,
  plus: <path d="M10 4.5v11M4.5 10h11" />,
  minus: <path d="M4.5 10h11" />,
  recenter: (
    <>
      <circle cx="10" cy="10" r="5" />
      <path d="M10 2.5v3M10 14.5v3M2.5 10h3M14.5 10h3" />
    </>
  ),
  route: (
    <>
      <circle cx="5" cy="15" r="2" />
      <circle cx="15" cy="5" r="2" />
      <path d="M6.5 13.5 9 9h3l1.5-2.5" />
    </>
  ),
  check: <path d="m4.5 10.5 3.5 3.5 7.5-8" />,
  copy: (
    <>
      <rect x="7" y="7" width="9.5" height="9.5" rx="1.5" />
      <path d="M13 7V5a1.5 1.5 0 0 0-1.5-1.5h-6A1.5 1.5 0 0 0 4 5v6A1.5 1.5 0 0 0 5.5 12.5H7" />
    </>
  ),
}

export interface IconProps {
  name: IconName
  size?: number
  className?: string
}

export function Icon({ name, size = 20, className }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {PATHS[name]}
    </svg>
  )
}
