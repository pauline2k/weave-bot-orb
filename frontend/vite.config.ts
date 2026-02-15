import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: "dist",
    assetsDir: "assets"
  },
  server: {
    port: 8080,
    proxy: {
      // any request starting with /api goes to the backend
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true
      }
    }
  }
})
