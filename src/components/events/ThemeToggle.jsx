import React from 'react';
import { useTheme } from '../../context/ThemeContext';

const ThemeToggle = ({ variant = 'icon' }) => {
  const { darkMode, toggleTheme } = useTheme();
  const isMenu = variant === 'menu';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={
        isMenu
          ? `mobile-nav-item font-medium py-3 px-4 rounded-lg flex items-center justify-center w-full ${
              darkMode ? 'bg-gray-700 text-yellow-200' : 'bg-gray-200 text-gray-800'
            }`
          : `p-2 rounded-lg flex items-center justify-center ${
              darkMode
                ? 'bg-gray-700 hover:bg-gray-600 text-yellow-200'
                : 'bg-gray-200 hover:bg-gray-300 text-gray-800'
            }`
      }
      aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
      title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {darkMode ? (
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
        </svg>
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
          <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
        </svg>
      )}
      {isMenu && <span className="ml-2">Theme</span>}
    </button>
  );
};

export default ThemeToggle;
