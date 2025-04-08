// Utility functions for saving and retrieving filters from localStorage

// Keys for localStorage
const FILTER_STORAGE_KEY = 'sproutme_filters';

/**
 * Save filters to localStorage
 * @param {Object} filters - Object containing all filter states
 */
export const saveFiltersToStorage = (filters) => {
  try {
    console.log('Saving filters to localStorage:', filters);
    localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filters));
  } catch (error) {
    console.error('Error saving filters to localStorage:', error);
  }
};

/**
 * Retrieve filters from localStorage
 * @returns {Object|null} - Object containing all filter states or null if not found
 */
export const getFiltersFromStorage = () => {
  try {
    const storedFilters = localStorage.getItem(FILTER_STORAGE_KEY);
    console.log('Retrieved filters from localStorage:', storedFilters);
    return storedFilters ? JSON.parse(storedFilters) : null;
  } catch (error) {
    console.error('Error retrieving filters from localStorage:', error);
    return null;
  }
};

/**
 * Clear filters from localStorage
 */
export const clearFiltersFromStorage = () => {
  try {
    console.log('Clearing filters from localStorage');
    localStorage.removeItem(FILTER_STORAGE_KEY);
  } catch (error) {
    console.error('Error clearing filters from localStorage:', error);
  }
}; 