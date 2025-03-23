import React, { memo, useRef, useEffect } from 'react';
import EventCard from './EventCard';
import Pagination from './Pagination';

// Helper function to check if an element is in viewport
const isElementInViewport = (el) => {
  if (!el) return false;
  const rect = el.getBoundingClientRect();
  return (
    rect.top >= 0 &&
    rect.left >= 0 &&
    rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
    rect.right <= (window.innerWidth || document.documentElement.clientWidth)
  );
};

// Generate a unique key for each event that includes its favorite status
const getEventKey = (event, index) => {
  return `${event.event_name}-${event.venue}-${event.date}-${event.is_favorite ? 'fav' : 'nofav'}-${index}`;
};

const EventList = memo(({
  loading,
  error,
  filteredEvents,
  displayedEvents,
  currentPage,
  eventsPerPage,
  onPageChange,
  onFavoriteEvent,
  showStarredOnly
}) => {
  // Ref to track rendered event cards
  const eventRefs = useRef({});
  
  // Setup intersection observer for virtualizing content
  useEffect(() => {
    if (loading) return;
    
    const options = {
      root: null,
      rootMargin: '200px',
      threshold: 0
    };
    
    // Create an observer instance
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        const eventId = entry.target.dataset.eventId;
        if (entry.isIntersecting) {
          // Render full content when visible
          if (eventRefs.current[eventId]) {
            eventRefs.current[eventId].classList.remove('opacity-0');
            eventRefs.current[eventId].classList.add('opacity-100');
          }
        } else {
          // Reduce content details when not visible
          if (eventRefs.current[eventId] && !isElementInViewport(eventRefs.current[eventId])) {
            eventRefs.current[eventId].classList.remove('opacity-100');
            eventRefs.current[eventId].classList.add('opacity-0');
          }
        }
      });
    }, options);
    
    // Observe all event cards
    Object.values(eventRefs.current).forEach(ref => {
      if (ref) observer.observe(ref);
    });
    
    return () => {
      // Cleanup - disconnect observer when component unmounts
      observer.disconnect();
    };
  }, [displayedEvents, loading]);
  
  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="w-12 h-12 border-4 border-green-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-100 border-2 border-red-300 text-red-700 p-4 rounded-lg">
        {error}
      </div>
    );
  }

  if (filteredEvents.length === 0) {
    return (
      <div className="bg-yellow-50 border-2 border-yellow-300 text-yellow-700 p-6 rounded-xl text-center">
        <p className="text-lg font-medium">No events found matching your filters.</p>
        <p className="mt-2">
          {showStarredOnly 
            ? "You don't have any favorited events matching your current filters. Try adjusting your filters or star some events first." 
            : "Try adjusting your filters to see more results."}
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {displayedEvents.map((event, index) => {
          // Create a unique key for each event that includes its favorite status
          const eventKey = getEventKey(event, index);
          
          return (
            <div 
              key={eventKey}
              ref={el => {
                eventRefs.current[eventKey] = el;
              }}
              data-event-id={eventKey}
              className="transition-opacity duration-300"
            >
              <EventCard 
                event={event} 
                index={index}
                onFavorite={onFavoriteEvent}
              />
            </div>
          );
        })}
      </div>
      
      {/* Bottom pagination only */}
      {filteredEvents.length > eventsPerPage && (
        <Pagination
          currentPage={currentPage}
          totalItems={filteredEvents.length}
          itemsPerPage={eventsPerPage}
          onPageChange={onPageChange}
        />
      )}
    </>
  );
});

export default EventList; 