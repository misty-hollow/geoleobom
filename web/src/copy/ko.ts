/**
 * 사용자에게 보이는 문구 전부 (UI/UX 설계 v1 D·E·H절, DESIGN.md 21절).
 *
 * 컴포넌트에는 한국어 리터럴을 두지 않는다. 여기 없는 문장은 화면에 없다.
 *
 * **여기 있는 것은 UI 문구다.** 확정설계가 글자까지 고정한 계약 문구(결과 설명 문장,
 * 상태 문구 3종, "현재 충청권만 지원합니다", 데이터 기준일 라벨, "데이터가 갱신되었습니다",
 * 우회 표시 형식)는 `format.ts`에 있다. 두 파일이 같은 문장을 다르게 적는 일이 없게
 * 계약 문구는 여기서 다시 쓰지 않는다.
 *
 * 문체: "~해요". 한 문장에 정보 하나. 느낌표·이모지 없음. 내부 용어(OSRM·스냅·density·
 * fid·캐시) 없음.
 */

export const MAX_CANDIDATES_LABEL = 4

export const ko = {
  app: {
    title: '걸어봄',
    tagline: '이 집, 걸어서 살 만해?',
  },

  topBar: {
    searchPlaceholder: '주소, 건물, 장소 검색',
    openSearch: '검색',
    candidates: (count: number) => `후보 ${count}곳`,
    openCandidates: '담은 후보 열기',
  },

  hint: {
    empty: '살 곳을 검색하거나 지도를 눌러 핀을 놓으세요',
  },

  pending: {
    label: '지도에서 고른 위치',
    analyze: '여기 분석',
  },

  header: {
    pickedLabel: '지도에서 고른 위치',
    sharedLabel: '공유된 위치',
    save: '담기',
    saved: '담김',
    share: '공유',
    candidateTag: (n: number) => `후보 ${n}`,
  },

  trust: {
    verified: '실측 검증',
    unverified: '미검수 지역 · 예상치',
    estimate: '예상 도보시간이에요. 실제와 다를 수 있어요.',
  },

  warnings: {
    snap: (meters: number) =>
      `가장 가까운 보행로가 ${meters}m 떨어져 있어요. 도보시간이 실제와 다를 수 있어요.`,
  },

  loading: {
    analysis: '보행 경로를 계산하고 있어요',
    route: '경로를 불러오고 있어요',
  },

  live: {
    analysisDone: '분석이 끝났어요',
    analysisFailed: '분석에 실패했어요',
  },

  row: {
    nearestTag: '가장 가까움',
    routeShown: '경로 표시 중',
    routeLoading: '경로 표시 중…',
    uncertainNote: '보행로에서 멀리 떨어진 시설이 더 가까울 수 있어 확인이 필요해요',
    expandHint: (name: string) => `${name} 상세`,
  },

  density: {
    label: '카페·음식점',
    subLabel: '도보 10분 안',
    capped: '20곳까지 확인하고 멈췄어요',
    complete: (count: number) => `10분 안에 ${count}곳`,
    incomplete: (checked: number, total: number) => `후보 ${total}곳 중 ${checked}곳까지 확인했어요`,
    unit: '곳',
  },

  route: {
    close: '경로 닫기',
    failed: '경로를 표시할 수 없어요. 다시 시도해 주세요',
    retry: '다시 시도',
  },

  errors: {
    retry: '다시 시도',
    recenter: '공주대로 돌아가기',
    movePin: '핀 옮기기',
    pickOther: '다른 위치 고르기',
    outOfRegionBody: '대전·세종·충남·충북 안에서 위치를 골라 주세요.',
    snapFailedTitle: '이 위치 근처에서 보행로를 찾지 못했어요',
    snapFailedBody: '길에 가까운 곳으로 핀을 옮겨 다시 시도해 주세요.',
    rateLimitedTitle: '요청이 너무 잦아요',
    internalTitle: '분석 중 내부 오류가 났어요',
    internalBody: '이 위치는 지금 분석할 수 없어요. 다른 위치로 시도해 주세요.',
    osrmTitle: '경로 계산 서버에 문제가 있어요',
    timeoutTitle: '계산이 시간 안에 끝나지 않았어요',
    httpTitle: '서버에 연결할 수 없어요',
    networkTitle: '인터넷 연결을 확인해 주세요',
    networkBody: '연결되면 다시 시도할 수 있어요.',
    clientTimeoutTitle: '응답이 늦어지고 있어요',
    laterBody: '잠시 후 다시 시도해 주세요.',
  },

  search: {
    back: '뒤로',
    clear: '지우기',
    inputLabel: '주소, 건물, 장소 검색',
    resultsLabel: '검색 결과',
    hint: '도로명 주소나 건물 이름으로 검색해요',
    empty: (query: string) =>
      `'${query}' 검색 결과가 없어요. 도로명 주소나 건물 이름으로 다시 검색해 보세요`,
    failed: '검색을 할 수 없어요. 잠시 후 다시 시도해 주세요',
    retry: '다시 시도',
  },

  candidates: {
    title: (count: number) => `후보 ${count}/${MAX_CANDIDATES_LABEL}`,
    full: '가득 찼어요',
    empty: '담은 후보가 없어요. 결과 화면에서 ☆를 누르면 여기 모여요.',
    searchCta: '위치 검색',
    item: (n: number) => `후보 ${n}`,
    open: '열기',
    remove: '삭제',
    removeAria: (n: number) => `후보 ${n} 삭제`,
    clear: '모두 비우기',
    clearConfirm: '담은 후보를 모두 비울까요?',
    clearYes: '모두 비우기',
    compare: '비교하기',
    needTwo: '후보 2곳 이상이면 비교할 수 있어요',
    added: (count: number) => `후보에 담았어요 (${count}/${MAX_CANDIDATES_LABEL})`,
    removed: '후보에서 뺐어요',
    replaceTitle: '후보가 4곳이에요. 하나를 빼고 담을까요?',
    replaceConfirm: '빼고 담기',
    cancel: '취소',
    close: '닫기',
    barLabel: (count: number) => `후보 ${count}/${MAX_CANDIDATES_LABEL}`,
  },

  share: {
    title: '링크 복사',
    notice: '이 링크에는 선택한 위치 좌표가 들어 있어요.',
    copy: '복사',
    copied: '링크를 복사했어요',
    system: '공유',
    manual: '길게 눌러 복사해 주세요',
    close: '닫기',
  },

  compare: {
    title: (count: number) => `후보 ${count}곳 비교`,
    itemColumn: '항목',
    dominant: '우세 항목',
    count: (n: number) => `${n}개`,
    countUnit: '개',
    bestMin: '가장 짧음',
    bestMax: '가장 많음',
    tooMany: '4곳까지만 비교해요',
    empty: '비교할 후보가 없어요',
    toMap: '지도로 가기',
    copyLink: '링크 복사',
    loadingCell: '불러오는 중',
    failedCell: '불러오지 못했어요',
    columnAria: (n: number) => `후보 ${n} 결과 화면으로`,
  },

  map: {
    ariaLabel: '지도',
    srHint: '지도는 위치를 고르는 보조 수단이에요. 검색으로도 같은 결과를 볼 수 있어요.',
    loadFailed: '지도를 불러올 수 없어요. 네트워크를 확인해 주세요',
    retry: '다시 시도',
    recenter: '공주대로',
    zoomIn: '확대',
    zoomOut: '축소',
  },

  sheet: {
    handle: '시트 크기 조절',
    resultLabel: '분석 결과',
  },

  summary: {
    label: '요약',
  },

  notFound: {
    title: '주소가 올바르지 않아요',
    toMap: '지도로 가기',
  },

  about: {
    title: '방법론·정책',
    sections: {
      method: '계산 방식',
      sources: '출처와 데이터 기준일',
      survey: '실측 결과',
      privacy: '개인정보·저장·공유',
    },
    poiDateFallback: '데이터 기준일은 결과 화면에 표시됩니다',
    pending: '문안은 준비 중이에요',
    version: (data: string, model: string) => `버전 ${data} · ${model}`,
  },
} as const
