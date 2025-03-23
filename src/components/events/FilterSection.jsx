import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { useToast } from '../../pages/Components/ToastNotification';

const FilterSection = ({
  showFilters,
  setShowFilters,
  filterCount,
  resetFilters,
  dateRange,
  setDateRange,
  searchTerm,
  setSearchTerm,
  priceSort,
  setPriceSort,
  selectedGenres,
  selectedOrganizers,
  selectedVenues,
  selectedCities,
  openFilterModal,
  events,
  filteredEvents,
  showStarredOnly,
  setShowStarredOnly,
  isLoggedIn,
  sharing,
  handleShareFavorites
}) => {
  const navigate = useNavigate();
  const { isLoggedIn: authIsLoggedIn, logout } = useAuth();
  const { darkMode } = useTheme();
  const toast = useToast();
  
  return (
    <>
      {/* Mobile-Friendly Filters */}
      {showFilters && (
        <div className="w-full max-w-5xl px-4 mb-6">
          {/* Top filters that are always visible */}
          <div className={`${
            darkMode 
              ? 'bg-gray-800 border-green-700 text-gray-200' 
              : 'bg-white border-green-200 text-black'
          } rounded-xl shadow-md p-4 mb-2 border transition-colors duration-300`}>
            {/* Starred Events Filter */}
            {isLoggedIn && (
              <div className="mb-4">
                <label className={`flex items-center space-x-2 cursor-pointer ${
                  darkMode 
                    ? 'text-gray-200 bg-gray-800 hover:bg-gray-700' 
                    : 'text-black bg-white hover:bg-gray-50'
                } p-2 rounded-md transition-colors duration-300`}>
                  <input
                    type="checkbox"
                    checked={showStarredOnly}
                    onChange={() => {
                      console.log('Toggling starred only filter:', !showStarredOnly);
                      // Check if we have any favorited events first
                      const hasFavorites = events.some(event => event.is_favorite === true);
                      
                      if (!showStarredOnly && !hasFavorites) {
                        // Show toast notification if there are no favorites
                        toast.warning('No favorited events to display. Click the star icon on events you like to save them as favorites.');
                        return;
                      }
                      
                      setShowStarredOnly(!showStarredOnly);
                    }}
                    className="form-checkbox h-5 w-5 text-yellow-300 rounded border-gray-300 focus:ring-yellow-300"
                  />
                  <span className={`${
                    darkMode ? 'text-gray-300' : 'text-gray-700'
                  } font-medium flex items-center transition-colors duration-300`}>
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-yellow-300 mr-1" viewBox="0 0 20 20" fill="currentColor">
                      <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118l-2.799-2.034c-.784-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                    </svg>
                    Show Favorited Events Only
                  </span>
                </label>
                
                {/* Share Favorites Button in Filter Section (visible when showStarredOnly is true) */}
                {showStarredOnly && (
                  <div className="mt-2 sm:hidden">
                    <button
                      onClick={handleShareFavorites}
                      className={`${
                        darkMode 
                          ? 'bg-blue-800 hover:bg-blue-700 text-blue-100' 
                          : 'bg-blue-500 hover:bg-blue-600 text-white'
                      } font-medium py-2 px-3 text-sm rounded-lg transition-colors w-full flex items-center justify-center`}
                      disabled={sharing}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                      </svg>
                      {sharing ? 'Generating Share Link...' : 'Share My Favorites'}
                    </button>
                  </div>
                )}
              </div>
            )}
            
            {/* Date Range Filter */}
            <div className="mb-4">
              <label className={`block ${
                darkMode ? 'text-gray-300' : 'text-gray-700'
              } text-sm font-bold mb-2 transition-colors duration-300`}>Date Range</label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className={`text-xs ${
                    darkMode ? 'text-gray-400' : 'text-gray-500'
                  } mb-1 transition-colors duration-300`}>Start Date</div>
                  <div className="relative">
                    <input
                      type="date"
                      className={`border rounded-md p-2 w-full ${
                        darkMode 
                          ? 'bg-gray-700 border-gray-600 text-gray-200' 
                          : 'bg-white border-gray-300 text-black'
                      } transition-colors duration-300`}
                      value={dateRange.start}
                      onChange={(e) => setDateRange({ ...dateRange, start: e.target.value })}
                    />
                  </div>
                </div>
                <div>
                  <div className={`text-xs ${
                    darkMode ? 'text-gray-400' : 'text-gray-500'
                  } mb-1 transition-colors duration-300`}>End Date</div>
                  <div className="relative">
                    <input
                      type="date"
                      className={`border rounded-md p-2 w-full ${
                        darkMode 
                          ? 'bg-gray-700 border-gray-600 text-gray-200' 
                          : 'bg-white border-gray-300 text-black'
                      } transition-colors duration-300`}
                      value={dateRange.end}
                      onChange={(e) => setDateRange({ ...dateRange, end: e.target.value })}
                    />
                  </div>
                </div>
              </div>
            </div>
            
            {/* Event Name Search */}
            <div className="mb-4">
              <label className={`block ${
                darkMode ? 'text-gray-300' : 'text-gray-700'
              } text-sm font-bold mb-2 transition-colors duration-300`}>
                Search Events
              </label>
              <div className="relative">
                <input
                  type="text"
                  placeholder="Enter event name..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className={`border rounded-md p-2 pl-10 w-full ${
                    darkMode 
                      ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' 
                      : 'bg-white border-gray-300 text-black placeholder-gray-500'
                  } transition-colors duration-300`}
                />
                <div className="absolute inset-y-0 left-0 flex items-center pl-3">
                  <svg xmlns="http://www.w3.org/2000/svg" className={`h-5 w-5 ${
                    darkMode ? 'text-gray-400' : 'text-gray-500'
                  } transition-colors duration-300`} viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
                  </svg>
                </div>
              </div>
            </div>
            
            {/* Price Sort */}
            <div className="mb-4">
              <label className={`block ${
                darkMode ? 'text-gray-300' : 'text-gray-700'
              } text-sm font-bold mb-2 transition-colors duration-300`}>
                Price Sort
              </label>
              <div className="flex space-x-4">
                <label className={`flex items-center space-x-2 cursor-pointer ${
                  darkMode ? 'text-gray-300' : 'text-gray-700'
                } transition-colors duration-300`}>
                  <input
                    type="radio"
                    value="none"
                    checked={priceSort === "none"}
                    onChange={() => setPriceSort("none")}
                    className="form-radio h-4 w-4 text-green-500"
                  />
                  <span>None</span>
                </label>
                <label className={`flex items-center space-x-2 cursor-pointer ${
                  darkMode ? 'text-gray-300' : 'text-gray-700'
                } transition-colors duration-300`}>
                  <input
                    type="radio"
                    value="asc"
                    checked={priceSort === "asc"}
                    onChange={() => setPriceSort("asc")}
                    className="form-radio h-4 w-4 text-green-500"
                  />
                  <span>Low to High</span>
                </label>
                <label className={`flex items-center space-x-2 cursor-pointer ${
                  darkMode ? 'text-gray-300' : 'text-gray-700'
                } transition-colors duration-300`}>
                  <input
                    type="radio"
                    value="desc"
                    checked={priceSort === "desc"}
                    onChange={() => setPriceSort("desc")}
                    className="form-radio h-4 w-4 text-green-500"
                  />
                  <span>High to Low</span>
                </label>
              </div>
            </div>
            
            {/* Filter Category Buttons */}
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => openFilterModal("genres")}
                className={`px-3 py-2 rounded-lg ${
                  darkMode
                    ? 'bg-gray-700 hover:bg-gray-600 text-gray-200 border border-gray-600'
                    : 'bg-gray-50 hover:bg-gray-100 text-gray-800 border border-gray-200'
                } shadow-sm flex justify-between items-center transition-colors duration-300`}
              >
                <span>Genres</span>
                <div className="flex items-center">
                  {selectedGenres.length > 0 && (
                    <span className={`${
                      darkMode ? 'bg-green-700 text-green-200' : 'bg-green-100 text-green-800'
                    } px-2 py-0.5 rounded-full text-xs mr-1 transition-colors duration-300`}>
                      {selectedGenres.length}
                    </span>
                  )}
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </div>
              </button>
              
              <button
                onClick={() => openFilterModal("organizers")}
                className={`px-3 py-2 rounded-lg ${
                  darkMode
                    ? 'bg-gray-700 hover:bg-gray-600 text-gray-200 border border-gray-600'
                    : 'bg-gray-50 hover:bg-gray-100 text-gray-800 border border-gray-200'
                } shadow-sm flex justify-between items-center transition-colors duration-300`}
              >
                <span>Organizers</span>
                <div className="flex items-center">
                  {selectedOrganizers.length > 0 && (
                    <span className={`${
                      darkMode ? 'bg-green-700 text-green-200' : 'bg-green-100 text-green-800'
                    } px-2 py-0.5 rounded-full text-xs mr-1 transition-colors duration-300`}>
                      {selectedOrganizers.length}
                    </span>
                  )}
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </div>
              </button>
              
              <button
                onClick={() => openFilterModal("venues")}
                className={`px-3 py-2 rounded-lg ${
                  darkMode
                    ? 'bg-gray-700 hover:bg-gray-600 text-gray-200 border border-gray-600'
                    : 'bg-gray-50 hover:bg-gray-100 text-gray-800 border border-gray-200'
                } shadow-sm flex justify-between items-center transition-colors duration-300`}
              >
                <span>Venues</span>
                <div className="flex items-center">
                  {selectedVenues.length > 0 && (
                    <span className={`${
                      darkMode ? 'bg-green-700 text-green-200' : 'bg-green-100 text-green-800'
                    } px-2 py-0.5 rounded-full text-xs mr-1 transition-colors duration-300`}>
                      {selectedVenues.length}
                    </span>
                  )}
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </div>
              </button>
              
              <button
                onClick={() => openFilterModal("cities")}
                className={`px-3 py-2 rounded-lg ${
                  darkMode
                    ? 'bg-gray-700 hover:bg-gray-600 text-gray-200 border border-gray-600'
                    : 'bg-gray-50 hover:bg-gray-100 text-gray-800 border border-gray-200'
                } shadow-sm flex justify-between items-center transition-colors duration-300`}
              >
                <span>Cities</span>
                <div className="flex items-center">
                  {selectedCities.length > 0 && (
                    <span className={`${
                      darkMode ? 'bg-green-700 text-green-200' : 'bg-green-100 text-green-800'
                    } px-2 py-0.5 rounded-full text-xs mr-1 transition-colors duration-300`}>
                      {selectedCities.length}
                    </span>
                  )}
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </div>
              </button>
            </div>
            
            {/* Reset Filters Button */}
            {filterCount > 0 && (
              <div className="mt-4 flex justify-center">
                <button
                  onClick={resetFilters}
                  className={`px-4 py-2 rounded-lg ${
                    darkMode
                      ? 'bg-red-800 hover:bg-red-700 text-white'
                      : 'bg-red-500 hover:bg-red-600 text-white'
                  } transition-colors duration-300`}
                >
                  Reset All Filters
                </button>
              </div>
            )}
            
            {/* Event Counts */}
            <div className={`mt-4 text-center text-sm ${
              darkMode ? 'text-gray-400' : 'text-gray-500'
            } transition-colors duration-300`}>
              Showing {filteredEvents.length} of {events.length} events
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default FilterSection; 