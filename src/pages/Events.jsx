import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
// Update the hash function to use browser's WebCrypto API
export const hashPhoneNumber = async (phoneNumber) => {
  // Convert the phone number to an ArrayBuffer
  const encoder = new TextEncoder();
  const data = encoder.encode(phoneNumber);
  
  // Hash the data using SHA-256
  const hashBuffer = await window.crypto.subtle.digest('SHA-256', data);
  
  // Convert the hash to a hex string
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
};

// Update the verification function to be async as well
export const verifyPhoneHash = async (phoneNumber, hash) => {
  const generatedHash = await hashPhoneNumber(phoneNumber);
  return generatedHash === hash;
};

const EventsPage = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const { phoneHash } = useParams();
  const [events, setEvents] = useState([]);
  const [filteredEvents, setFilteredEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actualPhoneNumber, setActualPhoneNumber] = useState(null);
  const [name, setName] = useState("");

  // Filter states
  const [dateRange, setDateRange] = useState({ start: "", end: "" });
  const [selectedGenres, setSelectedGenres] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedOrganizers, setSelectedOrganizers] = useState([]);
  const [selectedVenues, setSelectedVenues] = useState([]);
  const [priceSort, setPriceSort] = useState("none"); // "none", "asc", "desc"
  const [selectedCities, setSelectedCities] = useState([]);
  const [availableCities, setAvailableCities] = useState([]);
  
  // For dropdown filters
  const [availableGenres, setAvailableGenres] = useState([]);
  const [availableOrganizers, setAvailableOrganizers] = useState([]);
  const [availableVenues, setAvailableVenues] = useState([]);
  
  // Mobile UI states
  const [showFilters, setShowFilters] = useState(false);
  const [activeFilterModal, setActiveFilterModal] = useState(null); // null, "genres", "organizers", "venues"
  const [filterCount, setFilterCount] = useState(0);


  useEffect(() => {
    if(phoneHash) {
      fetchEvents();
      getNameByPhoneHash(phoneHash);
    }
  }, [phoneHash]);

  // Apply filters whenever filter states or events change
  useEffect(() => {
    applyFilters();
  }, [events, dateRange, selectedGenres, searchTerm, selectedOrganizers, selectedVenues, priceSort]);

  // Extract unique filter options when events are loaded
  useEffect(() => {
    if (events.length > 0) {
      // Extract unique genres
      const genres = [...new Set(events.flatMap(event => 
        event.genre.split(', ').map(g => g.trim())
      ))].sort();
      
      // Extract unique organizers
      const organizers = [...new Set(events.map(event => 
        event.organizer.trim()
      ))].filter(org => org).sort();
      
      // Extract unique venues
      const venues = [...new Set(events.map(event => 
        event.venue.trim()
      ))].sort();
      
      setAvailableGenres(genres);
      setAvailableOrganizers(organizers);
      setAvailableVenues(venues);
    }
  }, [events]);

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
    
    setFilterCount(count);
  }, [dateRange, selectedGenres, searchTerm, selectedOrganizers, selectedVenues, selectedCities, priceSort]);

  // Parse date string to Date object
  const parseEventDate = (rawDate) => {
    const [year, month, day] = rawDate.split('/').map(Number);
    return new Date(year, month - 1, day);
  };

  // Extract ticket price from ticket_info
  const extractPrice = (ticketInfo) => {
    const priceMatch = ticketInfo.match(/\$(\d+(?:-\d+)?)/);
    if (priceMatch) {
      const priceStr = priceMatch[1];
      if (priceStr.includes('-')) {
        return parseFloat(priceStr.split('-')[0]);
      }
      return parseFloat(priceStr);
    }
    return 0; // Default price if no price found
  };

  useEffect(() => {
    if (events.length > 0) {
      // Extract unique cities
      const cities = [...new Set(events.map(event => 
        event.city?.trim()
      ))].filter(city => city).sort();
      
      setAvailableCities(cities);
      
      // Your existing code for genres, organizers, venues...
    }
  }, [events]);

  const applyFilters = () => {
    let result = [...events];
    
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
    
    // Apply genre filter
    if (selectedGenres.length > 0) {
      result = result.filter(event => {
        const eventGenres = event.genre.split(', ').map(g => g.trim());
        return selectedGenres.some(genre => eventGenres.includes(genre));
      });
    }

        // Apply city filter
    if (selectedCities.length > 0) {
      result = result.filter(event => 
        selectedCities.includes(event.city?.trim())
      );
    }
        
    // Apply search term filter (for event name)
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      result = result.filter(event => 
        event.event_name.toLowerCase().includes(term)
      );
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
    
    // Apply price sorting
    if (priceSort !== "none") {
      result.sort((a, b) => {
        const priceA = extractPrice(a.ticket_info);
        const priceB = extractPrice(b.ticket_info);
        return priceSort === "asc" ? priceA - priceB : priceB - priceA;
      });
    }
    
    setFilteredEvents(result);
  };

  async function fetchEvents() {
    if (!phoneHash) {
      setError("Phone hash not provided");
      setLoading(false);
      return;
    }

    try {
      const url = `${apiUrl}/events?phone_hash=${encodeURIComponent(phoneHash)}`;
      
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
      const eventsData = data.data || [];
      setEvents(eventsData);
      setFilteredEvents(eventsData);
      
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

  async function getNameByPhoneHash(phoneHash) {
    const url = `${apiUrl}/get_name`;
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ phone_hash: phoneHash }),
      });

      const data = await response.json();

      if (response.ok) {
        setName(data.name + "'s");
      } else {
        throw new Error(data.error || 'Error retrieving name');
      }
    } catch (error) {
      console.error('Error:', error);
      return null;
    }
  }

  // Helper function to toggle item in array
  const toggleArrayItem = (array, item) => {
    return array.includes(item)
      ? array.filter(i => i !== item)
      : [...array, item];
  };

  // Reset all filters
  const resetFilters = () => {
    setDateRange({ start: "", end: "" });
    setSelectedGenres([]);
    setSearchTerm("");
    setSelectedOrganizers([]);
    setSelectedVenues([]);
    setSelectedCities([]);
    setPriceSort("none");
    setActiveFilterModal(null);
  };

  // Open filter modal
  const openFilterModal = (modalName) => {
    if (activeFilterModal === modalName) {
      setActiveFilterModal(null);
    } else {
      setActiveFilterModal(modalName);
    }
  };

  return (
    <div className="w-screen h-screen flex flex-col items-center bg-gray-50 overflow-y-scroll">
      <div className="text-3xl md:text-4xl font-bold text-green-600 mb-2 mt-4 md:mt-6">Upcoming Events</div>
      <div className="text-lg md:text-xl font-medium text-gray-700 mb-2 px-4 text-center">
        {actualPhoneNumber ? `Events for ${actualPhoneNumber}` : `${name} upcoming events`}
      </div>
      
      {/* Filters Toggle Button */}
      <div className="w-full max-w-5xl px-4 flex justify-between items-center mb-4">
        <button 
          onClick={() => setShowFilters(!showFilters)}
          className="bg-green-500 hover:bg-green-600 text-white font-medium py-2 px-4 rounded-lg transition-colors flex items-center"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M3 3a1 1 0 011-1h12a1 1 0 011 1v3a1 1 0 01-.293.707L12 11.414V15a1 1 0 01-.293.707l-2 2A1 1 0 018 17v-5.586L3.293 6.707A1 1 0 013 6V3z" clipRule="evenodd" />
          </svg>
          Filters
          {filterCount > 0 && (
            <span className="ml-2 bg-white text-green-600 rounded-full w-5 h-5 flex items-center justify-center text-xs font-bold">
              {filterCount}
            </span>
          )}
        </button>
        
        {filterCount > 0 && (
          <button
            onClick={resetFilters}
            className="text-green-600 font-medium bg-white"
          >
            Clear All
          </button>
        )}
      </div>
      
      {/* Mobile-Friendly Filters */}
      {showFilters && (
        <div className="w-full max-w-5xl px-4 mb-6">
          {/* Top filters that are always visible */}
          <div className="bg-white rounded-xl shadow-md p-4 mb-2">
            {/* Date Range Filter */}
            <div className="mb-4 text-black bg-white">
              <label className="block text-gray-700 text-sm font-bold mb-2 text-black bg-white">Date Range</label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-xs text-gray-500 text-black bg-white mb-1">Start Date</div>
                  <input
                    type="date"
                    className="border rounded-md p-2 w-full text-black bg-white"
                    value={dateRange.start}
                    onChange={(e) => setDateRange({ ...dateRange, start: e.target.value })}
                  />
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1 text-black bg-white">End Date</div>
                  <input
                    type="date"
                    className="border rounded-md p-2 w-full text-black bg-white"
                    value={dateRange.end}
                    onChange={(e) => setDateRange({ ...dateRange, end: e.target.value })}
                  />
                </div>
              </div>
            </div>
            
            {/* Event Name Search */}
            <div className="mb-4">
              <label className="block text-gray-700 text-sm font-bold mb-2 text-black bg-white">Event Name</label>
              <input
                type="text"
                className="border rounded-md p-2 w-full text-black bg-white"
                placeholder="Search by event name..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            
            {/* Price Sort */}
            <div>
              <label className="block text-gray-700 text-sm font-bold mb-2 text-black bg-white">Sort by Price</label>
              <select
                className="border rounded-md p-2 w-full text-black bg-white"
                value={priceSort}
                onChange={(e) => setPriceSort(e.target.value)}
              >
                <option value="none">No Sorting</option>
                <option value="asc">Price: Low to High</option>
                <option value="desc">Price: High to Low</option>
              </select>
            </div>
          </div>
          
          {/* Category filter buttons */}
          <div className="grid grid-cols-4 gap-2 mb-2 text-black bg-white">
            <button
              onClick={() => openFilterModal("genres")}
              className={`p-3 rounded-lg flex flex-col items-center justify-center ${
                selectedGenres.length > 0 
                  ? 'bg-green-500 text-white' 
                  : 'bg-white shadow-md'
              }`}
            >
              <span className="text-sm font-bold">Genres</span>
              {selectedGenres.length > 0 && (
                <span className="text-xs mt-1">
                  {selectedGenres.length} selected
                </span>
              )}
            </button>
            
            <button
              onClick={() => openFilterModal("organizers")}
              className={`p-3 rounded-lg flex flex-col items-center justify-center ${
                selectedOrganizers.length > 0 
                  ? 'bg-green-500 text-white' 
                  : 'bg-white shadow-md'
              }`}
            >
              <span className="text-sm font-bold">Organizers</span>
              {selectedOrganizers.length > 0 && (
                <span className="text-xs mt-1">
                  {selectedOrganizers.length} selected
                </span>
              )}
            </button>
            
            <button
              onClick={() => openFilterModal("venues")}
              className={`p-3 rounded-lg flex flex-col items-center justify-center ${
                selectedVenues.length > 0 
                  ? 'bg-green-500 text-white' 
                  : 'bg-white shadow-md'
              }`}
            >
              <span className="text-sm font-bold">Venues</span>
              {selectedVenues.length > 0 && (
                <span className="text-xs mt-1">
                  {selectedVenues.length} selected
                </span>
              )}
            </button>

          <button
            onClick={() => openFilterModal("cities")}
            className={`p-3 rounded-lg flex flex-col items-center justify-center ${
              selectedCities.length > 0 
                ? 'bg-green-500 text-white' 
                : 'bg-white shadow-md'
            }`}
          >
            <span className="text-sm font-bold">Cities</span>
            {selectedCities.length > 0 && (
              <span className="text-xs mt-1">
                {selectedCities.length} selected
              </span>
            )}
          </button>
          </div>
        </div>
      )}
      
      {/* Filter Modals */}
      {activeFilterModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl w-full max-w-md max-h-[80vh] flex flex-col">
            <div className="p-4 border-b flex justify-between items-center ">
                  <h3 className="font-bold text-lg text-black bg-white">
        {activeFilterModal === "genres" ? "Select Genres" : 
        activeFilterModal === "organizers" ? "Select Organizers" : 
        activeFilterModal === "venues" ? "Select Venues" :
        "Select Cities"}
      </h3>
              <button 
                onClick={() => setActiveFilterModal(null)}
                className="text-gray-500 bg-white hover:text-gray-700"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            <div className="overflow-y-auto p-4 flex-grow">
              {activeFilterModal === "genres" && (
                <div className="space-y-2 max-h-96 text-black bg-white">
                  {availableGenres.map((genre) => (
                    <div 
                      key={genre}
                      onClick={() => setSelectedGenres(toggleArrayItem(selectedGenres, genre))}
                      className={`p-3 rounded-lg flex items-center ${
                        selectedGenres.includes(genre)
                          ? 'bg-green-100 border border-green-500'
                          : 'bg-gray-50 border border-gray-200'
                      }`}
                    >
                      <div className={`w-5 h-5 rounded border flex items-center justify-center mr-3 ${
                        selectedGenres.includes(genre)
                          ? 'bg-green-500 border-green-500'
                          : 'border-gray-400'
                      }`}>
                        {selectedGenres.includes(genre) && (
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        )}
                      </div>
                      <span>{genre}</span>
                    </div>
                  ))}
                </div>
              )}


              {activeFilterModal === "cities" && (
                <div className="space-y-2 max-h-96 text-black bg-white">
                  {availableCities.map((city) => (
                    <div 
                      key={city}
                      onClick={() => setSelectedCities(toggleArrayItem(selectedCities, city))}
                      className={`p-3 rounded-lg flex items-center ${
                        selectedCities.includes(city)
                          ? 'bg-green-100 border border-green-500'
                          : 'bg-gray-50 border border-gray-200'
                      }`}
                    >
                      <div className={`w-5 h-5 rounded border flex items-center justify-center mr-3 ${
                        selectedCities.includes(city)
                          ? 'bg-green-500 border-green-500'
                          : 'border-gray-400'
                      }`}>
                        {selectedCities.includes(city) && (
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        )}
                      </div>
                      <span>{city}</span>
                    </div>
                  ))}
                </div>
              )}
              
              {activeFilterModal === "organizers" && (
                <div className="space-y-2 max-h-96 text-black bg-white">
                  {availableOrganizers.map((organizer) => (
                    <div 
                      key={organizer}
                      onClick={() => setSelectedOrganizers(toggleArrayItem(selectedOrganizers, organizer))}
                      className={`p-3 rounded-lg flex items-center ${
                        selectedOrganizers.includes(organizer)
                          ? 'bg-green-100 border border-green-500'
                          : 'bg-gray-50 border border-gray-200'
                      }`}
                    >
                      <div className={`w-5 h-5 rounded border flex items-center justify-center mr-3 ${
                        selectedOrganizers.includes(organizer)
                          ? 'bg-green-500 border-green-500'
                          : 'border-gray-400'
                      }`}>
                        {selectedOrganizers.includes(organizer) && (
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        )}
                      </div>
                      <span>{organizer || "Unknown"}</span>
                    </div>
                  ))}
                </div>
              )}
              
              {activeFilterModal === "venues" && (
                <div className="space-y-2 max-h-96 text-black bg-white">
                  {availableVenues.map((venue) => (
                    <div 
                      key={venue}
                      onClick={() => setSelectedVenues(toggleArrayItem(selectedVenues, venue))}
                      className={`p-3 rounded-lg flex items-center ${
                        selectedVenues.includes(venue)
                          ? 'bg-green-100 border border-green-500'
                          : 'bg-gray-50 border border-gray-200'
                      }`}
                    >
                      <div className={`w-5 h-5 rounded border flex items-center justify-center mr-3 ${
                        selectedVenues.includes(venue)
                          ? 'bg-green-500 border-green-500'
                          : 'border-gray-400'
                      }`}>
                        {selectedVenues.includes(venue) && (
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        )}
                      </div>
                      <span>{venue}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            <div className="p-4 border-t flex justify-between">
                      <button
            onClick={() => {
              if (activeFilterModal === "genres") setSelectedGenres([]);
              if (activeFilterModal === "organizers") setSelectedOrganizers([]);
              if (activeFilterModal === "venues") setSelectedVenues([]);
              if (activeFilterModal === "cities") setSelectedCities([]);
            }}
            className="text-gray-600 font-medium bg-white py-2 px-4"
          >
            Clear
          </button>
              <button
                onClick={() => setActiveFilterModal(null)}
                className="bg-green-500 hover:bg-green-600 text-white font-medium py-2 px-6 rounded-lg"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Event Count */}
      <div className="w-full max-w-5xl px-4 mb-2">
        <div className="text-gray-600 text-sm">
          Showing {filteredEvents.length} of {events.length} events
        </div>
      </div>
      
      {/* Events List */}
      <div className="w-full max-w-5xl px-4 pb-6">
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-12 h-12 border-4 border-green-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : error ? (
          <div className="bg-red-100 border-2 border-red-300 text-red-700 p-4 rounded-lg">
            {error}
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="bg-yellow-50 border-2 border-yellow-300 text-yellow-700 p-6 rounded-xl text-center">
            <p className="text-lg font-medium">No events found matching your filters.</p>
            <p className="mt-2">Try adjusting your filters to see more results.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredEvents.map((event, index) => (
              <div
                key={index}
                className="bg-white p-4 rounded-xl shadow-md border border-green-200 transition-all hover:shadow-lg hover:border-green-400"
              >
                <h3 className="font-bold text-lg text-gray-800 mb-2 font-unlock">{event.event_name.trim()}</h3>
                
                <div className="space-y-1 mb-3 text-sm">
                  <div className="flex">
                    <span className="font-medium text-gray-600 w-20">Date:</span>
                    <span className="text-gray-800">{event.date.trim()}</span>
                  </div>
                  
                  <div className="flex">
                    <span className="font-medium text-gray-600 w-20">Venue:</span>
                    <span className="text-gray-800">{event.venue.trim()}</span>
                  </div>
                  
                  <div className="flex flex-wrap items-center">
                    <span className="font-medium text-gray-600 w-20">Genre:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {event.genre.split(', ').map((g, i) => (
                        <span key={i} className="bg-purple-100 text-purple-800 px-2 py-0.5 rounded text-xs">{g.trim()}</span>
                      ))}
                    </div>
                  </div>

                  <div className="flex">
                    <span className="font-medium text-gray-600 w-20">Tickets:</span>
                    <span className="text-gray-800">{event.ticket_info.trim()}</span>
                  </div>

                  <div className="flex">
                    <span className="font-medium text-gray-600 w-20">Organizer:</span>
                    <span className="text-gray-800">{event.organizer.trim() || "N/A"}</span>
                  </div>
                </div>
                
                {event.event_url && (
                  <a
                    href={event.event_url.trim()}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block w-full text-center bg-green-500 hover:bg-green-600 hover:text-white text-white font-medium py-2 rounded-lg transition-colors"
                  >
                    View Event
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default EventsPage;