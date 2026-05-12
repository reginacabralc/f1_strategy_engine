/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        pitwall: {
          bg: "#0f1117",
          surface: "#1a1d27",
          border: "#2a2d3a",
          text: "#e2e8f0",
          muted: "#6b7280",
          accent: "#e10600",
        },
      },
    },
  },
  plugins: [],
};
