// tailwind.config.js
export default {
    content: [
      "./index.html",
      "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
      extend: {
        fontFamily: {
          unlock: ['Unlock','cursive'], // Add the Unlock font as a fallback
        },
      },
    },
    plugins: [],
  };
  