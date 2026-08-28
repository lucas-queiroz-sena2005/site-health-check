/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#020617', // Slate 950
        surface: '#0f172a', // Slate 900
        border: '#1e293b', // Slate 800
      }
    },
  },
  plugins: [],
}
