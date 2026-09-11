import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 개발 서버에서 /api 를 로컬 FastAPI(uvicorn 기본 8000)로 넘긴다.
// 운영에서는 Caddy가 같은 도메인의 /api/* 를 api 컨테이너로 프록시한다 (v2.2 5절).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
