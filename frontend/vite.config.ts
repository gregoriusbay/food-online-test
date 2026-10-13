import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The app calls the backend under /api (same as nginx in production);
// in dev, Vite forwards /api/* to the Flask backend with the prefix stripped.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        "/api": {
          target: env.BACKEND_API_URL || "http://localhost:5000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
