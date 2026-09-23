import React, { memo, useEffect, useRef } from 'react';
import EventCard from './EventCard';
import { useTheme } from '../../context/ThemeContext';

const getEventKey = (event, index) => {
  return `${event.id || event.event_name}-${event.venue}-${event.date}-${event.is_favorite ? 'fav' : 'nofav'}-${index}`;
};

const EventList = memo(({
  loading,
  loadingMore = false,
  error,
  events,
  hasMore = false,
  onLoadMore,
  onFavoriteEvent,
  showStarredOnly,
  totalEvents = 0,
}) => {
  const { darkMode } = useTheme();
  const sentinelRef = useRef(null);
  const loadMoreRef = useRef(onLoadMore);

  useEffect(() => {
    loadMoreRef.current = onLoadMore;
  }, [onLoadMore]);

  useEffect(() => {
    if (loading || !hasMore || !onLoadMore) return undefined;

    const node = sentinelRef.current;
    if (!node) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          loadMoreRef.current?.();
        }
      },
      { root: null, rootMargin: '400px', threshold: 0 }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [loading, hasMore, onLoadMore, events.length]);

  if (loading) {
    return (
      <div className="w-full min-h-[60vh]">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              key={index}
              className={`page-skeleton h-36 rounded-xl border ${
                darkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
              }`}
            />
          ))}
        </div>
        <div className="flex justify-center py-6">
          <div className="page-spinner" aria-label="Loading events" />
        </div>
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

  if (events.length === 0) {
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
      {totalEvents > 0 && (
        <p className={`text-sm mb-3 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
          Showing {events.length.toLocaleString()} of {totalEvents.toLocaleString()} events
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {events.map((event, index) => {
          const eventKey = getEventKey(event, index);
          return (
            <div key={eventKey} className="h-full">
              <EventCard
                event={event}
                index={index}
                onFavorite={onFavoriteEvent}
              />
            </div>
          );
        })}
      </div>

      <div ref={sentinelRef} className="w-full py-4 flex justify-center min-h-[2rem]">
        {loadingMore && (
          <div className="page-spinner" aria-label="Loading more events" />
        )}
        {!hasMore && events.length > 0 && (
          <p className={`text-sm ${darkMode ? 'text-gray-500' : 'text-gray-400'}`}>
            End of results
          </p>
        )}
      </div>
    </>
  );
});

export default EventList;
