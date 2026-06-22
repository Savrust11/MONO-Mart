/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        critical: { DEFAULT: '#ef4444', light: '#fee2e2', text: '#991b1b' },
        warning:  { DEFAULT: '#f59e0b', light: '#fef3c7', text: '#92400e' },
        overstock: { DEFAULT: '#3b82f6', light: '#dbeafe', text: '#1e40af' },
      },
      fontFamily: {
        sans: ['var(--font-noto-sans-jp)', 'Hiragino Sans', 'Yu Gothic', 'Meiryo', 'sans-serif'],
        mono: ['Consolas', 'Monaco', 'Courier New', 'monospace'],
      },
    },
  },
  plugins: [],
};
