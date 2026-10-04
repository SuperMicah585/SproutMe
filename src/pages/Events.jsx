import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import EventList from "../components/events/EventList";
import FilterSection from "../components/events/FilterSection";
import FilterModal from "../components/events/FilterModal";
import QuickFilterBar from "../components/events/QuickFilterBar";
import ThemeToggle from "../components/events/ThemeToggle";
import ContactFooter from "../components/events/ContactFooter";
import LoginPrompt from "../components/events/LoginPrompt";
import AddEventModal from "../components/events/AddEventModal";
import { CHATGPT_HREF } from "../components/events/ChatGptWidget";
import { toggleArrayItem } from "../components/events/eventUtils";
import sproutIcon from './Components/sprout_icon.png';
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useToast } from "./Components/ToastNotification";
import { trackEvent } from "../utils/analytics";
import { getFiltersFromStorage, saveFiltersToStorage } from "../utils/filterStorage";
import { lookupApproxLocation, matchEventCity } from "../utils/cityFromLocation";
import {
  getDefaultDateRange,
  rangeForPreset,
  detectDatePreset,
} from "../utils/eventFilters";

const PAGE_SIZE = 50;

const EventsPage = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const { isLoggedIn, userName, phoneNumber: authPhoneNumber, getPhoneHash, logout } = useAuth();
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
  
  const hasLoadedInitialData = useRef(false);
  const fetchAbortRef = useRef(null);
  const loadingMoreRef = useRef(false);
  const requestIdRef = useRef(0);
  
  const [events, setEvents] = useState([]);
  const [totalEvents, setTotalEvents] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [actualPhoneNumber, setActualPhoneNumber] = useState(null);

  const storedFiltersRef = useRef(getFiltersFromStorage());
  const geoTriedRef = useRef(false);
  const facetCitiesRef = useRef([]);

  // Filter states — default Tonight (Fri–Sun) / Weekend (Mon–Thu) like Sep 26
  const [dateRange, setDateRange] = useState(() => {
    const stored = storedFiltersRef.current?.dateRange;
    if (storedFiltersRef.current?.hasChosenDates && (stored?.start || stored?.end)) {
      return { start: stored.start || "", end: stored.end || "" };
    }
    if (storedFiltersRef.current?.hasChosenDates && stored && !stored.start && !stored.end) {
      return { start: "", end: "" };
    }
    return getDefaultDateRange();
  });
  const [selectedGenres, setSelectedGenres] = useState(() => storedFiltersRef.current?.selectedGenres || []);
  const [searchTerm, setSearchTerm] = useState(() => storedFiltersRef.current?.searchTerm || "");
  const [selectedOrganizers, setSelectedOrganizers] = useState(() => storedFiltersRef.current?.selectedOrganizers || []);
  const [selectedVenues, setSelectedVenues] = useState(() => storedFiltersRef.current?.selectedVenues || []);
  const [priceSort, setPriceSort] = useState(() => storedFiltersRef.current?.priceSort || "none");
  const [scoreSort, setScoreSort] = useState(() => storedFiltersRef.current?.scoreSort || "none");
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
  const [showAddEvent, setShowAddEvent] = useState(false);
  const [showMobileNav, setShowMobileNav] = useState(false);
  const chromeRef = useRef(null);
  const [chromeHeight, setChromeHeight] = useState(0);

  const [debouncedSearch, setDebouncedSearch] = useState(
    () => storedFiltersRef.current?.searchTerm || ""
  );

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchTerm), 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    const node = chromeRef.current;
    if (!node || typeof ResizeObserver === "undefined") return undefined;
    const sync = () => setChromeHeight(node.getBoundingClientRect().height);
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(node);
    return () => observer.disconnect();
  }, [showMobileNav, filterCount, selectedCities.length, selectedGenres.length, darkMode]);

  const applyDatePreset = useCallback((preset) => {
    setDateRange(rangeForPreset(preset));
  }, []);

  const emptyHints = useMemo(() => {
    const hints = [];
    const preset = detectDatePreset(dateRange);
    if (preset === "tonight") {
      hints.push({
        id: "weekend",
        label: "Try this weekend",
        onClick: () => applyDatePreset("weekend"),
      });
    }
    if (preset !== "all") {
      hints.push({
        id: "all-dates",
        label: "Show all dates",
        onClick: () => applyDatePreset("all"),
      });
    }
    if (selectedGenres.length) {
      hints.push({
        id: "clear-genres",
        label: "Clear genres",
        onClick: () => setSelectedGenres([]),
      });
    }
    if (selectedCities.length) {
      hints.push({
        id: "clear-cities",
        label: "Clear city",
        onClick: () => setSelectedCities([]),
      });
    }
    return hints;
  }, [dateRange, selectedGenres.length, selectedCities.length, applyDatePreset]);

  const phoneForApi = actualPhoneNumber || authPhoneNumber || null;

  const buildEventParams = useCallback((offset = 0, { exclude } = {}) => {
    const params = new URLSearchParams();
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(offset));

    if (exclude !== "search" && debouncedSearch.trim()) {
      params.set("q", debouncedSearch.trim());
    }
    if (exclude !== "cities") {
      selectedCities.forEach((city) => params.append("city", city));
    }
    if (exclude !== "genres") {
      selectedGenres.forEach((genre) => params.append("genre", genre));
    }
    if (exclude !== "venues") {
      selectedVenues.forEach((venue) => params.append("venue", venue));
    }
    if (exclude !== "organizers") {
      selectedOrganizers.forEach((organizer) => params.append("organizer", organizer));
    }
    if (exclude !== "date") {
      if (dateRange.start) params.set("date_start", dateRange.start);
      if (dateRange.end) params.set("date_end", dateRange.end);
    }
    if (priceSort === "asc" || priceSort === "desc") {
      params.set("price_sort", priceSort);
    }
    if (exclude !== "starred" && showStarredOnly) {
      params.set("favorites_only", "1");
    }
    if (phoneForApi) {
      params.set("phone_number", phoneForApi);
    }
    return params;
  }, [
    debouncedSearch,
    selectedCities,
    selectedGenres,
    selectedVenues,
    selectedOrganizers,
    dateRange.start,
    dateRange.end,
    priceSort,
    showStarredOnly,
    phoneForApi,
  ]);

  const displayedEvents = useMemo(() => {
    if (scoreSort === "none") return events;
    return [...events].sort((a, b) => {
      const scoreA = Number.isFinite(Number(a.sprout_score ?? a.health))
        ? Number(a.sprout_score ?? a.health)
        : -1;
      const scoreB = Number.isFinite(Number(b.sprout_score ?? b.health))
        ? Number(b.sprout_score ?? b.health)
        : -1;
      return scoreSort === "asc" ? scoreA - scoreB : scoreB - scoreA;
    });
  }, [events, scoreSort]);

  const fetchEventsPage = useCallback(async ({ reset, soft = false } = {}) => {
    if (reset) {
      fetchAbortRef.current?.abort();
      const controller = new AbortController();
      fetchAbortRef.current = controller;
      requestIdRef.current += 1;
      const requestId = requestIdRef.current;
      loadingMoreRef.current = false;
      // Soft refetch keeps current cards visible (e.g. geo city apply).
      if (!soft || events.length === 0) {
        setLoading(true);
      }
      setLoadingMore(false);
      setError(null);

      try {
        const params = buildEventParams(0);
        const response = await fetch(`${apiUrl}/events?${params}`, {
          method: "GET",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Server responded with status ${response.status}`);
        }
        const data = await response.json();
        if (requestId !== requestIdRef.current) return;

        const page = Array.isArray(data.data) ? data.data : [];
        const total = Number.isFinite(Number(data.total)) ? Number(data.total) : page.length;
        setEvents(page);
        setTotalEvents(total);
        setHasMore(
          typeof data.has_more === "boolean"
            ? data.has_more
            : page.length < total
        );
        setLoading(false);
        hasLoadedInitialData.current = true;
      } catch (err) {
        if (err?.name === "AbortError") return;
        console.error("Error fetching events:", err);
        if (requestId !== requestIdRef.current) return;
        setError("Failed to fetch events. Please try again later.");
        setEvents([]);
        setTotalEvents(0);
        setHasMore(false);
        setLoading(false);
      }
      return;
    }

    if (!hasMore || loadingMoreRef.current || loading) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    const requestId = requestIdRef.current;
    const offset = events.length;

    try {
      const params = buildEventParams(offset);
      const response = await fetch(`${apiUrl}/events?${params}`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }
      const data = await response.json();
      if (requestId !== requestIdRef.current) return;

      const page = Array.isArray(data.data) ? data.data : [];
      const total = Number.isFinite(Number(data.total)) ? Number(data.total) : null;

      setEvents((prev) => {
        const seen = new Set(
          prev.map(
            (event) =>
              event?.id ??
              `${event?.event_name}|${event?.venue}|${event?.raw_date || event?.date}`
          )
        );
        const next = [...prev];
        for (const event of page) {
          const key =
            event?.id ??
            `${event?.event_name}|${event?.venue}|${event?.raw_date || event?.date}`;
          if (seen.has(key)) continue;
          seen.add(key);
          next.push(event);
        }
        return next;
      });

      if (total != null) setTotalEvents(total);
      setHasMore(
        typeof data.has_more === "boolean"
          ? data.has_more
          : total != null
            ? offset + page.length < total
            : page.length >= PAGE_SIZE
      );
    } catch (err) {
      console.error("Error loading more events:", err);
    } finally {
      loadingMoreRef.current = false;
      if (requestId === requestIdRef.current) {
        setLoadingMore(false);
      }
    }
  }, [apiUrl, buildEventParams, events.length, hasMore, loading]);

  const loadMoreEvents = useCallback(() => {
    fetchEventsPage({ reset: false });
  }, [fetchEventsPage]);

  const filtersReadyRef = useRef(false);
  // Refetch when server-side filters change
  useEffect(() => {
    // First mount always hard-loads; later geo/filter changes can soft-refresh.
    const soft = filtersReadyRef.current && events.length > 0;
    filtersReadyRef.current = true;
    fetchEventsPage({ reset: true, soft });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    debouncedSearch,
    selectedCities,
    selectedGenres,
    selectedVenues,
    selectedOrganizers,
    dateRange.start,
    dateRange.end,
    priceSort,
    showStarredOnly,
    phoneForApi,
  ]);

  const fetchFacets = useCallback(async (exclude) => {
    try {
      const params = buildEventParams(0, { exclude });
      params.delete("limit");
      params.delete("offset");
      params.delete("price_sort");
      if (exclude) params.set("exclude", exclude);
      const response = await fetch(`${apiUrl}/events/facets?${params}`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) return null;
      const data = await response.json();
      return data.data || null;
    } catch (err) {
      console.error("Error fetching facets:", err);
      return null;
    }
  }, [apiUrl, buildEventParams]);

  useEffect(() => {
    if (!activeFilterModal) return undefined;
    const excludeMap = {
      genres: "genres",
      cities: "cities",
      venues: "venues",
      organizers: "organizers",
    };
    const exclude = excludeMap[activeFilterModal];
    if (!exclude) return undefined;

    let cancelled = false;
    (async () => {
      const facets = await fetchFacets(exclude);
      if (cancelled || !facets) return;
      if (activeFilterModal === "genres") setAvailableGenres(facets.genres || []);
      if (activeFilterModal === "organizers") setAvailableOrganizers(facets.organizers || []);
      if (activeFilterModal === "venues") setAvailableVenues(facets.venues || []);
      if (activeFilterModal === "cities") {
        setAvailableCities(facets.cities || []);
        facetCitiesRef.current = (facets.cities || []).map((item) => item.name);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    activeFilterModal,
    fetchFacets,
    debouncedSearch,
    selectedCities,
    selectedGenres,
    selectedVenues,
    selectedOrganizers,
    dateRange.start,
    dateRange.end,
    showStarredOnly,
  ]);

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
    if (scoreSort !== "none") count++;
    if (showStarredOnly) count++;
    
    setFilterCount(count);
  }, [dateRange, selectedGenres, searchTerm, selectedOrganizers, selectedVenues, selectedCities, priceSort, scoreSort, showStarredOnly]);

  useEffect(() => {
    const hasFilters = selectedCities.length
      || selectedGenres.length
      || selectedOrganizers.length
      || selectedVenues.length
      || searchTerm.trim()
      || priceSort !== 'none'
      || scoreSort !== 'none'
      || storedFiltersRef.current;
    if (!hasFilters) return;
    saveFiltersToStorage({
      selectedCities,
      selectedGenres,
      selectedOrganizers,
      selectedVenues,
      searchTerm,
      priceSort,
      scoreSort,
      dateRange,
      hasChosenDates: true,
      skipGeo: Boolean(storedFiltersRef.current?.skipGeo),
    });
  }, [selectedCities, selectedGenres, selectedOrganizers, selectedVenues, searchTerm, priceSort, scoreSort, dateRange]);

  // Geo after first paint: don't block initial /events, and only soft-refetch if a city matches.
  useEffect(() => {
    const skipGeo = storedFiltersRef.current?.skipGeo
      || storedFiltersRef.current?.selectedCities?.length
      || selectedCities.length;
    if (geoTriedRef.current || skipGeo || loading || !hasLoadedInitialData.current) {
      return undefined;
    }
    let cancelled = false;
    (async () => {
      geoTriedRef.current = true;
      const [facets, geo] = await Promise.all([
        fetchFacets(),
        lookupApproxLocation(),
      ]);
      if (cancelled) return;
      const cities = (facets?.cities || []).map((item) => item.name).filter(Boolean);
      facetCitiesRef.current = cities;
      if (!geo?.city || !cities.length) return;
      const match = matchEventCity(geo, cities);
      if (match) {
        setSelectedCities([match]);
        trackEvent('geo_city_filter', { city: match, source: 'ip' });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedCities.length, fetchFacets, loading, events.length]);

  useEffect(() => {
    const cities = facetCitiesRef.current;
    if (!cities.length || !selectedCities.length) return undefined;
    const upgraded = selectedCities.map((city) => {
      const specific = cities.find((option) =>
        option !== city && option.toLowerCase().startsWith(`${city.toLowerCase()},`)
      );
      return specific || city;
    });
    if (upgraded.some((city, index) => city !== selectedCities[index])) {
      setSelectedCities(upgraded);
    }
    return undefined;
  }, [selectedCities, totalEvents]);

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
          'score_sort': scoreSort !== 'none',
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
    scoreSort,
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

  // Favorites are applied server-side when phone_number is passed to /events.

  // Reset all filters
  const resetFilters = () => {
    setDateRange({ start: "", end: "" });
    setSelectedGenres([]);
    setSearchTerm("");
    setSelectedOrganizers([]);
    setSelectedVenues([]);
    setPriceSort("none");
    setScoreSort("none");
    setSelectedCities([]);
    setShowStarredOnly(false);
    storedFiltersRef.current = {
      selectedCities: [],
      selectedGenres: [],
      selectedOrganizers: [],
      selectedVenues: [],
      searchTerm: "",
      priceSort: "none",
      scoreSort: "none",
      dateRange: { start: "", end: "" },
      hasChosenDates: true,
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
    <div className={`w-full max-w-full min-h-screen flex flex-col items-center pixel-grid ${
      darkMode ? 'text-sprout-text' : 'text-gray-900'
    } relative`}>
      {/* Modal Overlay - Only shown when login tooltip is visible */}
      {!isLoggedIn && showLoginTooltip && (
        <div 
          className="hidden md:block fixed inset-0 bg-black bg-opacity-5 z-40"
          onClick={closeLoginTooltip}
        />
      )}
    
      {/* Fixed top chrome: brand header + filters */}
      <div
        ref={chromeRef}
        className={`fixed top-0 left-0 right-0 z-30 ${
          darkMode ? 'bg-sprout-void' : 'bg-[#f4f7f5]'
        }`}
      >
      {/* Header */}
      <div className={`w-full border-b-2 ${
        darkMode ? 'bg-sprout-panel border-sprout-border' : 'bg-white border-gray-300'
      } relative`}>
        <div className="p-3 sm:p-4 flex justify-between items-center">
          <div className="flex items-center min-w-0 mr-2">
            <Link to="/events" aria-label="SproutMe home" className="flex items-center min-w-0">
              <img src={sproutIcon} alt="" className="pixel-icon h-8 w-8 mr-2 flex-shrink-0" />
              <span className={`font-pixel text-xl truncate ${
                darkMode ? 'text-sprout-lime' : 'text-green-700'
              }`}>SproutMe</span>
            </Link>
          </div>

          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={() => setShowAddEvent(true)}
              className="pixel-btn inline-flex items-center px-3 py-2 text-sm"
              aria-label="Add an event"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
              </svg>
              Add Event
            </button>
            <ThemeToggle />

            {isLoggedIn && (
              <span className={`font-read text-sm ${
                darkMode ? 'text-sprout-muted' : 'text-gray-600'
              } mr-2`}>
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
                className={`font-pixel text-sm px-3 py-2 border-2 ${
                  darkMode
                    ? 'border-sprout-sms text-sprout-sms'
                    : 'border-purple-500 text-purple-800'
                } inline-flex items-center`}
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
                className={`font-pixel text-sm px-3 py-2 border-2 ${
                  isLoggedIn
                    ? darkMode ? 'border-red-500 text-red-300' : 'border-red-500 text-red-700'
                    : darkMode ? 'border-sprout-sms text-sprout-sms' : 'border-purple-500 text-purple-800'
                }`}
              >
                {isLoggedIn ? 'Logout' : 'Login'}
              </button>

              {!isLoggedIn && showLoginTooltip && (
                <div
                  className={`absolute right-0 top-full mt-2 w-72 p-4 pixel-panel z-50 ${
                    darkMode ? 'text-sprout-text border-sprout-lime' : 'text-gray-800'
                  }`}
                  style={{ pointerEvents: 'auto' }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="relative overflow-hidden">
                    <div className="flex justify-between items-start mb-3">
                      <div className="font-pixel text-sm text-sprout-lime">Login to unlock features:</div>
                      <button
                        onClick={closeLoginTooltip}
                        className="text-gray-500 hover:text-gray-700 p-1"
                        aria-label="Close tooltip"
                        type="button"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                        </svg>
                      </button>
                    </div>
                    <ul className="font-read text-sm space-y-2">
                      <li>Save your favorite events</li>
                      <li>Quick access across devices</li>
                    </ul>
                    <button
                      type="button"
                      onClick={() => {
                        closeLoginTooltip();
                        navigate('/login');
                      }}
                      className="pixel-btn w-full mt-3 py-2 text-sm"
                    >
                      Log in
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Mobile hamburger */}
          <button
            type="button"
            className={`md:hidden p-2 ${
              darkMode ? 'text-sprout-text' : 'text-gray-800'
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
          <div className={`md:hidden border-t-2 px-4 py-3 flex flex-col gap-2 ${
            darkMode ? 'border-sprout-border bg-sprout-panel' : 'border-gray-300 bg-white'
          }`}>
            {isLoggedIn && (
              <p className={`font-read text-sm ${darkMode ? 'text-sprout-muted' : 'text-gray-600'} px-1`}>
                Welcome, {userName || "User"}
              </p>
            )}
            <button
              type="button"
              onClick={() => {
                setShowMobileNav(false);
                setShowAddEvent(true);
              }}
              className="pixel-btn mobile-nav-item py-3 px-4 flex items-center justify-center w-full"
            >
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
                className={`mobile-nav-item font-pixel py-3 px-4 border-2 flex items-center justify-center w-full ${
                  darkMode ? 'border-sprout-sms text-sprout-sms' : 'border-purple-500 text-purple-800'
                }`}
              >
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
              className={`mobile-nav-item font-pixel py-3 px-4 border-2 flex items-center justify-center w-full ${
                isLoggedIn
                  ? darkMode ? 'border-red-500 text-red-300' : 'border-red-500 text-red-700'
                  : darkMode ? 'border-sprout-sms text-sprout-sms' : 'border-purple-500 text-purple-800'
              }`}
            >
              {isLoggedIn ? 'Logout' : 'Login'}
            </button>
          </div>
        )}
      </div>

      <QuickFilterBar
        dateRange={dateRange}
        onDatePreset={applyDatePreset}
        selectedCities={selectedCities}
        onRemoveCity={(city) =>
          setSelectedCities((prev) => prev.filter((item) => item !== city))
        }
        onOpenCities={() => {
          setShowFilters(false);
          openFilterModal("cities");
        }}
        selectedGenres={selectedGenres}
        onRemoveGenre={(genre) =>
          setSelectedGenres((prev) => prev.filter((item) => item !== genre))
        }
        onOpenGenres={() => {
          setShowFilters(false);
          openFilterModal("genres");
        }}
        onOpenFilters={() => setShowFilters(true)}
        filterCount={filterCount}
        onClear={resetFilters}
        chatgptHref={CHATGPT_HREF}
      />
      </div>

      <div
        className="w-full flex flex-col items-center"
        style={{ paddingTop: chromeHeight || undefined }}
      >
      {/* Compact tagline */}
      <div className="w-full max-w-5xl px-4 mb-3 md:mb-4 text-center mt-4">
        <p className={`hidden md:block font-read text-sm md:text-base ${
          darkMode ? 'text-sprout-muted' : 'text-gray-600'
        }`}>
          Discover the best electronic music events across North America
        </p>
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
        setPriceSort={(value) => {
          setPriceSort(value);
          if (value !== "none") setScoreSort("none");
        }}
        scoreSort={scoreSort}
        setScoreSort={(value) => {
          setScoreSort(value);
          if (value !== "none") setPriceSort("none");
        }}
        selectedGenres={selectedGenres}
        selectedOrganizers={selectedOrganizers}
        selectedVenues={selectedVenues}
        selectedCities={selectedCities}
        openFilterModal={openFilterModal}
        events={events}
        filteredEvents={displayedEvents}
        totalEvents={totalEvents}
        loadedCount={events.length}
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
      
      <div className="w-full max-w-5xl px-4 sm:px-5 pb-28 flex-1 flex flex-col min-w-0">
        <EventList
          loading={loading}
          loadingMore={loadingMore}
          error={error}
          events={displayedEvents}
          hasMore={hasMore}
          totalEvents={totalEvents}
          onLoadMore={loadMoreEvents}
          onFavoriteEvent={handleFavoriteEvent}
          showStarredOnly={showStarredOnly}
          emptyHints={emptyHints}
        />
      </div>
      </div>
      
      <LoginPrompt
        open={showLoginPrompt}
        onClose={() => setShowLoginPrompt(false)}
      />

      <AddEventModal
        open={showAddEvent}
        onClose={() => setShowAddEvent(false)}
        apiUrl={apiUrl}
        onAdd={(event) => {
          setEvents((prev) => [event, ...prev]);
          setTotalEvents((prev) => prev + 1);
        }}
      />
      
      <ContactFooter />
    </div>
  );
};

export default EventsPage;