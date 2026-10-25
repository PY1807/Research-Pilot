import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Requests to /api go to the FastAPI server, so the browser sees one origin (no CORS setup).
// Inside docker compose the API is reachable as http://api:8000.
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': apiTarget,
    },
  },
})
