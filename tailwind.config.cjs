// tailwind.config.js
module.exports = {
    content: [
      "./index.html",
      "./src/**/*.{js,ts,jsx,tsx}",
    ],
    darkMode: 'class', // Enable dark mode using class strategy
    theme: {
      extend: {
        fontFamily: {
          unlock: ['Unlock','cursive'], // Add the Unlock font as a fallback
          prosto: ["'Prosto One'", "cursive"],
        },
        backgroundColor: {
          'dark': '#242424',
          'light': '#ffffff',
        },
        textColor: {
          'dark': 'rgba(255, 255, 255, 0.87)',
          'light': '#213547',
        },
      },
    },
    // Disable default transitions
    corePlugins: {
      transition: false,
      transitionDuration: false,
      transitionProperty: false,
      transitionTimingFunction: false,
      transitionDelay: false,
      animation: false,
    },
    plugins: [
      function({ addUtilities }) {
        const newUtilities = {
          '.no-transitions': {
            'transition': 'none !important',
            'animation': 'none !important',
            '-webkit-transition': 'none !important',
            '-moz-transition': 'none !important',
            '-o-transition': 'none !important',
            '-ms-transition': 'none !important',
          }
        }
        addUtilities(newUtilities)
      }
    ],
  };
  