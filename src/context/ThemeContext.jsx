import React, { createContext, useState, useContext, useEffect, useRef } from 'react';

// Create context
const ThemeContext = createContext(null);

// Custom hook to use the theme context
export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider = ({ children }) => {
  // Keep track of whether this is the initial render
  const isInitialMount = useRef(true);
  
  // Check for stored preference, but always default to dark mode if none stored
  const [darkMode, setDarkMode] = useState(() => {
    const storedTheme = localStorage.getItem('darkMode');
    // Always default to true (dark mode) if no preference is stored
    return storedTheme !== null ? storedTheme === 'true' : true;
  });
  
  // Apply theme class immediately on initial render
  useEffect(() => {
    // Force dark mode on initial load and set localStorage
    if (isInitialMount.current) {
      if (darkMode) {
        document.documentElement.classList.add('dark');
      }
      
      // Set localStorage if not already set
      if (localStorage.getItem('darkMode') === null) {
        localStorage.setItem('darkMode', 'true');
      }
      
      isInitialMount.current = false;
    }
  }, [darkMode]);
  
  // Apply theme class when it changes - optimized for Chrome
  useEffect(() => {
    if (!isInitialMount.current) { // Skip on initial render as it's handled above
      // Add no-transitions class before making any changes
      document.documentElement.classList.add('no-transitions');
      
      // Force a repaint before continuing (needed especially for Chrome)
      // This prevents the browser from batching the class changes with the style changes
      void document.documentElement.offsetHeight;
      
      // Change theme synchronously without animations
      if (darkMode) {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }
      
      // Store preference
      localStorage.setItem('darkMode', String(darkMode));
      
      // Remove the no-transitions class after a short time
      setTimeout(() => {
        document.documentElement.classList.remove('no-transitions');
      }, 100);
    }
  }, [darkMode]);
  
  // Direct toggle function with no extra logic
  const toggleTheme = () => setDarkMode(!darkMode);
  
  return (
    <ThemeContext.Provider value={{ darkMode, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export default ThemeContext; 