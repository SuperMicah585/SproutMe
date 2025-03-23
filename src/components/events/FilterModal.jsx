import React, { useState, useEffect } from 'react';
import { useTheme } from '../../context/ThemeContext';

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
  const { darkMode } = useTheme();
  
  // Reset search term when modal changes
  useEffect(() => {
    setModalSearchTerm('');
  }, [activeFilterModal]);
  
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
    switch (activeFilterModal) {
      case "genres":
        return (
          <div className="space-y-2 max-h-96">
            {filteredOptions.length === 0 ? (
              <div className={`p-3 ${darkMode ? 'text-gray-400' : 'text-gray-500'} text-center transition-colors duration-300`}>No matching genres available</div>
            ) : (
              filteredOptions.map((genre) => (
                <div 
                  key={genre.name}
                  onClick={() => setSelectedGenres(toggleArrayItem(selectedGenres, genre.name))}
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
                  <span className={`${darkMode ? 'text-gray-400' : 'text-gray-500'} text-sm transition-colors duration-300`}>{genre.count}</span>
                </div>
              ))
            )}
          </div>
        );
      case "cities":
        return (
          <div className="space-y-2 max-h-96">
            {filteredOptions.length === 0 ? (
              <div className={`p-3 ${darkMode ? 'text-gray-400' : 'text-gray-500'} text-center transition-colors duration-300`}>No matching cities available</div>
            ) : (
              filteredOptions.map((city) => (
                <div 
                  key={city.name}
                  onClick={() => setSelectedCities(toggleArrayItem(selectedCities, city.name))}
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
                  <span className={`${darkMode ? 'text-gray-400' : 'text-gray-500'} text-sm transition-colors duration-300`}>{city.count}</span>
                </div>
              ))
            )}
          </div>
        );
      case "organizers":
        return (
          <div className="space-y-2 max-h-96">
            {filteredOptions.length === 0 ? (
              <div className={`p-3 ${darkMode ? 'text-gray-400' : 'text-gray-500'} text-center transition-colors duration-300`}>No matching organizers available</div>
            ) : (
              filteredOptions.map((organizer) => (
                <div 
                  key={organizer.name}
                  onClick={() => setSelectedOrganizers(toggleArrayItem(selectedOrganizers, organizer.name))}
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
                  <span className={`${darkMode ? 'text-gray-400' : 'text-gray-500'} text-sm transition-colors duration-300`}>{organizer.count}</span>
                </div>
              ))
            )}
          </div>
        );
      case "venues":
        return (
          <div className="space-y-2 max-h-96">
            {filteredOptions.length === 0 ? (
              <div className={`p-3 ${darkMode ? 'text-gray-400' : 'text-gray-500'} text-center transition-colors duration-300`}>No matching venues available</div>
            ) : (
              filteredOptions.map((venue) => (
                <div 
                  key={venue.name}
                  onClick={() => setSelectedVenues(toggleArrayItem(selectedVenues, venue.name))}
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
                  <span className={`${darkMode ? 'text-gray-400' : 'text-gray-500'} text-sm transition-colors duration-300`}>{venue.count}</span>
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
      <div className={`${darkMode ? 'bg-gray-800' : 'bg-white'} rounded-xl w-full max-w-md max-h-[80vh] flex flex-col transition-colors duration-300`}>
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
            className={`${
              darkMode 
                ? 'bg-gray-700 hover:bg-gray-600 text-gray-300 hover:text-white' 
                : 'text-gray-600 hover:text-gray-800'
            } font-medium py-2 px-4 rounded-lg transition-colors duration-300`}
          >
            Clear
          </button>
          <button
            onClick={() => setActiveFilterModal(null)}
            className={`${
              darkMode 
                ? 'bg-purple-700 hover:bg-purple-800' 
                : 'bg-purple-500 hover:bg-purple-600'
            } text-white font-medium py-2 px-6 rounded-lg transition-colors duration-300`}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

export default FilterModal; 