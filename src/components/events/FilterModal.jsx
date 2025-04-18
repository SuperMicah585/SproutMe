import React, { useState, useEffect } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { trackEvent } from "../../utils/analytics";

const FilterModal = ({
  activeFilterModal,
  setActiveFilterModal,
  availableGenres,
  availableOrganizers,
  availableVenues,
  availableCities,
  selectedGenres,
  selectedOrganizers,
  selectedVenues,
  selectedCities,
  setSelectedGenres,
  setSelectedOrganizers,
  setSelectedVenues,
  setSelectedCities,
  toggleArrayItem
}) => {
  const [modalSearchTerm, setModalSearchTerm] = useState('');
  const [filteredOptions, setFilteredOptions] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasInitialDataCheck, setHasInitialDataCheck] = useState(false);
  const { darkMode } = useTheme();
  
  // Reset search term and handle loading state when modal changes
  useEffect(() => {
    if (!activeFilterModal) return;
    
    setModalSearchTerm('');
    
    // Only set loading state if we haven't done initial data check
    // or if we're switching to a different filter type
    if (!hasInitialDataCheck || !isLoading) {
      setIsLoading(true);
    }
    
    // Determine if we have data already
    const hasData = () => {
      switch (activeFilterModal) {
        case 'genres':
          return availableGenres && availableGenres.length > 0;
        case 'organizers':
          return availableOrganizers && availableOrganizers.length > 0;
        case 'venues':
          return availableVenues && availableVenues.length > 0;
        case 'cities':
          return availableCities && availableCities.length > 0;
        default:
          return true;
      }
    };
    
    // Check if data already exists before setting any timeouts
    if (hasData()) {
      setIsLoading(false);
      setHasInitialDataCheck(true);
      return;
    }
    
    // Mark that we've done the initial data check
    setHasInitialDataCheck(true);
    
    // Wait a bit longer on initial page load to avoid the double loading
    const initialTimeout = 500;
    
    let timer = setTimeout(() => {
      if (hasData()) {
        setIsLoading(false);
      } else {
        // Set up a data check interval that runs less frequently
        const dataCheckInterval = setInterval(() => {
          if (hasData()) {
            setIsLoading(false);
            clearInterval(dataCheckInterval);
          }
        }, 300);
        
        // Safety timeout to prevent infinite loading
        setTimeout(() => {
          clearInterval(dataCheckInterval);
          setIsLoading(false);
        }, 2500);
      }
    }, initialTimeout);
    
    return () => {
      clearTimeout(timer);
    };
  }, [activeFilterModal, availableGenres, availableOrganizers, availableVenues, availableCities, hasInitialDataCheck, isLoading]);
  
  // Filter options based on search term
  useEffect(() => {
    if (!modalSearchTerm.trim()) {
      // If no search term, use all available options
      switch (activeFilterModal) {
        case 'genres':
          setFilteredOptions(availableGenres);
          break;
        case 'organizers':
          setFilteredOptions(availableOrganizers);
          break;
        case 'venues':
          setFilteredOptions(availableVenues);
          break;
        case 'cities':
          setFilteredOptions(availableCities);
          break;
        default:
          setFilteredOptions([]);
      }
      return;
    }
    
    const term = modalSearchTerm.toLowerCase().trim();
    
    switch (activeFilterModal) {
      case 'genres':
        setFilteredOptions(availableGenres.filter(item => 
          item.name.toLowerCase().includes(term)
        ));
        break;
      case 'organizers':
        setFilteredOptions(availableOrganizers.filter(item => 
          item.name.toLowerCase().includes(term)
        ));
        break;
      case 'venues':
        setFilteredOptions(availableVenues.filter(item => 
          item.name.toLowerCase().includes(term)
        ));
        break;
      case 'cities':
        setFilteredOptions(availableCities.filter(item => 
          item.name.toLowerCase().includes(term)
        ));
        break;
      default:
        setFilteredOptions([]);
    }
  }, [modalSearchTerm, activeFilterModal, availableGenres, availableOrganizers, availableVenues, availableCities]);

  if (!activeFilterModal) return null;

  const renderModalContent = () => {
    if (isLoading) {
      return (
        <div className="flex flex-col items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-500 mb-4"></div>
          <p className={`text-sm ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>
            Loading data...
          </p>
        </div>
      );
    }
    
    // Check if we have data to display
    const hasNoData = () => {
      switch (activeFilterModal) {
        case 'genres':
          return !availableGenres || availableGenres.length === 0;
        case 'organizers':
          return !availableOrganizers || availableOrganizers.length === 0;
        case 'venues':
          return !availableVenues || availableVenues.length === 0;
        case 'cities':
          return !availableCities || availableCities.length === 0;
        default:
          return false;
      }
    };
    
    // If we still have no data after loading is complete
    if (hasNoData()) {
      return (
        <div className="flex flex-col items-center justify-center h-64">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M12 20h.01" />
          </svg>
          <p className={`text-center ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>
            No data available. Please try again later.
          </p>
        </div>
      );
    }
    
    switch (activeFilterModal) {
      case "genres":
        return (
          <div className="space-y-2 h-64 overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <div className={`p-3 ${darkMode ? 'text-gray-400' : 'text-gray-500'} text-center transition-colors duration-300`}>No matching genres available</div>
            ) : (
              filteredOptions.map((genre) => (
                <div 
                  key={genre.name}
                  onClick={() => {
                    setSelectedGenres(toggleArrayItem(selectedGenres, genre.name));
                    // Track genre selection in Google Analytics
                    trackEvent('select_filter', {
                      'filter_type': 'genre',
                      'filter_value': genre.name,
                      'action': selectedGenres.includes(genre.name) ? 'deselect' : 'select'
                    });
                  }}
                  className={`p-3 rounded-lg flex items-center justify-between ${
                    selectedGenres.includes(genre.name)
                      ? 'bg-purple-600 text-white border border-purple-700'
                      : genre.count === 0 
                        ? darkMode 
                          ? 'bg-gray-700 border border-gray-600 opacity-50 text-gray-400' 
                          : 'bg-gray-100 border border-gray-200 opacity-50 text-gray-500'
                        : darkMode 
                          ? 'bg-gray-700 border border-gray-600 text-gray-300' 
                          : 'bg-gray-50 border border-gray-200 text-gray-700'
                  } transition-colors duration-300`}
                >
                  <div className="flex items-center">
                    <div className={`w-5 h-5 rounded border flex items-center justify-center mr-3 ${
                      selectedGenres.includes(genre.name)
                        ? 'bg-purple-500 border-purple-500'
                        : darkMode ? 'border-gray-500' : 'border-gray-400'
                    } transition-colors duration-300`}>
                      {selectedGenres.includes(genre.name) && (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      )}
                    </div>
                    <span>{genre.name}</span>
                  </div>
                  <span className={`text-sm font-medium ${
                    selectedGenres.includes(genre.name) 
                      ? 'text-white' 
                      : darkMode ? 'text-gray-400' : 'text-gray-600'
                  } transition-colors duration-300`}>{genre.count}</span>
                </div>
              ))
            )}
          </div>
        );
      case "organizers":
        return (
          <div className="space-y-2 h-64 overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <div className={`p-3 ${darkMode ? 'text-gray-400' : 'text-gray-500'} text-center transition-colors duration-300`}>No matching organizers available</div>
            ) : (
              filteredOptions.map((organizer) => (
                <div 
                  key={organizer.name}
                  onClick={() => {
                    setSelectedOrganizers(toggleArrayItem(selectedOrganizers, organizer.name));
                    // Track organizer selection in Google Analytics
                    trackEvent('select_filter', {
                      'filter_type': 'organizer',
                      'filter_value': organizer.name,
                      'action': selectedOrganizers.includes(organizer.name) ? 'deselect' : 'select'
                    });
                  }}
                  className={`p-3 rounded-lg flex items-center justify-between ${
                    selectedOrganizers.includes(organizer.name)
                      ? 'bg-purple-600 text-white border border-purple-700'
                      : organizer.count === 0 
                        ? darkMode 
                          ? 'bg-gray-700 border border-gray-600 opacity-50 text-gray-400' 
                          : 'bg-gray-100 border border-gray-200 opacity-50 text-gray-500'
                        : darkMode 
                          ? 'bg-gray-700 border border-gray-600 text-gray-300' 
                          : 'bg-gray-50 border border-gray-200 text-gray-700'
                  } transition-colors duration-300`}
                >
                  <div className="flex items-center">
                    <div className={`w-5 h-5 rounded border flex items-center justify-center mr-3 ${
                      selectedOrganizers.includes(organizer.name)
                        ? 'bg-purple-500 border-purple-500'
                        : darkMode ? 'border-gray-500' : 'border-gray-400'
                    } transition-colors duration-300`}>
                      {selectedOrganizers.includes(organizer.name) && (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      )}
                    </div>
                    <span>{organizer.name || "Unknown"}</span>
                  </div>
                  <span className={`text-sm font-medium ${
                    selectedOrganizers.includes(organizer.name) 
                      ? 'text-white' 
                      : darkMode ? 'text-gray-400' : 'text-gray-600'
                  } transition-colors duration-300`}>{organizer.count}</span>
                </div>
              ))
            )}
          </div>
        );
      case "venues":
        return (
          <div className="space-y-2 h-64 overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <div className={`p-3 ${darkMode ? 'text-gray-400' : 'text-gray-500'} text-center transition-colors duration-300`}>No matching venues available</div>
            ) : (
              filteredOptions.map((venue) => (
                <div 
                  key={venue.name}
                  onClick={() => {
                    setSelectedVenues(toggleArrayItem(selectedVenues, venue.name));
                    // Track venue selection in Google Analytics
                    trackEvent('select_filter', {
                      'filter_type': 'venue',
                      'filter_value': venue.name,
                      'action': selectedVenues.includes(venue.name) ? 'deselect' : 'select'
                    });
                  }}
                  className={`p-3 rounded-lg flex items-center justify-between ${
                    selectedVenues.includes(venue.name)
                      ? 'bg-purple-600 text-white border border-purple-700'
                      : venue.count === 0 
                        ? darkMode 
                          ? 'bg-gray-700 border border-gray-600 opacity-50 text-gray-400' 
                          : 'bg-gray-100 border border-gray-200 opacity-50 text-gray-500'
                        : darkMode 
                          ? 'bg-gray-700 border border-gray-600 text-gray-300' 
                          : 'bg-gray-50 border border-gray-200 text-gray-700'
                  } transition-colors duration-300`}
                >
                  <div className="flex items-center">
                    <div className={`w-5 h-5 rounded border flex items-center justify-center mr-3 ${
                      selectedVenues.includes(venue.name)
                        ? 'bg-purple-500 border-purple-500'
                        : darkMode ? 'border-gray-500' : 'border-gray-400'
                    } transition-colors duration-300`}>
                      {selectedVenues.includes(venue.name) && (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      )}
                    </div>
                    <span>{venue.name}</span>
                  </div>
                  <span className={`text-sm font-medium ${
                    selectedVenues.includes(venue.name) 
                      ? 'text-white' 
                      : darkMode ? 'text-gray-400' : 'text-gray-600'
                  } transition-colors duration-300`}>{venue.count}</span>
                </div>
              ))
            )}
          </div>
        );
      case "cities":
        return (
          <div className="space-y-2 h-64 overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <div className={`p-3 ${darkMode ? 'text-gray-400' : 'text-gray-500'} text-center transition-colors duration-300`}>No matching cities available</div>
            ) : (
              filteredOptions.map((city) => (
                <div 
                  key={city.name}
                  onClick={() => {
                    setSelectedCities(toggleArrayItem(selectedCities, city.name));
                    // Track city selection in Google Analytics
                    trackEvent('select_filter', {
                      'filter_type': 'city',
                      'filter_value': city.name,
                      'action': selectedCities.includes(city.name) ? 'deselect' : 'select'
                    });
                  }}
                  className={`p-3 rounded-lg flex items-center justify-between ${
                    selectedCities.includes(city.name)
                      ? 'bg-purple-600 text-white border border-purple-700'
                      : city.count === 0 
                        ? darkMode 
                          ? 'bg-gray-700 border border-gray-600 opacity-50 text-gray-400' 
                          : 'bg-gray-100 border border-gray-200 opacity-50 text-gray-500'
                        : darkMode 
                          ? 'bg-gray-700 border border-gray-600 text-gray-300' 
                          : 'bg-gray-50 border border-gray-200 text-gray-700'
                  } transition-colors duration-300`}
                >
                  <div className="flex items-center">
                    <div className={`w-5 h-5 rounded border flex items-center justify-center mr-3 ${
                      selectedCities.includes(city.name)
                        ? 'bg-purple-500 border-purple-500'
                        : darkMode ? 'border-gray-500' : 'border-gray-400'
                    } transition-colors duration-300`}>
                      {selectedCities.includes(city.name) && (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      )}
                    </div>
                    <span>{city.name}</span>
                  </div>
                  <span className={`text-sm font-medium ${
                    selectedCities.includes(city.name) 
                      ? 'text-white' 
                      : darkMode ? 'text-gray-400' : 'text-gray-600'
                  } transition-colors duration-300`}>{city.count}</span>
                </div>
              ))
            )}
          </div>
        );
      default:
        return null;
    }
  };

  const clearCurrentSelection = () => {
    switch (activeFilterModal) {
      case "genres":
        setSelectedGenres([]);
        break;
      case "organizers":
        setSelectedOrganizers([]);
        break;
      case "venues":
        setSelectedVenues([]);
        break;
      case "cities":
        setSelectedCities([]);
        break;
      default:
        break;
    }
  };

  const getModalTitle = () => {
    switch (activeFilterModal) {
      case "genres": return "Select Genres";
      case "organizers": return "Select Organizers";
      case "venues": return "Select Venues";
      case "cities": return "Select Cities (from venues)";
      default: return "";
    }
  };

  const getPlaceholderText = () => {
    switch (activeFilterModal) {
      case "genres": return "Search genres...";
      case "organizers": return "Search organizers...";
      case "venues": return "Search venues...";
      case "cities": return "Search cities...";
      default: return "Search...";
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      <div className={`${darkMode ? 'bg-gray-800' : 'bg-white'} rounded-xl w-full max-w-md h-[500px] flex flex-col transition-colors duration-300`}>
        <div className={`p-4 ${darkMode ? 'border-gray-700' : 'border-gray-200'} border-b flex justify-between items-center transition-colors duration-300`}>
          <h3 className={`font-bold text-lg ${darkMode ? 'text-gray-200' : 'text-gray-800'} transition-colors duration-300`}>
            {getModalTitle()}
          </h3>
          <button 
            onClick={() => setActiveFilterModal(null)}
            className={`${darkMode ? 'text-gray-400 hover:text-gray-300' : 'text-gray-500 hover:text-gray-700'} transition-colors duration-300`}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        <div className="px-4 pt-3 pb-2">
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <svg className={`h-5 w-5 ${darkMode ? 'text-gray-500' : 'text-gray-400'} transition-colors duration-300`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <input
              type="text"
              className={`block w-full pl-10 pr-3 py-2 border ${
                darkMode 
                  ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400 focus:ring-purple-600 focus:border-purple-600' 
                  : 'bg-white border-gray-300 text-gray-700 placeholder-gray-500 focus:ring-purple-500 focus:border-purple-500'
              } rounded-md leading-5 focus:outline-none focus:placeholder-gray-400 focus:ring-1 sm:text-sm transition-colors duration-300`}
              placeholder={getPlaceholderText()}
              value={modalSearchTerm}
              onChange={(e) => setModalSearchTerm(e.target.value)}
            />
            {modalSearchTerm && (
              <button
                onClick={() => setModalSearchTerm('')}
                className="absolute inset-y-0 right-0 pr-3 flex items-center"
              >
                <svg className={`h-5 w-5 ${
                  darkMode 
                    ? 'text-gray-500 hover:text-gray-400' 
                    : 'text-gray-400 hover:text-gray-600'
                } transition-colors duration-300`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>
        
        <div className="overflow-y-auto p-4 flex-grow">
          {renderModalContent()}
        </div>
        
        <div className={`p-4 ${darkMode ? 'border-gray-700' : 'border-gray-200'} border-t flex justify-between transition-colors duration-300`}>
          <button
            onClick={clearCurrentSelection}
            className={`px-4 py-2 ${
              darkMode ? 'bg-gray-700 hover:bg-gray-600 text-gray-300' : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
            } text-sm font-medium rounded-lg transition-colors duration-300`}
          >
            Clear
          </button>
          <button
            onClick={() => {
              // Track filter application in Google Analytics
              trackEvent('apply_filters', {
                'filter_type': activeFilterModal,
                'filter_count': activeFilterModal === "genres" ? selectedGenres.length :
                                activeFilterModal === "cities" ? selectedCities.length :
                                activeFilterModal === "organizers" ? selectedOrganizers.length :
                                activeFilterModal === "venues" ? selectedVenues.length : 0
              });
              setActiveFilterModal(null);
            }}
            className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 text-sm font-medium rounded-lg transition-colors duration-300"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

export default FilterModal; 