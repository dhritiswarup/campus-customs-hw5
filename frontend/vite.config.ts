import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The desk runs on http://localhost:5173 and calls the FastAPI backend (see .env).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, open: true },
});
