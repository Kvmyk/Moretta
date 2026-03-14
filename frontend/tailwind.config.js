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
          'bg': '#07060a',
          'surface': '#0e0d12',
          'surface-light': '#16151a',
          'border': '#1f1e26',
          'text': '#f5f5f5',
          'text-muted': '#7a7a7a',
          'accent': '#a295ba',
          'accent-light': '#dbd5e5',
          'red-accent': '#a32121',
          'green': '#b8afc8',
          'green-light': '#dbd5e5',
          'green-text': '#e0dde8',
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
