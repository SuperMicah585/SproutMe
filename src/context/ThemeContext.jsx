import React, { createContext, useContext, useState } from 'react';

// Create the theme context
const ThemeContext = createContext();

// Custom hook to use the theme
export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider = ({ children }) => {
  // More explicit boolean check for initial state
  const initialDarkMode = localStorage.getItem('darkMode') === 'false' ? false : true;
  const [darkMode, setDarkMode] = useState(initialDarkMode);
  
  // Direct toggle function with inline DOM manipulation for maximum speed
  const toggleTheme = () => {
    // Apply no-transition class
    document.documentElement.classList.add('no-transitions');
    
    // Toggle state
    const newDarkMode = !darkMode;
    setDarkMode(newDarkMode);
    
    // Direct DOM manipulation - don't wait for React
    if (newDarkMode) {
      document.documentElement.classList.add('dark');
      document.documentElement.style.backgroundColor = '#242424';
      document.documentElement.style.color = 'rgba(255, 255, 255, 0.87)';
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.style.backgroundColor = '#ffffff';
      document.documentElement.style.color = '#213547';
    }
    
    // Store in localStorage
    localStorage.setItem('darkMode', String(newDarkMode));
    
    // Remove no-transition class after a delay
    setTimeout(() => {
      document.documentElement.classList.remove('no-transitions');
    }, 50);
  };
  
  return (
    <ThemeContext.Provider value={{ darkMode, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export default ThemeContext; 