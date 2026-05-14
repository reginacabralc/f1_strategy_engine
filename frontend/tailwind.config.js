/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        pitwall: {
          bg: "#0a0c12",
          surface: "#12151f",
          panel: "#0f1117",
          border: "#1e2130",
          "border-strong": "#2a2d3a",
          text: "#e2e8f0",
          muted: "#5a6070",
          accent: "#e10600",
          "accent-glow": "rgba(225,6,0,0.15)",
          green: "#22c55e",
          yellow: "#eab308",
          orange: "#f97316",
        },
      },
    },
  },
  plugins: [],
};
