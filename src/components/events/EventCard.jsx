import React, { memo, useCallback } from 'react';
import { useTheme } from '../../context/ThemeContext';

const EventCard = memo(({ event, index, onFavorite, readOnly = false }) => {
  const { darkMode } = useTheme();
  
  // Safety check for undefined event
  if (!event) {
    return (
      <div className={`${darkMode ? 'bg-gray-800 border-red-900 text-red-400' : 'bg-white border-red-200 text-red-500'} p-4 rounded-xl shadow-md border`}>
        <p>Error: Event data is missing</p>
      </div>
    );
  }
  
  // Safely trim strings only if they exist
  const safelyTrim = (str) => (str && typeof str === 'string') ? str.trim() : str;
  const eventName = safelyTrim(event.event_name) || 'Unnamed Event';
  const venue = safelyTrim(event.venue) || 'Unknown Venue';
  const date = safelyTrim(event.date) || 'Unknown Date';
  const ticketInfo = safelyTrim(event.ticket_info) || 'N/A';
  const organizer = safelyTrim(event.organizer) || 'N/A';
  const genre = safelyTrim(event.genre) || '';
  const eventUrl = safelyTrim(event.event_url) || '';
  const isFavorite = !!event.is_favorite;
  
  // Handle favorite button click
  const handleFavoriteClick = useCallback((e) => {
    e.stopPropagation();
    onFavorite(event, index, e);
  }, [event, index, onFavorite]);
  
  return (
    <div className={`${darkMode 
      ? 'bg-gray-800 border-green-700 hover:border-green-500 text-gray-100' 
      : 'bg-white border-green-200 hover:border-green-400 text-black'
    } p-4 rounded-xl shadow-md border transition-all hover:shadow-lg`}>
      <div className="flex justify-between items-start mb-2">
        <h3 className={`font-extrabold font-prosto ${darkMode ? 'text-gray-100' : 'text-black'}`}>{eventName}</h3>
        {!readOnly && (
          <div className="group relative">
            <button 
              onClick={handleFavoriteClick}
              className="transition-all focus:outline-none bg-transparent p-1 relative"
              aria-label={isFavorite ? "Remove from favorites" : "Add to favorites"}
              data-favorite={isFavorite ? "true" : "false"}
              aria-pressed={isFavorite}
            >
              <div className={`absolute inset-0 ${isFavorite ? 'opacity-100' : 'opacity-0'} w-full h-full border-2 border-dashed border-yellow-400 rounded-md transition-opacity`}></div>
              <div className={`w-7 h-7 flex items-center justify-center ${isFavorite 
                ? darkMode ? 'bg-green-900' : 'bg-green-50' 
                : ''
              } rounded-md transition-all duration-300 ease-in-out transform hover:scale-125 hover:shadow-lg`}>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 transition-all duration-300 ease-in-out transform hover:rotate-45" 
                  fill={isFavorite ? "#FBBF24" : "none"} 
                  viewBox="0 0 24 24" 
                  stroke="#FBBF24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                </svg>
              </div>
            </button>
          </div>
        )}
        {readOnly && isFavorite && (
          <div className="p-1 relative group">
            <div className="absolute inset-0 w-full h-full border-2 border-dashed border-yellow-400 rounded-md"></div>
            <div className={`w-7 h-7 flex items-center justify-center ${darkMode ? 'bg-green-900' : 'bg-green-50'} rounded-md transition-all duration-300 ease-in-out transform hover:scale-125 hover:shadow-lg`}>
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 transition-all duration-300 ease-in-out transform hover:rotate-45" 
                fill="#FBBF24" 
                viewBox="0 0 24 24" 
                stroke="#FBBF24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
              </svg>
            </div>
          </div>
        )}
      </div>
      
      <div className="space-y-1 mb-3 text-sm">
        <div className="flex">
          <span className={`font-medium w-20 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Date:</span>
          <span className={darkMode ? 'text-gray-300' : 'text-gray-800'}>{date}</span>
        </div>
        
        <div className="flex">
          <span className={`font-medium w-20 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Venue:</span>
          <span className={darkMode ? 'text-gray-300' : 'text-gray-800'}>{venue}</span>
        </div>
        
        <div className="flex flex-wrap items-center">
          <span className={`font-medium w-20 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Genre:</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {genre && genre.split(', ').map((g, i) => (
              <span key={i} className={`${darkMode 
                ? 'bg-purple-900 text-purple-200' 
                : 'bg-purple-100 text-purple-800'
              } px-2 py-0.5 rounded text-xs`}>{g.trim()}</span>
            ))}
            {!genre && (
              <span className={darkMode ? 'text-gray-500' : 'text-gray-500'}>Not specified</span>
            )}
          </div>
        </div>

        <div className="flex">
          <span className={`font-medium w-20 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Tickets:</span>
          <span className={darkMode ? 'text-gray-300' : 'text-gray-800'}>{ticketInfo}</span>
        </div>

        <div className="flex">
          <span className={`font-medium w-20 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Organizer:</span>
          <span className={darkMode ? 'text-gray-300' : 'text-gray-800'}>{organizer}</span>
        </div>
      </div>
      
      {eventUrl && (
        <a
          href={eventUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={`block w-full text-center ${darkMode 
            ? 'bg-green-700 hover:bg-green-600' 
            : 'bg-green-500 hover:bg-green-600'
          } text-white font-medium py-2 rounded-lg transition-colors`}
        >
          View Event
        </a>
      )}
    </div>
  );
}, (prevProps, nextProps) => {
  // Custom comparison function to prevent unnecessary rerenders
  // But ALWAYS rerender if the favorite status changes
  return (
    prevProps.readOnly === nextProps.readOnly &&
    prevProps.index === nextProps.index &&
    prevProps.event.is_favorite === nextProps.event.is_favorite
  );
});

export default EventCard; 