import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import EventList from "../components/events/EventList";
import FilterSection from "../components/events/FilterSection";
import FilterModal from "../components/events/FilterModal";
import ThemeToggle from "../components/events/ThemeToggle";
import ContactFooter from "../components/events/ContactFooter";
import { 
  hashPhoneNumber, 
  verifyPhoneHash, 
  parseEventDate, 
  extractPrice, 
  toggleArrayItem,
  extractCityFromVenue
} from "../components/events/eventUtils";
import sproutIcon from './Components/sprout_icon.png';
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useToast } from "./Components/ToastNotification";
import { trackEvent, trackPageView, verifyAnalytics } from "../utils/analytics";

const EventsPage = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const { phoneHash: urlPhoneHash } = useParams();
  const { isLoggedIn, phoneHash: authPhoneHash, userName, phoneNumber: authPhoneNumber, getPhoneHash, logout } = useAuth();
  const { darkMode } = useTheme();
  const toast = useToast();
  const navigate = useNavigate();
  
  // Track page view when component mounts
  useEffect(() => {
    // Track page view
    trackPageView('/events', 'Events Page');
  }, []);
  
  // Refs to prevent unnecessary refetching
  const hasLoadedInitialData = useRef(false);
  const prevUrlPhoneHash = useRef(urlPhoneHash);
  const prevAuthPhoneHash = useRef(authPhoneHash);
  
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actualPhoneNumber, setActualPhoneNumber] = useState(null);
  const [name, setName] = useState("");

  // Pagination states
  const [currentPage, setCurrentPage] = useState(1);
  const [eventsPerPage] = useState(50); // Reduced from 100 to 50 for better performance

  // Filter states
  const [dateRange, setDateRange] = useState({ start: "", end: "" });
  const [selectedGenres, setSelectedGenres] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedOrganizers, setSelectedOrganizers] = useState([]);
  const [selectedVenues, setSelectedVenues] = useState([]);
  const [priceSort, setPriceSort] = useState("none"); // "none", "asc", "desc"
  const [selectedCities, setSelectedCities] = useState([]);
  const [showStarredOnly, setShowStarredOnly] = useState(false);
  
  // For dropdown filters - only populate when needed
  const [availableGenres, setAvailableGenres] = useState([]);
  const [availableOrganizers, setAvailableOrganizers] = useState([]);
  const [availableVenues, setAvailableVenues] = useState([]);
  const [availableCities, setAvailableCities] = useState([]);
  
  // Mobile UI states
  const [showFilters, setShowFilters] = useState(true);
  const [activeFilterModal, setActiveFilterModal] = useState("cities"); // Set to "cities" by default
  const [filterCount, setFilterCount] = useState(0);
  const [sharing, setSharing] = useState(false);
  const [showLoginTooltip, setShowLoginTooltip] = useState(true);

  useEffect(() => {
    // Only run once on mount or when phone hash changes
    const fetchData = async () => {
      if (!hasLoadedInitialData.current) {
        await fetchEvents();
        hasLoadedInitialData.current = true;
      } else if (
        urlPhoneHash !== prevUrlPhoneHash.current || 
        authPhoneHash !== prevAuthPhoneHash.current
      ) {
        await fetchEvents();
      }
      
      // Update previous hash values regardless
      prevUrlPhoneHash.current = urlPhoneHash;
      prevAuthPhoneHash.current = authPhoneHash;
    };
    
    fetchData();
    
    // Using an empty dependency array ensures this only runs once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Use useMemo to compute filtered events instead of storing in state
  const filteredEvents = useMemo(() => {
    let result = events;
    
    // Apply date range filter
    if (dateRange.start) {
      const startDate = new Date(dateRange.start);
      result = result.filter(event => {
        const eventDate = parseEventDate(event.raw_date);
        return eventDate >= startDate;
      });
    }
    
    if (dateRange.end) {
      const endDate = new Date(dateRange.end);
      result = result.filter(event => {
        const eventDate = parseEventDate(event.raw_date);
        return eventDate <= endDate;
      });
    }
    
    // Apply search term filter
    if (searchTerm.trim() !== '') {
      const term = searchTerm.trim().toLowerCase();
      result = result.filter(event => 
        event.event_name.toLowerCase().includes(term)
      );
    }
    
    // Apply genre filter
    if (selectedGenres.length > 0) {
      result = result.filter(event => {
        // Handle empty genre case
        if (!event.genre || !event.genre.trim()) {
          return selectedGenres.includes('None');
        }
        
        const eventGenres = event.genre.split(', ').map(g => g.trim());
        return selectedGenres.some(genre => eventGenres.includes(genre));
      });
    }
    
    // Apply city filter
    if (selectedCities.length > 0) {
      result = result.filter(event => {
        const city = extractCityFromVenue(event.venue);
        return city && selectedCities.includes(city);
      });
    }
    
    // Apply organizer filter
    if (selectedOrganizers.length > 0) {
      result = result.filter(event => 
        selectedOrganizers.includes(event.organizer.trim())
      );
    }
    
    // Apply venue filter
    if (selectedVenues.length > 0) {
      result = result.filter(event => 
        selectedVenues.includes(event.venue.trim())
      );
    }
    
    // Apply starred events filter
    if (showStarredOnly) {
      result = result.filter(event => event.is_favorite === true);
    }
    
    // Apply price sorting
    if (priceSort !== "none") {
      return [...result].sort((a, b) => {
        const priceA = extractPrice(a.ticket_info);
        const priceB = extractPrice(b.ticket_info);
        return priceSort === "asc" ? priceA - priceB : priceB - priceA;
      });
    }
    
    return result;
  }, [events, dateRange, selectedGenres, searchTerm, selectedOrganizers, selectedVenues, selectedCities, priceSort, showStarredOnly]);

  // Memoize displayed events for current page
  const displayedEvents = useMemo(() => {
    const indexOfLastEvent = currentPage * eventsPerPage;
    const indexOfFirstEvent = indexOfLastEvent - eventsPerPage;
    return filteredEvents.slice(indexOfFirstEvent, indexOfLastEvent);
  }, [filteredEvents, currentPage, eventsPerPage]);

  // Memoize the filter counts calculation
  const calculateFilteredEventsForCounts = useCallback((excludeFilterType) => {
    let result = events;
    
    // Apply date range filter
    if (excludeFilterType !== 'date' && (dateRange.start || dateRange.end)) {
      if (dateRange.start) {
        const startDate = new Date(dateRange.start);
        result = result.filter(event => {
          const eventDate = parseEventDate(event.raw_date);
          return eventDate >= startDate;
        });
      }
      
      if (dateRange.end) {
        const endDate = new Date(dateRange.end);
        result = result.filter(event => {
          const eventDate = parseEventDate(event.raw_date);
          return eventDate <= endDate;
        });
      }
    }
    
    // Apply search term filter
    if (excludeFilterType !== 'search' && searchTerm.trim() !== '') {
      const term = searchTerm.trim().toLowerCase();
      result = result.filter(event => 
        event.event_name.toLowerCase().includes(term)
      );
    }
    
    // Apply genre filter
    if (excludeFilterType !== 'genres' && selectedGenres.length > 0) {
      result = result.filter(event => {
        // Handle empty genre case
        if (!event.genre || !event.genre.trim()) {
          return selectedGenres.includes('None');
        }
        
        const eventGenres = event.genre.split(', ').map(g => g.trim());
        return selectedGenres.some(genre => eventGenres.includes(genre));
      });
    }
    
    // Apply city filter
    if (excludeFilterType !== 'cities' && selectedCities.length > 0) {
      result = result.filter(event => {
        const city = extractCityFromVenue(event.venue);
        return city && selectedCities.includes(city);
      });
    }
    
    // Apply organizer filter
    if (excludeFilterType !== 'organizers' && selectedOrganizers.length > 0) {
      result = result.filter(event => 
        selectedOrganizers.includes(event.organizer.trim())
      );
    }
    
    // Apply venue filter
    if (excludeFilterType !== 'venues' && selectedVenues.length > 0) {
      result = result.filter(event => 
        selectedVenues.includes(event.venue.trim())
      );
    }
    
    // Apply starred filter
    if (excludeFilterType !== 'starred' && showStarredOnly) {
      result = result.filter(event => event.is_favorite === true);
    }
    
    return result;
  }, [events, dateRange, selectedGenres, searchTerm, selectedOrganizers, selectedVenues, selectedCities, showStarredOnly]);

  // Memoize filtered events for counts to prevent recreation
  const filteredEventsForCounts = useMemo(() => {
    if (filterCount === 0 || !activeFilterModal) {
      return events;
    }
    
    // Skip the current filter type when calculating available options
    return calculateFilteredEventsForCounts(activeFilterModal);
  }, [events, activeFilterModal, filterCount, dateRange, selectedGenres, searchTerm, selectedOrganizers, selectedVenues, selectedCities, priceSort, showStarredOnly, calculateFilteredEventsForCounts]);

  // Update pagination when filtered events change
  useEffect(() => {
    // Reset to first page when filters change
    setCurrentPage(1);
  }, [filteredEvents.length]);

  // Extract filter options only when modal is opened
  useEffect(() => {
    if (activeFilterModal && filteredEventsForCounts.length > 0) {
      extractFilterOptions(filteredEventsForCounts);
    }
  }, [activeFilterModal, filteredEventsForCounts]);

  // Extract unique filter options with counts from the provided events array
  const extractFilterOptions = useCallback((eventsArray) => {
    if (!eventsArray || eventsArray.length === 0) return;
  
    // Extract unique genres with counts
    if (activeFilterModal === 'genres') {
    const genreCounts = {};
      eventsArray.forEach(event => {
        const eventGenres = event.genre && event.genre.trim() ? 
          event.genre.split(', ').map(g => g.trim()) : 
          ['None'];
        
        eventGenres.forEach(genre => {
        genreCounts[genre] = (genreCounts[genre] || 0) + 1;
      });
    });
    const genres = Object.entries(genreCounts)
      .map(([genre, count]) => ({ name: genre, count }))
      .sort((a, b) => b.count - a.count);
      setAvailableGenres(genres);
    }
    
    // Extract unique organizers with counts
    else if (activeFilterModal === 'organizers') {
    const organizerCounts = {};
      eventsArray.forEach(event => {
      const organizer = event.organizer.trim();
      if (organizer) {
        organizerCounts[organizer] = (organizerCounts[organizer] || 0) + 1;
      }
    });
    const organizers = Object.entries(organizerCounts)
      .map(([organizer, count]) => ({ name: organizer, count }))
      .sort((a, b) => b.count - a.count);
      setAvailableOrganizers(organizers);
    }
    
    // Extract unique venues with counts
    else if (activeFilterModal === 'venues') {
    const venueCounts = {};
      eventsArray.forEach(event => {
      const venue = event.venue.trim();
      venueCounts[venue] = (venueCounts[venue] || 0) + 1;
    });
    const venues = Object.entries(venueCounts)
      .map(([venue, count]) => ({ name: venue, count }))
      .sort((a, b) => b.count - a.count);
      setAvailableVenues(venues);
    }
    
    // Extract cities from venue strings with counts
    else if (activeFilterModal === 'cities') {
    const cityCounts = {};
      eventsArray.forEach(event => {
        const city = extractCityFromVenue(event.venue);
      if (city) {
        cityCounts[city] = (cityCounts[city] || 0) + 1;
      }
    });
    const cities = Object.entries(cityCounts)
      .map(([city, count]) => ({ name: city, count }))
      .sort((a, b) => b.count - a.count);
    setAvailableCities(cities);
  }
  }, [activeFilterModal]);

  // Update filter count for badge
  useEffect(() => {
    let count = 0;
    if (dateRange.start || dateRange.end) count++;
    if (selectedGenres.length) count++;
    if (searchTerm) count++;
    if (selectedOrganizers.length) count++;
    if (selectedVenues.length) count++;
    if (selectedCities.length) count++;
    if (priceSort !== "none") count++;
    if (showStarredOnly) count++;
    
    setFilterCount(count);
  }, [dateRange, selectedGenres, searchTerm, selectedOrganizers, selectedVenues, selectedCities, priceSort, showStarredOnly]);

  // Track filter changes
  useEffect(() => {
    // Don't track on initial render
    if (hasLoadedInitialData.current) {
      trackEvent('filter_change', {
        'filter_count': filterCount,
        'active_filters': {
          'date_range': !!dateRange.start || !!dateRange.end,
          'genres': selectedGenres.length > 0,
          'search': searchTerm.trim() !== '',
          'organizers': selectedOrganizers.length > 0,
          'venues': selectedVenues.length > 0,
          'cities': selectedCities.length > 0,
          'price_sort': priceSort !== 'none',
          'starred_only': showStarredOnly
        }
      });
    }
  }, [
    dateRange, 
    selectedGenres, 
    searchTerm, 
    selectedOrganizers, 
    selectedVenues, 
    selectedCities, 
    priceSort, 
    showStarredOnly,
    filterCount
  ]);

  // Check if we should show the login tooltip
  useEffect(() => {
    // Only show tooltip if user is not logged in
    if (isLoggedIn) {
      setShowLoginTooltip(false);
    }
  }, [isLoggedIn]);

  // Optimized favoriting to avoid unnecessary array copies
  const handleFavoriteEvent = useCallback(async (event, index, e) => {
    e.stopPropagation();
    
    if (isLoggedIn) {
      const phoneNumber = actualPhoneNumber || authPhoneNumber;
      
      if (!phoneNumber) {
        toast.error('Phone number not available. Please try logging in again.');
        return;
      }
      
      // Check if the event is already favorited
      const wasFavorite = event.is_favorite;
      
      // Update the events array to reflect the new favorite status
      setEvents(prevEvents => {
        // Create a new array with new event objects to ensure React detects the change
        return prevEvents.map(e => {
          if (e.event_name === event.event_name && 
              e.venue === event.venue && 
              e.date === event.date) {
            return { ...e, is_favorite: !wasFavorite };
          }
          return e;
        });
      });
      
      try {
        // Determine if we're favoriting or unfavoriting
        const action = wasFavorite ? 'unstar_event' : 'star_event';
        const url = `${apiUrl}/${action}`;
        
        // Create an object with essential event metadata for matching
        const eventMetadata = {
          event_name: event.event_name,
          venue: event.venue,
          date: event.date,
          raw_date: event.raw_date,
          organizer: event.organizer || "",
          ticket_info: event.ticket_info || "",
          genre: event.genre || "",
          event_url: event.event_url || ""
        };
        
        const requestBody = { 
          phone_number: phoneNumber,
          event_metadata: eventMetadata
        };
        
        // For star_event, include the full event
        if (action === 'star_event') {
          requestBody.event = event;
        }
        
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(requestBody),
        });
        
        const data = await response.json();
        
        if (!response.ok) {
          // Revert UI change if API call failed
          setEvents(prevEvents => {
            return prevEvents.map(e => {
              if (e.event_name === event.event_name && 
                  e.venue === event.venue && 
                  e.date === event.date) {
                return { ...e, is_favorite: wasFavorite };
              }
              return e;
            });
          });
          
          toast.error(data.message || `Failed to ${action} event`);
        } else {
          // Success case - show a success message
          toast.success(wasFavorite 
            ? 'Event removed from favorites!' 
            : 'Event added to favorites!');
        }
      } catch (error) {
        // Revert UI change if there was an error
        setEvents(prevEvents => {
          return prevEvents.map(e => {
            if (e.event_name === event.event_name && 
                e.venue === event.venue && 
                e.date === event.date) {
              return { ...e, is_favorite: wasFavorite };
            }
            return e;
          });
        });
        
        toast.error(`Failed to ${wasFavorite ? 'unstar' : 'star'} event`);
      }
    } else {
      toast.error('Please log in to favorite events');
    }
  }, [isLoggedIn, apiUrl, toast, actualPhoneNumber, authPhoneNumber]);

  // Function to share favorited events
  const handleShareFavorites = async () => {
    try {
      setSharing(true);
      // Use the getPhoneHash method that we already destructured
      const hashToUse = await getPhoneHash();
      
      if (!hashToUse) {
        throw new Error('Could not generate a valid hash for sharing');
      }

      // Create share URL with the resolved hash
      const shareUrl = `${window.location.origin}/favorited_events/${hashToUse}`;
      
      // Try to use native sharing if available
      if (navigator.share) {
        try {
          await navigator.share({
            title: 'My Favorited Events',
            text: `Check out ${userName || 'my'} favorited events on SproutMe!`,
            url: shareUrl
          });
        } catch (err) {
          // Fallback to copying to clipboard
          await copyToClipboard(shareUrl);
          toast.success('Share link copied to clipboard!');
        }
      } else {
        // Fallback for browsers without native sharing
        await copyToClipboard(shareUrl);
        toast.success('Share link copied to clipboard!');
      }
    } catch (error) {
      toast.error('Failed to generate share link. Please try again.');
    } finally {
      setSharing(false);
    }
  };

  // Helper function to copy text to clipboard
  const copyToClipboard = async (text) => {
    if (navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (err) {
        return false;
      }
    } else {
      // Fallback method for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      try {
        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        return successful;
      } catch (err) {
        document.body.removeChild(textArea);
        return false;
      }
    }
  };

  // Check which events are favorited for the current user - optimized
  const checkFavoritedEvents = useCallback(async (eventsData) => {
    // Use actualPhoneNumber if available, otherwise fall back to authPhoneNumber
    const phoneNumber = actualPhoneNumber || authPhoneNumber;
    
    if (!isLoggedIn || !phoneNumber) {
      return eventsData; // Return original data if not logged in or no phone number
    }

    try {
      const url = `${apiUrl}/favorite_events_by_phone?phone_number=${encodeURIComponent(phoneNumber)}`;
      
      const response = await fetch(url, {
        method: "GET",
        headers: {
          "Content-Type": "application/json"
        }
      });

      if (!response.ok) {
        return eventsData; // Return original data on API error
      }

      // Safely parse the JSON response
      let data;
      try {
        data = await response.json();
      } catch (parseError) {
        return eventsData; // Return original data on parse error
      }
      
      // The server returns data in data.data format based on your server implementation
      const favoritedEvents = data.data || [];
      
      if (favoritedEvents.length === 0) {
        return eventsData;
      }
      
      // Use Map for O(1) lookups instead of array.some() which is O(n)
      const favoritedMap = new Map();
      favoritedEvents.forEach(favEvent => {
        // Create a unique key for each event using event name, venue, and date
        const key = `${favEvent.event_name}|${favEvent.venue}|${favEvent.date}`;
        favoritedMap.set(key, true);
      });
      
      // Mark events as favorited using the map for fast lookups
      return eventsData.map(event => {
        // Create the same key format for matching
        const key = `${event.event_name}|${event.venue}|${event.date}`;
        return {
          ...event,
          is_favorite: favoritedMap.has(key)
        };
      });
    } catch (error) {
      console.error("Error checking favorited events:", error);
      return eventsData; // Return original data on error
    }
  }, [apiUrl, isLoggedIn, actualPhoneNumber, authPhoneNumber]);

  // Fetch events - optimized
  async function fetchEvents() {
    try {
      const url = `${apiUrl}/events`;
      const response = await fetch(url, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }

      const data = await response.json();
      let eventsData = data.data || [];
      
      // Process events to replace empty genres with 'None'
      eventsData = eventsData.map(event => ({
        ...event,
        genre: event.genre && event.genre.trim() ? event.genre : 'None'
      }));
      
      // Check which events are favorited for the current user
      const eventsWithFavorites = await checkFavoritedEvents(eventsData);
      
      // Update the events state with the favorited status
      setEvents(eventsWithFavorites);
      
      if (data.phoneNumber) {
        setActualPhoneNumber(data.phoneNumber);
      }
      
      setLoading(false);
    } catch (error) {
      console.error("Error fetching events:", error);
      setError("Failed to fetch events. Please try again later.");
      setLoading(false);
    }
  }

  // Reset all filters
  const resetFilters = () => {
    setDateRange({ start: "", end: "" });
    setSelectedGenres([]);
    setSearchTerm("");
    setSelectedOrganizers([]);
    setSelectedVenues([]);
    setPriceSort("none");
    setSelectedCities([]);
    setShowStarredOnly(false);
  };

  // Open filter modal
  const openFilterModal = useCallback((modalName) => {
    if (activeFilterModal === modalName) {
      setActiveFilterModal(null);
    } else {
      setActiveFilterModal(modalName);
    }
  }, [activeFilterModal]);

  // Memory cleanup on unmount
  useEffect(() => {
    return () => {
      // Clear large arrays when component unmounts
      setEvents([]);
      setAvailableGenres([]);
      setAvailableOrganizers([]);
      setAvailableVenues([]);
      setAvailableCities([]);
    };
  }, []);

  return (
    <div className={`w-screen min-h-screen flex flex-col items-center ${
      darkMode ? 'bg-gray-900 text-gray-100' : 'bg-gray-50 text-gray-900'
    } transition-colors duration-300`}>
      {/* Header */}
      <div className={`w-full ${
        darkMode ? 'bg-gray-800 shadow-gray-900' : 'bg-white shadow-gray-200'
      } shadow-md p-4 flex justify-between items-center mb-6 transition-colors duration-300`}>
        <div className="flex items-center">
          <img src={sproutIcon} alt="Sprout Logo" className="h-8 w-8 mr-2" />
          <span className={`font-bold text-xl ${
            darkMode ? 'text-green-400' : 'text-green-600'
          } transition-colors duration-300`}>SproutMe</span>
      </div>
      
        <div className="flex items-center space-x-2">
          <ThemeToggle />
          
          {/* Welcome Message */}
          {isLoggedIn && (
            <span className={`text-sm ${
              darkMode ? 'text-gray-300' : 'text-gray-600'
            } hidden md:inline-block mr-2 transition-colors duration-300`}>
              Welcome, {userName || "User"}
            </span>
          )}
        
          {/* Favorites Button (replacing Share Favorites) */}
          {isLoggedIn && (
          <button
              onClick={async () => {
                // Get the user's phone hash for the correct URL
                const hashToUse = await getPhoneHash();
                if (hashToUse) {
                  navigate(`/favorited_events/${hashToUse}`);
                } else {
                  toast.error('Could not retrieve your favorites');
                }
              }}
              className={`${
                darkMode 
                  ? 'bg-purple-700 hover:bg-purple-600 text-white' 
                  : 'bg-purple-600 hover:bg-purple-700 text-white'
              } font-medium py-2 md:px-4 px-2 text-sm md:text-base rounded-lg transition-colors mr-2 flex items-center justify-center`}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" viewBox="0 0 24 24" fill="#FBBF24" stroke="#FBBF24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
              </svg>
              <span className="hidden sm:inline whitespace-nowrap font-medium">Favorites</span>
              <span className="sm:hidden font-medium">Favs</span>
          </button>
        )}
          
          {/* Auth Button */}
          <div className="relative">
            <button
              onClick={() => isLoggedIn ? logout() : navigate('/login')}
              className={`${
                isLoggedIn 
                  ? darkMode ? 'bg-red-700 hover:bg-red-600' : 'bg-red-500 hover:bg-red-600' 
                  : darkMode ? 'bg-purple-700 hover:bg-purple-600' : 'bg-purple-500 hover:bg-purple-600'
              } text-white font-medium py-2 px-4 rounded-lg transition-colors`}
            >
              {isLoggedIn ? 'Logout' : 'Login'}
            </button>
            
            {/* Login Tooltip for non-logged in users */}
            {!isLoggedIn && showLoginTooltip && (
              <div className={`absolute right-0 top-full mt-2 w-72 p-4 rounded-lg shadow-2xl z-[100] ${
                darkMode ? 'bg-gray-800 text-gray-200 border-2 border-green-500' : 'bg-white text-gray-800 border-2 border-green-500'
              }`}>
                <div className="relative overflow-hidden">
                  {/* Shine effect */}
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shine"></div>
                  
                  <div className="flex justify-between items-start mb-3">
                    <div className="text-base font-bold text-green-500">Login to unlock features:</div>
            <button
                      onClick={() => setShowLoginTooltip(false)}
                      className="text-gray-500 hover:text-gray-700"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
                  <ul className="text-sm space-y-3">
                    <li className="flex items-start">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-green-500 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
                      <span className="font-medium">Save your favorite events</span>
                    </li>
                    <li className="flex items-start">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-green-500 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <span className="font-medium">Share events with friends</span>
                    </li>
                    <li className="flex items-start">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-green-500 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <span className="font-medium">Track your event history</span>
                    </li>
                  </ul>
          </div>
  </div>
            )}
          </div>
        </div>
      </div>
      
      {/* Tagline Header */}
      <div className="w-full max-w-5xl px-4 mb-6 text-center">
        <h1 className={`font-bold text-2xl md:text-3xl mb-2 ${
          darkMode ? 'text-green-400' : 'text-green-600'
        } transition-colors duration-300 font-prosto`}>
          Your EDM Show Companion
        </h1>
        <p className={`text-sm md:text-base ${
          darkMode ? 'text-gray-300' : 'text-gray-600'
        } transition-colors duration-300 font-prosto`}>
          Discover the best electronic music events across North America
        </p>
          </div>
      
      {/* Filter section */}
      <div className="w-full max-w-5xl px-4 flex justify-between items-center mb-4">
        <div className="flex items-center">
          <button 
            onClick={() => setShowFilters(!showFilters)}
            className={`${
              showFilters
                ? darkMode
                  ? 'bg-green-700 hover:bg-green-600 text-white border-2 border-green-500'
                  : 'bg-green-600 hover:bg-green-700 text-white border-2 border-green-400'
                : 'bg-green-500 hover:bg-green-600 text-white'
            } font-medium py-2 px-4 rounded-lg transition-colors flex items-center shadow-md`}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className={`h-5 w-5 mr-2 ${showFilters ? 'animate-pulse' : ''}`} viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M3 3a1 1 0 011-1h12a1 1 0 011 1v3a1 1 0 01-.293.707L12 11.414V15a1 1 0 01-.293.707l-2 2A1 1 0 018 17v-5.586L3.293 6.707A1 1 0 013 6V3z" clipRule="evenodd" />
            </svg>
            Filters
            {filterCount > 0 && (
              <span className="ml-2 bg-white text-green-600 rounded-full w-5 h-5 flex items-center justify-center text-xs font-bold">
                {filterCount}
              </span>
            )}
          </button>
            </div>
            
        {/* Clear All Button - moved from navbar */}
        {filterCount > 0 && (
                      <button
            onClick={resetFilters}
            className={`${
              darkMode 
                ? 'bg-amber-700 hover:bg-amber-600 text-amber-100' 
                : 'bg-yellow-500 hover:bg-yellow-600 text-white'
            } font-medium py-2 px-4 rounded-lg transition-colors flex items-center`}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
            Clear All
          </button>
        )}
      </div>
      
      <FilterSection 
        showFilters={showFilters}
        setShowFilters={setShowFilters}
        filterCount={filterCount}
        resetFilters={resetFilters}
        dateRange={dateRange}
        setDateRange={setDateRange}
        searchTerm={searchTerm}
        setSearchTerm={setSearchTerm}
        priceSort={priceSort}
        setPriceSort={setPriceSort}
        selectedGenres={selectedGenres}
        selectedOrganizers={selectedOrganizers}
        selectedVenues={selectedVenues}
        selectedCities={selectedCities}
        openFilterModal={openFilterModal}
        events={events}
        filteredEvents={filteredEvents}
        showStarredOnly={showStarredOnly}
        setShowStarredOnly={setShowStarredOnly}
        isLoggedIn={isLoggedIn}
        sharing={sharing}
        handleShareFavorites={handleShareFavorites}
      />
      
      <FilterModal
        activeFilterModal={activeFilterModal}
        setActiveFilterModal={setActiveFilterModal}
        availableGenres={availableGenres}
        availableOrganizers={availableOrganizers}
        availableVenues={availableVenues}
        availableCities={availableCities}
        selectedGenres={selectedGenres}
        selectedOrganizers={selectedOrganizers}
        selectedVenues={selectedVenues}
        selectedCities={selectedCities}
        setSelectedGenres={setSelectedGenres}
        setSelectedOrganizers={setSelectedOrganizers}
        setSelectedVenues={setSelectedVenues}
        setSelectedCities={setSelectedCities}
        toggleArrayItem={toggleArrayItem}
      />
      
      <div className="w-full max-w-5xl px-4 pb-6">
        <EventList
          loading={loading}
          error={error}
          filteredEvents={filteredEvents}
          displayedEvents={displayedEvents}
          currentPage={currentPage}
          eventsPerPage={eventsPerPage}
          onPageChange={setCurrentPage}
          onFavoriteEvent={handleFavoriteEvent}
          showStarredOnly={showStarredOnly}
        />
      </div>
      
      <ContactFooter />
    </div>
  );
};

export default EventsPage;