// Tailwind 2.x (postcss7-compat) uses `purge`, not `content`.
module.exports = {
    purge: {
      enabled: true,
      content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
      ],
    },
    darkMode: 'class', // Enable dark mode using class strategy
    theme: {
      extend: {
        fontFamily: {
          unlock: ['Unlock','cursive'],
          prosto: ["'Prosto One'", "cursive"],
          pixel: ['FreePixel', 'ui-monospace', 'monospace'],
          read: ['IBM Plex Sans', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        },
        borderRadius: {
          pixel: '2px',
        },
        colors: {
          sprout: {
            void: '#141816',
            panel: '#1c221f',
            'panel-2': '#252d29',
            border: '#3d4a42',
            lime: '#4ade80',
            muted: '#9aab9f',
            sms: '#a78bfa',
            text: '#e8eee9',
          },
        },
        backgroundColor: {
          'dark': '#141816',
          'light': '#f4f7f5',
        },
        textColor: {
          'dark': '#e8eee9',
          'light': '#213547',
        },
      },
    },
    corePlugins: {
      transition: false,
      transitionDuration: false,
      transitionProperty: false,
      transitionTimingFunction: false,
      transitionDelay: false,
    },
    plugins: [
      function({ addUtilities }) {
        const newUtilities = {
          '.no-transitions': {
            'transition': 'none !important',
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
