import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { parseEventDate } from '../components/events/eventUtils';
import EventCard from '../components/events/EventCard';
import { useAuth } from '../context/AuthContext';
import sproutIcon from './Components/sprout_icon.png';
import ThemeToggle from '../components/events/ThemeToggle';
import { useTheme } from '../context/ThemeContext';
import { useToast } from '../pages/Components/ToastNotification';

const FavoritedEvents = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const { phoneHash } = useParams();
  const { isLoggedIn } = useAuth();
  const { darkMode } = useTheme();
  const navigate = useNavigate();
  const toast = useToast();
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [userName, setUserName] = useState("");
  const [favoritedEvents, setFavoritedEvents] = useState([]);
  const [upcomingEvents, setUpcomingEvents] = useState([]);
  const [pastEvents, setPastEvents] = useState([]);
  const [isCopying, setIsCopying] = useState(false);
  
  // Function to copy current URL to clipboard
  const copyShareLink = async () => {
    try {
      setIsCopying(true);
      const shareUrl = window.location.href;
      
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(shareUrl);
        toast.success('Share link copied to clipboard!');
      } else {
        // Fallback method for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = shareUrl;
        textArea.style.position = 'fixed';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        
        if (successful) {
          toast.success('Share link copied to clipboard!');
        } else {
          toast.error('Failed to copy link');
        }
      }
    } catch (error) {
      console.error('Error copying to clipboard:', error);
      toast.error('Failed to copy link');
    } finally {
      setIsCopying(false);
    }
  };
  
  useEffect(() => {
    if (phoneHash) {
      fetchUserInfo();
      fetchFavoritedEvents();
    } else {
      setError("No phone hash provided");
      setLoading(false);
    }
  }, [phoneHash]);
  
  // Fetch user information based on phone hash
  const fetchUserInfo = async () => {
    try {
      const response = await fetch(`${apiUrl}/get_name`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ phone_hash: phoneHash })
      });
      
      if (!response.ok) {
        throw new Error(`Error fetching user information: ${response.status}`);
      }
      
      const data = await response.json();
      if (data && data.name) {
        setUserName(data.name || "Sprout User");
      } else {
        setUserName("Sprout User");
      }
    } catch (error) {
      console.error('Error fetching user info:', error);
      setUserName("Sprout User");
    }
  };
  
  // Fetch favorited events using the phone hash
  const fetchFavoritedEvents = async () => {
    try {
      setLoading(true);
      
      const response = await fetch(`${apiUrl}/favorite_events_by_hash?phone_hash=${phoneHash}`);
      
      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }
      
      const data = await response.json();
      console.log('Favorited events data:', data);
      
      if (data.success && Array.isArray(data.data)) {
        // Process the events to ensure they have all required fields
        const events = data.data.map(event => {
          // Add default values for any missing fields
          return {
            // Copy all existing properties
            ...event,
            // Ensure these fields exist with defaults if they don't
            event_name: event.event_name || "Unnamed Event",
            venue: event.venue || "Unknown Venue",
            date: event.date || "Unknown Date",
            raw_date: event.raw_date || "",
            organizer: event.organizer || "",
            ticket_info: event.ticket_info || "Not specified",
            genre: event.genre || "",
            event_url: event.event_url || "",
            is_favorite: true  // Since these are all favorited events
          };
        });
        
        console.log('Processed events with defaults:', events);
        setFavoritedEvents(events);
        
        // Split events into upcoming and past
        const currentDate = new Date();
        currentDate.setHours(0, 0, 0, 0); // Normalize to start of day
        
        const upcoming = [];
        const past = [];
        
        events.forEach(event => {
          // Only process events with valid raw_date
          if (event.raw_date) {
            const eventDate = parseEventDate(event.raw_date);
            if (eventDate >= currentDate) {
              upcoming.push(event);
            } else {
              past.push(event);
            }
          } else {
            // If no raw_date, default to upcoming
            upcoming.push(event);
          }
        });
        
        // Sort upcoming events by date (ascending)
        upcoming.sort((a, b) => {
          if (!a.raw_date) return 1;
          if (!b.raw_date) return -1;
          const dateA = parseEventDate(a.raw_date);
          const dateB = parseEventDate(b.raw_date);
          return dateA - dateB;
        });
        
        // Sort past events by date (descending)
        past.sort((a, b) => {
          if (!a.raw_date) return 1;
          if (!b.raw_date) return -1;
          const dateA = parseEventDate(a.raw_date);
          const dateB = parseEventDate(b.raw_date);
          return dateB - dateA;
        });
        
        setUpcomingEvents(upcoming);
        setPastEvents(past);
      } else {
        setFavoritedEvents([]);
        setUpcomingEvents([]);
        setPastEvents([]);
      }
      
      setLoading(false);
    } catch (error) {
      console.error('Error fetching favorited events:', error);
      setError('Error loading favorited events. Please try again later.');
      setLoading(false);
    }
  };
  
  if (loading) {
    return (
      <div className={`flex flex-col items-center justify-center min-h-screen ${
        darkMode ? 'bg-gray-900' : 'bg-gray-50'
      } p-4 transition-colors duration-300`}>
        <div className="w-12 h-12 border-4 border-green-500 border-t-transparent rounded-full animate-spin mb-4"></div>
        <p className={`${darkMode ? 'text-gray-300' : 'text-gray-600'} transition-colors duration-300`}>Loading favorites...</p>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className={`flex flex-col items-center justify-center min-h-screen ${
        darkMode ? 'bg-gray-900' : 'bg-gray-50'
      } p-4 transition-colors duration-300`}>
        <div className={`${
          darkMode ? 'bg-red-900 border-red-800 text-red-200' : 'bg-red-100 border-red-300 text-red-700'
        } border-2 p-4 rounded-lg max-w-md w-full transition-colors duration-300`}>
          <p className="font-bold">Error</p>
          <p>{error}</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className={`w-screen min-h-screen flex flex-col items-center ${
      darkMode ? 'bg-gray-900' : 'bg-gray-50'
    } overflow-y-auto pb-8 transition-colors duration-300`}>
      {/* Header */}
      <div className={`w-full ${
        darkMode ? 'bg-gray-800 shadow-gray-900' : 'bg-white shadow-gray-200'
      } shadow-md p-4 flex flex-col sm:flex-row justify-between items-center mb-6 transition-colors duration-300`}>
        <div className="flex items-center mb-3 sm:mb-0">
          <img src={sproutIcon} alt="Sprout Logo" className="h-8 w-8 mr-2" />
          <span className={`font-bold text-xl ${
            darkMode ? 'text-green-400' : 'text-green-600'
          } transition-colors duration-300`}>SproutMe</span>
        </div>
        <div className="flex items-center space-x-2 w-full sm:w-auto justify-center sm:justify-end">
          {/* Share Button */}
          <button
            onClick={copyShareLink}
            disabled={isCopying}
            className={`${
              darkMode 
                ? 'bg-blue-700 hover:bg-blue-600' 
                : 'bg-blue-500 hover:bg-blue-600'
            } text-white font-medium py-2 px-3 sm:px-4 rounded-lg transition-colors flex items-center text-sm sm:text-base`}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1 sm:mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
            </svg>
            {isCopying ? 'Copying...' : 'Share'}
          </button>
          
          {/* Back to Events Button */}
          <button
            onClick={() => navigate('/events')}
            className={`${
              darkMode ? 'bg-green-700 hover:bg-green-600' : 'bg-green-500 hover:bg-green-600'
            } text-white font-medium py-2 px-3 sm:px-4 rounded-lg transition-colors text-sm sm:text-base`}
          >
            Back
          </button>
          <ThemeToggle />
        </div>
      </div>
      
      <div className="w-full max-w-5xl px-4">
        <h1 className={`text-2xl font-bold text-center mb-8 ${
          darkMode ? 'text-gray-100' : 'text-gray-800'
        } transition-colors duration-300`}>
          {userName}'s Events
        </h1>
        
        {favoritedEvents.length === 0 ? (
          <div className={`${
            darkMode ? 'bg-yellow-900 border-yellow-800 text-yellow-200' : 'bg-yellow-50 border-yellow-300 text-yellow-700'
          } border-2 p-6 rounded-xl text-center transition-colors duration-300`}>
            <p className="text-lg font-medium">No favorited events found</p>
            <p className="mt-2">This user hasn't favorited any events yet.</p>
          </div>
        ) : (
          <>
            {/* Upcoming Events Section */}
            <div className="mb-10">
              <h2 className={`text-xl font-semibold mb-4 ${
                darkMode ? 'text-green-400 border-green-700' : 'text-green-600 border-green-200'
              } border-b-2 pb-2 transition-colors duration-300`}>
                Upcoming Events ({upcomingEvents.length})
              </h2>
              
              {upcomingEvents.length === 0 ? (
                <div className={`${
                  darkMode ? 'bg-gray-800 border-gray-700 text-gray-400' : 'bg-gray-50 border-gray-200 text-gray-500'
                } border p-4 rounded-lg text-center transition-colors duration-300`}>
                  No upcoming events favorited
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {upcomingEvents.map((event, index) => (
                    <EventCard 
                      key={index} 
                      event={event} 
                      index={index}
                      onFavorite={() => {}} // No actions available in shared view
                      readOnly={true}
                    />
                  ))}
                </div>
              )}
            </div>
            
            {/* Past Events Section */}
            <div>
              <h2 className={`text-xl font-semibold mb-4 ${
                darkMode ? 'text-purple-400 border-purple-700' : 'text-purple-600 border-purple-200'
              } border-b-2 pb-2 transition-colors duration-300`}>
                Past Events ({pastEvents.length})
              </h2>
              
              {pastEvents.length === 0 ? (
                <div className={`${
                  darkMode ? 'bg-gray-800 border-gray-700 text-gray-400' : 'bg-gray-50 border-gray-200 text-gray-500'
                } border p-4 rounded-lg text-center transition-colors duration-300`}>
                  No past events favorited
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {pastEvents.map((event, index) => (
                    <EventCard 
                      key={index} 
                      event={event} 
                      index={index}
                      onFavorite={() => {}} // No actions available in shared view
                      readOnly={true}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default FavoritedEvents; 