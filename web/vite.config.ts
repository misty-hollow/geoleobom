import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// 개발 서버에서 /api 를 로컬 FastAPI(uvicorn 기본 8000)로 넘긴다.
// 운영에서는 Caddy가 같은 도메인의 /api/* 를 api 컨테이너로 프록시한다 (v2.4 5절).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  // 단위·컴포넌트 검사. 기대값은 손계산 픽스처에서 온다 (AGENTS 4절).
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // CSS Module 클래스명을 원문 그대로 둔다. 검사가 `best` 같은 이름을 읽을 수 있다.
    css: { include: [/\.module\.css$/], modules: { classNameStrategy: 'non-scoped' } },
    // 검사에서는 SDK를 실제로 내려받지 않는다. 키는 훅이 "켜진" 경로를 타게 하는 자리표시자다.
    env: { VITE_KAKAO_JS_KEY: 'test-js-key-not-real' },
  },
})
