import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/ui/",
  plugins: [react()],
  // The NVIDIA WebRTC SDK is loaded only when the engineer connects a stream.
  build: {
    chunkSizeWarningLimit: 850
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/healthz": "http://127.0.0.1:8000",
      "/v1": "http://127.0.0.1:8000"
    }
  }
});
