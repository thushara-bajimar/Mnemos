/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"], mono: ["JetBrains Mono", "Consolas", "monospace"] },
      colors: {
        ink: { 50: "#f6f7f9", 100: "#eceef2", 200: "#d5d9e2", 300: "#b0b8c9", 400: "#8591ab", 500: "#667391", 600: "#515c78", 700: "#434b62", 800: "#3a4053", 900: "#1e2230", 950: "#13151f" },
        brand: { 50: "#eef4ff", 100: "#dae6ff", 200: "#bdd3ff", 300: "#90b6ff", 400: "#5c8dfd", 500: "#3866f6", 600: "#2248eb", 700: "#1a36d8", 800: "#1c2eaf", 900: "#1c2d8a" },
      },
    },
  },
  plugins: [],
};
