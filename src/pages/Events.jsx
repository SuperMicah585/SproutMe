import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import EventList from "../components/events/EventList";
import FilterSection from "../components/events/FilterSection";
import FilterModal from "../components/events/FilterModal";
import ThemeToggle from "../components/events/ThemeToggle";
import ContactFooter from "../components/events/ContactFooter";
import LoginPrompt from "../components/events/LoginPrompt";
import SmsIntroModal, { SMS_STORAGE_KEY } from "../components/events/SmsIntroModal";
import AddEventModal from "../components/events/AddEventModal";
import { 
  hashPhoneNumber, 
  verifyPhoneHash, 
  toggleArrayItem,
} from "../components/events/eventUtils";
import sproutIcon from './Components/sprout_icon.png';
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useToast } from "./Components/ToastNotification";
import { trackEvent } from "../utils/analytics";
import { getFiltersFromStorage, saveFiltersToStorage } from "../utils/filterStorage";
import { lookupApproxLocation, matchEventCity } from "../utils/cityFromLocation";

const EventsPage = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const { phoneHash: urlPhoneHash } = useParams();
  const { isLoggedIn, phoneHash: authPhoneHash, userName, phoneNumber: authPhoneNumber, getPhoneHash, logout } = useAuth();
  const { darkMode } = useTheme();
  const toast = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    const closeMobileNavOnDesktop = () => {
      if (window.innerWidth >= 768) {
        setShowMobileNav(false);
      }
    };
    window.addEventListener('resize', closeMobileNavOnDesktop);
    return () => window.removeEventListener('resize', closeMobileNavOnDesktop);
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

  // Infinite-scroll / server pagination
  const [hasMore, setHasMore] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const eventsPerPage = 50;
  const fetchOffsetRef = useRef(0);
  const fetchInFlightRef = useRef(false);
  const fetchGenerationRef = useRef(0);

  const storedFiltersRef = useRef(getFiltersFromStorage());
  const geoTriedRef = useRef(false);

  // Filter states
  const [dateRange, setDateRange] = useState({ start: "", end: "" });
  const [selectedGenres, setSelectedGenres] = useState(() => storedFiltersRef.current?.selectedGenres || []);
  const [searchTerm, setSearchTerm] = useState(() => storedFiltersRef.current?.searchTerm || "");
  const [selectedOrganizers, setSelectedOrganizers] = useState(() => storedFiltersRef.current?.selectedOrganizers || []);
  const [selectedVenues, setSelectedVenues] = useState(() => storedFiltersRef.current?.selectedVenues || []);
  const [priceSort, setPriceSort] = useState(() => storedFiltersRef.current?.priceSort || "none");
  const [selectedCities, setSelectedCities] = useState(() => storedFiltersRef.current?.selectedCities || []);
  const [showStarredOnly, setShowStarredOnly] = useState(false);
  
  // For dropdown filters - only populate when needed
  const [availableGenres, setAvailableGenres] = useState([]);
  const [availableOrganizers, setAvailableOrganizers] = useState([]);
  const [availableVenues, setAvailableVenues] = useState([]);
  const [availableCities, setAvailableCities] = useState([]);
  
  // Mobile UI states
  const [showFilters, setShowFilters] = useState(false);
  const [activeFilterModal, setActiveFilterModal] = useState(null);
  const [filterCount, setFilterCount] = useState(0);
  const [sharing, setSharing] = useState(false);
  const [showLoginTooltip, setShowLoginTooltip] = useState(true);
  const [showLoginPrompt, setShowLoginPrompt] = useState(false);
  const [showSmsIntro, setShowSmsIntro] = useState(false);
  const [showAddEvent, setShowAddEvent] = useState(false);
  const [showMobileNav, setShowMobileNav] = useState(false);

  const buildEventsQuery = useCallback((offset = 0) => {
    const params = new URLSearchParams();
    params.set('limit', String(eventsPerPage));
    params.set('offset', String(offset));
    selectedCities.forEach((city) => params.append('city', city));
    selectedGenres.forEach((genre) => params.append('genre', genre));
    selectedVenues.forEach((venue) => params.append('venue', venue));
    selectedOrganizers.forEach((organizer) => params.append('organizer', organizer));
    if (searchTerm.trim()) params.set('q', searchTerm.trim());
    if (dateRange.start) params.set('date_start', dateRange.start);
    if (dateRange.end) params.set('date_end', dateRange.end);
    if (priceSort !== 'none') params.set('price_sort', priceSort);
    if (showStarredOnly) params.set('favorites_only', '1');
    const phone = actualPhoneNumber || authPhoneNumber;
    if (phone) params.set('phone_number', phone);
    return params;
  }, [
    eventsPerPage,
    selectedCities,
    selectedGenres,
    selectedVenues,
    selectedOrganizers,
    searchTerm,
    dateRange.start,
    dateRange.end,
    priceSort,
    showStarredOnly,
    actualPhoneNumber,
    authPhoneNumber,
  ]);

  const fetchFacets = useCallback(async (exclude = null) => {
    try {
      const params = buildEventsQuery(0);
      params.delete('limit');
      params.delete('offset');
      params.delete('price_sort');
      if (exclude) params.set('exclude', exclude);
      const response = await fetch(`${apiUrl}/events/facets?${params.toString()}`);
      if (!response.ok) throw new Error(`Facets failed: ${response.status}`);
      const data = await response.json();
      const facets = data.data || {};
      setAvailableCities(facets.cities || []);
      setAvailableGenres(facets.genres || []);
      setAvailableOrganizers(facets.organizers || []);
      setAvailableVenues(facets.venues || []);
    } catch (err) {
      console.error('Error fetching facets:', err);
    }
  }, [apiUrl, buildEventsQuery]);

  const fetchEventsPage = useCallback(async ({ reset = false } = {}) => {
    if (fetchInFlightRef.current && !reset) return;
    const generation = reset
      ? (fetchGenerationRef.current += 1)
      : fetchGenerationRef.current;
    fetchInFlightRef.current = true;
    const offset = reset ? 0 : fetchOffsetRef.current;
    if (reset) {
      setLoading(true);
      setError(null);
      setHasMore(false);
    } else {
      setLoadingMore(true);
    }
    try {
      const params = buildEventsQuery(offset);
      const response = await fetch(`${apiUrl}/events?${params.toString()}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }
      const data = await response.json();
      if (generation !== fetchGenerationRef.current) return;

      const page = (data.data || []).map((event) => ({
        ...event,
        genre: event.genre && String(event.genre).trim() ? event.genre : 'None',
      }));

      setTotalCount(Number(data.total) || 0);
      setHasMore(Boolean(data.has_more));
      fetchOffsetRef.current = offset + page.length;
      setEvents((prev) => (reset ? page : [...prev, ...page]));
      if (data.phoneNumber) {
        setActualPhoneNumber(data.phoneNumber);
      }
    } catch (err) {
      console.error('Error fetching events:', err);
      if (generation !== fetchGenerationRef.current) return;
      if (reset) {
        setError('Failed to fetch events. Please try again later.');
        setEvents([]);
        setHasMore(false);
        setTotalCount(0);
      }
    } finally {
      if (generation === fetchGenerationRef.current) {
        setLoading(false);
        setLoadingMore(false);
        fetchInFlightRef.current = false;
      }
    }
  }, [apiUrl, buildEventsQuery]);

  const loadMoreEvents = useCallback(() => {
    if (!hasMore || loadingMore || loading || fetchInFlightRef.current) return;
    fetchEventsPage({ reset: false });
  }, [hasMore, loadingMore, loading, fetchEventsPage]);

  // Initial load + auth hash changes
  useEffect(() => {
    const run = async () => {
      if (!hasLoadedInitialData.current) {
        await fetchEventsPage({ reset: true });
        hasLoadedInitialData.current = true;
      } else if (
        urlPhoneHash !== prevUrlPhoneHash.current ||
        authPhoneHash !== prevAuthPhoneHash.current
      ) {
        await fetchEventsPage({ reset: true });
      }
      prevUrlPhoneHash.current = urlPhoneHash;
      prevAuthPhoneHash.current = authPhoneHash;
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Refetch when server-side filters change (debounced for typing)
  const skipFilterFetchRef = useRef(true);
  useEffect(() => {
    if (!hasLoadedInitialData.current) return undefined;
    if (skipFilterFetchRef.current) {
      skipFilterFetchRef.current = false;
      return undefined;
    }
    const handle = setTimeout(() => {
      fetchOffsetRef.current = 0;
      fetchEventsPage({ reset: true });
    }, searchTerm ? 300 : 0);
    return () => clearTimeout(handle);
    // intentionally omit fetchEventsPage to avoid refetch loops from callback identity
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    selectedCities,
    selectedGenres,
    selectedVenues,
    selectedOrganizers,
    searchTerm,
    dateRange.start,
    dateRange.end,
    priceSort,
    showStarredOnly,
    actualPhoneNumber,
    authPhoneNumber,
  ]);

  // Load facet options when a filter modal opens
  useEffect(() => {
    if (!activeFilterModal) return;
    const excludeMap = {
      genres: 'genres',
      organizers: 'organizers',
      venues: 'venues',
      cities: 'cities',
    };
    fetchFacets(excludeMap[activeFilterModal] || null);
  }, [activeFilterModal, fetchFacets]);

  // Keep city list available for geo matching even before opening the modal
  useEffect(() => {
    if (!hasLoadedInitialData.current) return;
    if (availableCities.length) return;
    fetchFacets();
  }, [availableCities.length, fetchFacets]);

  // Update filter count for badge  // Update filter count for badge
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

  useEffect(() => {
    const hasFilters = selectedCities.length
      || selectedGenres.length
      || selectedOrganizers.length
      || selectedVenues.length
      || searchTerm.trim()
      || priceSort !== 'none'
      || storedFiltersRef.current;
    if (!hasFilters) return;
    saveFiltersToStorage({
      selectedCities,
      selectedGenres,
      selectedOrganizers,
      selectedVenues,
      searchTerm,
      priceSort,
      skipGeo: Boolean(storedFiltersRef.current?.skipGeo),
    });
  }, [selectedCities, selectedGenres, selectedOrganizers, selectedVenues, searchTerm, priceSort]);

  useEffect(() => {
    const skipGeo = storedFiltersRef.current?.skipGeo
      || storedFiltersRef.current?.selectedCities?.length
      || selectedCities.length;
    const cityNames = availableCities.map((item) => item.name || item).filter(Boolean);
    if (!cityNames.length || geoTriedRef.current || skipGeo) {
      return undefined;
    }
    let cancelled = false;
    (async () => {
      const geo = await lookupApproxLocation();
      if (cancelled) return;
      geoTriedRef.current = true;
      if (!geo?.city) return;
      const match = matchEventCity(geo, cityNames);
      if (match) {
        setSelectedCities([match]);
        trackEvent('geo_city_filter', { city: match, source: 'ip' });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [availableCities, selectedCities.length]);

  useEffect(() => {
    if (!availableCities.length || !selectedCities.length) return undefined;
    const venueCities = availableCities.map((item) => item.name || item).filter(Boolean);
    const upgraded = selectedCities.map((city) => {
      const specific = venueCities.find((option) =>
        option !== city && option.toLowerCase().startsWith(`${city.toLowerCase()},`)
      );
      return specific || city;
    });
    if (upgraded.some((city, index) => city !== selectedCities[index])) {
      setSelectedCities(upgraded);
    }
    return undefined;
  }, [availableCities, selectedCities]);

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

  // Function to close login tooltip
  const closeLoginTooltip = () => {
    setShowLoginTooltip(false);
    // Store the preference in localStorage so it doesn't reappear
    localStorage.setItem('hideLoginTooltip', 'true');
  };
  
  // Update the useEffect for showLoginTooltip initialization
  useEffect(() => {
    // Check if user has previously closed the tooltip
    const hideTooltip = localStorage.getItem('hideLoginTooltip') === 'true';
    setShowLoginTooltip(!hideTooltip && !isLoggedIn);
  }, [isLoggedIn]);

  useEffect(() => {
    const hideSmsIntro = localStorage.getItem(SMS_STORAGE_KEY) === 'true';
    setShowSmsIntro(!hideSmsIntro);
  }, []);

  const closeSmsIntro = useCallback(() => {
    setShowSmsIntro(false);
    localStorage.setItem(SMS_STORAGE_KEY, 'true');
  }, []);

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
      setShowLoginPrompt(true);
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
    storedFiltersRef.current = {
      selectedCities: [],
      selectedGenres: [],
      selectedOrganizers: [],
      selectedVenues: [],
      searchTerm: "",
      priceSort: "none",
      skipGeo: true,
    };
    saveFiltersToStorage(storedFiltersRef.current);
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
    } transition-colors duration-300 relative`}>
      {/* Modal Overlay - Only shown when login tooltip is visible */}
      {!isLoggedIn && showLoginTooltip && (
        <div 
          className="hidden md:block fixed inset-0 bg-black bg-opacity-5 z-40"
          onClick={closeLoginTooltip}
        />
      )}
    
      {/* Header */}
      <div className={`w-full ${
        darkMode ? 'bg-gray-800 shadow-gray-900' : 'bg-white shadow-gray-200'
      } shadow-md mb-6 transition-colors duration-300 relative`}>
        <div className="p-4 flex justify-between items-center">
          <div className="flex items-center min-w-0 mr-2">
            <Link to="/events" aria-label="SproutMe home" className="flex items-center min-w-0">
              <img src={sproutIcon} alt="" className="h-8 w-8 mr-2 flex-shrink-0" />
              <span className={`font-bold text-xl truncate ${
                darkMode ? 'text-green-400' : 'text-green-600'
              } transition-colors duration-300`}>SproutMe</span>
            </Link>
          </div>

          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={() => setShowAddEvent(true)}
              className={`${
                darkMode ? 'bg-green-700 hover:bg-green-600' : 'bg-green-600 hover:bg-green-500'
              } text-white font-medium py-2 px-3 text-sm rounded-lg flex items-center`}
              aria-label="Add an event"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
              </svg>
              Add Event
            </button>
            <ThemeToggle />

            {isLoggedIn && (
              <span className={`text-sm ${
                darkMode ? 'text-gray-300' : 'text-gray-600'
              } mr-2 transition-colors duration-300`}>
                Welcome, {userName || "User"}
              </span>
            )}

            {isLoggedIn && (
              <button
                onClick={async () => {
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
                } font-medium py-2 px-4 text-sm rounded-lg transition-colors flex items-center justify-center`}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" viewBox="0 0 24 24" fill="#FBBF24" stroke="#FBBF24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                </svg>
                Favorites
              </button>
            )}

            <div className="relative" style={{ zIndex: 100 }}>
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

              {!isLoggedIn && showLoginTooltip && (
                <div
                  className={`absolute right-0 top-full mt-2 w-72 p-4 rounded-lg shadow-2xl z-50 ${
                    darkMode ? 'bg-gray-800 text-gray-200 border-2 border-green-500' : 'bg-white text-gray-800 border-2 border-green-500'
                  }`}
                  style={{ pointerEvents: 'auto' }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="relative overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shine pointer-events-none"></div>
                    <div className="flex justify-between items-start mb-3">
                      <div className="text-base font-bold text-green-500">Login to unlock features:</div>
                      <button
                        onClick={closeLoginTooltip}
                        className="text-gray-500 hover:text-gray-700 p-1 rounded-full hover:bg-gray-200 cursor-pointer"
                        aria-label="Close tooltip"
                        type="button"
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
                    <div className="mt-4 flex justify-between">
                      <button
                        onClick={() => {
                          navigate('/login');
                          closeLoginTooltip();
                        }}
                        className={`${darkMode ? 'bg-purple-700 hover:bg-purple-600' : 'bg-purple-600 hover:bg-purple-500'} text-white px-4 py-2 rounded-lg font-medium text-sm cursor-pointer`}
                        type="button"
                      >
                        Login Now
                      </button>
                      <button
                        onClick={closeLoginTooltip}
                        className={`${darkMode ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-200 hover:bg-gray-300'} ${darkMode ? 'text-gray-300' : 'text-gray-700'} px-4 py-2 rounded-lg font-medium text-sm cursor-pointer`}
                        type="button"
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Mobile hamburger */}
          <button
            type="button"
            className={`md:hidden p-2 rounded-lg ${
              darkMode ? 'text-gray-100 hover:bg-gray-700' : 'text-gray-800 hover:bg-gray-100'
            }`}
            aria-label={showMobileNav ? 'Close menu' : 'Open menu'}
            aria-expanded={showMobileNav}
            onClick={() => setShowMobileNav((open) => !open)}
          >
            {showMobileNav ? (
              <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>

        {showMobileNav && (
          <div className={`md:hidden border-t px-4 py-3 flex flex-col gap-2 ${
            darkMode ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-white'
          }`}>
            {isLoggedIn && (
              <p className={`text-sm ${darkMode ? 'text-gray-300' : 'text-gray-600'} px-1`}>
                Welcome, {userName || "User"}
              </p>
            )}
            <button
              type="button"
              onClick={() => {
                setShowMobileNav(false);
                setShowAddEvent(true);
              }}
              className={`mobile-nav-item ${
                darkMode ? 'bg-green-700' : 'bg-green-600'
              } text-white font-medium py-3 px-4 rounded-lg flex items-center justify-center w-full`}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
              </svg>
              Add Event
            </button>
            {isLoggedIn && (
              <button
                onClick={async () => {
                  setShowMobileNav(false);
                  const hashToUse = await getPhoneHash();
                  if (hashToUse) {
                    navigate(`/favorited_events/${hashToUse}`);
                  } else {
                    toast.error('Could not retrieve your favorites');
                  }
                }}
                className={`mobile-nav-item ${
                  darkMode ? 'bg-purple-700 text-white' : 'bg-purple-600 text-white'
                } font-medium py-3 px-4 rounded-lg flex items-center justify-center w-full`}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" viewBox="0 0 24 24" fill="#FBBF24" stroke="#FBBF24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                </svg>
                Favorites
              </button>
            )}
            <ThemeToggle variant="menu" />
            <button
              onClick={() => {
                setShowMobileNav(false);
                if (isLoggedIn) {
                  logout();
                } else {
                  navigate('/login');
                }
              }}
              className={`mobile-nav-item ${
                isLoggedIn
                  ? darkMode ? 'bg-red-700' : 'bg-red-500'
                  : darkMode ? 'bg-purple-700' : 'bg-purple-500'
              } text-white font-medium py-3 px-4 rounded-lg flex items-center justify-center w-full`}
            >
              {isLoggedIn ? 'Logout' : 'Login'}
            </button>
          </div>
        )}
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
        filteredEvents={events}
        totalCount={totalCount}
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
      
      <div className="w-full max-w-5xl px-4 pb-28">
        <EventList
          loading={loading}
          loadingMore={loadingMore}
          error={error}
          events={events}
          hasMore={hasMore}
          totalCount={totalCount}
          onLoadMore={loadMoreEvents}
          onFavoriteEvent={handleFavoriteEvent}
          showStarredOnly={showStarredOnly}
        />
      </div>
      
      <LoginPrompt
        open={showLoginPrompt}
        onClose={() => setShowLoginPrompt(false)}
      />

      <SmsIntroModal
        open={showSmsIntro}
        onClose={closeSmsIntro}
      />

      <AddEventModal
        open={showAddEvent}
        onClose={() => setShowAddEvent(false)}
        apiUrl={apiUrl}
        onAdd={(event) => {
          setEvents((prev) => [event, ...prev]);
          setTotalCount((prev) => prev + 1);
        }}
      />
      
      <ContactFooter />
    </div>
  );
};

export default EventsPage;