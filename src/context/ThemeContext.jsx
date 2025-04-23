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
    
    // This sets the localStorage on initial load to ensure consistency
    if (localStorage.getItem('darkMode') === null) {
      localStorage.setItem('darkMode', 'true');
    }
  }, []);
  
  // Apply theme class when it changes
  useEffect(() => {
    // Batch DOM operations for better performance
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    
    // Store preference (only when it changes)
    localStorage.setItem('darkMode', darkMode.toString());
  }, [darkMode]);
  
  // Listen for system preference changes (unchanged)
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    
    const handleChange = (e) => {
      // Only update if user hasn't explicitly set a preference
      if (localStorage.getItem('darkMode') === null) {
        setDarkMode(e.matches);
      }
    };
    
    // Add listener
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
    } else {
      // For older browsers
      mediaQuery.addListener(handleChange);
    }
    
    return () => {
      // Clean up
      if (mediaQuery.removeEventListener) {
        mediaQuery.removeEventListener('change', handleChange);
      } else {
        mediaQuery.removeListener(handleChange);
      }
    };
  }, []);
  
  // Toggle theme - memoized to prevent unnecessary renders
  const toggleTheme = React.useCallback(() => {
    setDarkMode(prev => !prev);
  }, []);
  
  // Provide context with memoized value
  const contextValue = React.useMemo(() => ({ 
    darkMode, 
    toggleTheme 
  }), [darkMode, toggleTheme]);
  
  return (
    <ThemeContext.Provider value={contextValue}>
      {children}
    </ThemeContext.Provider>
  );
};

export default ThemeContext; 