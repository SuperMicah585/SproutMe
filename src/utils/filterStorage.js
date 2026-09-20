const FILTER_STORAGE_KEY = 'sproutme_filters';

export const emptyStoredFilters = () => ({
  selectedCities: [],
  selectedGenres: [],
  selectedOrganizers: [],
  selectedVenues: [],
  searchTerm: '',
  priceSort: 'none',
  skipGeo: false,
});

export const saveFiltersToStorage = (filters) => {
  try {
    localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify({
      ...emptyStoredFilters(),
      ...filters,
    }));
  } catch (error) {
    console.error('Error saving filters to localStorage:', error);
  }
};

export const getFiltersFromStorage = () => {
  try {
    const storedFilters = localStorage.getItem(FILTER_STORAGE_KEY);
    return storedFilters ? { ...emptyStoredFilters(), ...JSON.parse(storedFilters) } : null;
  } catch (error) {
    console.error('Error retrieving filters from localStorage:', error);
    return null;
  }
};

export const clearFiltersFromStorage = () => {
  try {
    localStorage.removeItem(FILTER_STORAGE_KEY);
  } catch (error) {
    console.error('Error clearing filters from localStorage:', error);
  }
};
