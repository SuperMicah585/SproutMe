import React, { memo, useCallback } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { trackEvent } from '../../utils/analytics';

const partPercent = (value) => {
  if (value == null || value === '') return null;
  const amount = Number(value);
  if (!Number.isFinite(amount)) return null;
  return Math.round(Math.min(Math.max(amount, 0), 1) * 100);
};

const sproutBadgeClass = (score, darkMode) => {
  if (score >= 70) {
    return darkMode ? 'bg-green-900 text-green-200' : 'bg-green-100 text-green-800';
  }
  if (score >= 45) {
    return darkMode ? 'bg-yellow-900 text-yellow-200' : 'bg-yellow-100 text-yellow-800';
  }
  return darkMode ? 'bg-gray-700 text-gray-300' : 'bg-gray-200 text-gray-700';
};

const sproutPartLabel = (parts, key, label) => {
  const percent = partPercent(parts[key]);
  return percent == null ? `${label} n/a` : `${label} ${percent}`;
};

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
  const sproutScore = Number.isFinite(Number(event.sprout_score ?? event.health))
    ? Math.round(Number(event.sprout_score ?? event.health))
    : null;
  const sproutParts = event.sprout_parts || event.health_parts || {};
  const sproutTitle = sproutScore == null
    ? ''
    : `SproutMe score ${sproutScore}: ${sproutPartLabel(sproutParts, 'artist', 'artist')}, ${sproutPartLabel(sproutParts, 'hot', 'heat')}, ${sproutPartLabel(sproutParts, 'venue', 'room')}`;
  
  // Handle favorite button click
  const handleFavoriteClick = useCallback((e) => {
    e.stopPropagation();
    onFavorite(event, index, e);
  }, [event, index, onFavorite]);
  
  return (
    <div className={`${darkMode 
      ? 'bg-gray-800 border-green-700 text-gray-100' 
      : 'bg-white border-green-200 text-black'
    } relative h-full p-4 rounded-xl shadow-md border`}>
      <div className="flex justify-between items-center mb-2">
        <h3
          className={`font-extrabold font-prosto min-w-0 flex-1 overflow-hidden pr-2 ${darkMode ? 'text-gray-100' : 'text-black'}`}
          title={eventName}
        >
          {eventUrl ? (
            <a
              href={eventUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`${eventName} (opens in a new window)`}
              onClick={() => trackEvent('click', {
                outbound: true,
                link_url: eventUrl,
                link_text: eventName,
                content_type: 'event',
              })}
              className={`flex items-center min-w-0 max-w-full ${
                darkMode ? 'text-gray-100' : 'text-black'
              }`}
            >
              <span className="truncate">{eventName}</span>
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                className="w-3.5 h-3.5 flex-shrink-0 ml-1 opacity-70"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2.5}
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                />
              </svg>
            </a>
          ) : (
            <span className="block truncate">{eventName}</span>
          )}
        </h3>
        {!readOnly && (
          <div className="relative flex-shrink-0">
            <button 
              onClick={handleFavoriteClick}
              className="focus:outline-none bg-transparent p-1 relative"
              aria-label={isFavorite ? "Remove from favorites" : "Add to favorites"}
              data-favorite={isFavorite ? "true" : "false"}
              aria-pressed={isFavorite}
            >
              <div className={`absolute inset-0 ${isFavorite ? 'opacity-100' : 'opacity-0'} w-full h-full border-2 border-dashed border-yellow-400 rounded-md`}></div>
              <div className={`w-7 h-7 flex items-center justify-center ${isFavorite 
                ? darkMode ? 'bg-green-900' : 'bg-green-50' 
                : ''
              } rounded-md`}>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" 
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
          <div className="p-1 relative flex-shrink-0">
            <div className="absolute inset-0 w-full h-full border-2 border-dashed border-yellow-400 rounded-md"></div>
            <div className={`w-7 h-7 flex items-center justify-center ${darkMode ? 'bg-green-900' : 'bg-green-50'} rounded-md`}>
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" 
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
      
      <div className={`space-y-1 text-sm ${sproutScore != null ? 'mb-1 pr-14' : 'mb-3'}`}>
        <div className="flex min-w-0">
          <span className={`font-medium w-20 flex-shrink-0 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Date:</span>
          <span className={`truncate ${darkMode ? 'text-gray-300' : 'text-gray-800'}`} title={date}>{date}</span>
        </div>
        
        <div className="flex min-w-0">
          <span className={`font-medium w-20 flex-shrink-0 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Venue:</span>
          <span className={`truncate ${darkMode ? 'text-gray-300' : 'text-gray-800'}`} title={venue}>{venue}</span>
        </div>
        
        <div className="flex items-center min-w-0">
          <span className={`font-medium w-20 flex-shrink-0 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Genre:</span>
          <div className="flex flex-nowrap gap-1 overflow-hidden min-w-0">
            {genre && genre.split(', ').map((g, i) => (
              <span key={i} className={`${darkMode 
                ? 'bg-purple-900 text-purple-200' 
                : 'bg-purple-100 text-purple-800'
              } px-2 py-0.5 rounded text-xs whitespace-nowrap flex-shrink-0`}>{g.trim()}</span>
            ))}
            {!genre && (
              <span className={darkMode ? 'text-gray-500' : 'text-gray-500'}>Not specified</span>
            )}
          </div>
        </div>

        <div className="flex min-w-0">
          <span className={`font-medium w-20 flex-shrink-0 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Tickets:</span>
          <span className={`truncate ${darkMode ? 'text-gray-300' : 'text-gray-800'}`} title={ticketInfo}>{ticketInfo}</span>
        </div>

        <div className="flex min-w-0">
          <span className={`font-medium w-20 flex-shrink-0 ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Organizer:</span>
          <span className={`truncate ${darkMode ? 'text-gray-300' : 'text-gray-800'}`} title={organizer}>{organizer}</span>
        </div>
      </div>
      {sproutScore != null && (
        <div
          className={`absolute bottom-3 right-3 min-w-[2.25rem] px-2 py-1 rounded-lg text-center text-sm font-bold ${sproutBadgeClass(sproutScore, darkMode)}`}
          title={sproutTitle}
          aria-label={sproutTitle}
        >
          {sproutScore}
        </div>
      )}
    </div>
  );
}, (prevProps, nextProps) => {
  // Custom comparison function to prevent unnecessary rerenders
  // But ALWAYS rerender if the favorite status changes
  return (
    prevProps.readOnly === nextProps.readOnly &&
    prevProps.index === nextProps.index &&
    prevProps.event.is_favorite === nextProps.event.is_favorite &&
    prevProps.event.sprout_score === nextProps.event.sprout_score &&
    prevProps.event.health === nextProps.event.health
  );
});

export default EventCard; 