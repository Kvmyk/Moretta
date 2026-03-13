/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'pp': {
          'bg': '#1a1a1a',
          'surface': '#242424',
          'surface-light': '#2e2e2e',
          'border': '#3a3a3a',
          'text': '#e0e0e0',
          'text-muted': '#888888',
          'accent': '#4a6741',
          'accent-light': '#5a8050',
          'green': '#3d5a35',
          'green-light': '#4a6b40',
          'green-text': '#a8d49d',
          'red': '#d44040',
          'yellow': '#d4a840',
          'badge-red': '#ff4444',
          'badge-yellow': '#ffaa44',
          'badge-gray': '#888888',
        },
      },
      fontFamily: {
        'sans': ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        'mono': ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};
