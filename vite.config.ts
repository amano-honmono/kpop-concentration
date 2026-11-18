import { defineConfig } from "vite";

export default defineConfig({
  // 相対パスで書き出す(GitHub Pages の https://<user>.github.io/<repo>/ のようなサブパスでも動くように)
  base: "./",
});
