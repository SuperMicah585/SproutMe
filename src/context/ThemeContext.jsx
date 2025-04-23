import React, { createContext, useState, useContext, useEffect } from 'react';

// Create context
const ThemeContext = createContext(null);

// Custom hook to use the theme context
export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider = ({ children }) => {
  // Check for stored preference, but always default to dark mode if none stored
  const [darkMode, setDarkMode] = useState(() => {
    const storedTheme = localStorage.getItem('darkMode');
    // Always default to true (dark mode) if no preference is stored
    return storedTheme !== null ? storedTheme === 'true' : true;
  });
  
  // Apply theme class immediately on initial render
  useEffect(() => {
    // Force dark mode on initial load
    document.documentElement.classList.add('dark');
    
    // Set localStorage if not already set
    if (localStorage.getItem('darkMode') === null) {
      localStorage.setItem('darkMode', 'true');
    }
  }, []);
  
  // Apply theme class when it changes - direct DOM manipulation for speed
  useEffect(() => {
    // Direct DOM manipulation without animations
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    
    // Store preference
    localStorage.setItem('darkMode', darkMode.toString());
  }, [darkMode]);
  
  // Simple toggle function - direct implementation for speed
  const toggleTheme = () => {
    setDarkMode(prev => !prev);
  };
  
  return (
    <ThemeContext.Provider value={{ darkMode, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export default ThemeContext; 