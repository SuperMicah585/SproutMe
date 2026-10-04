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
  emptyHints = [],
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
              className={`page-skeleton h-36 border-2 ${
                darkMode ? 'bg-sprout-panel border-sprout-border' : 'bg-white border-gray-300'
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
      <div className={`pixel-panel p-4 ${darkMode ? 'text-red-300' : 'text-red-700'}`}>
        {error}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className={`pixel-panel p-6 text-center ${darkMode ? 'text-sprout-text' : 'text-gray-800'}`}>
        <p className="font-read text-lg font-medium">No events found matching your filters.</p>
        <p className={`font-read mt-2 ${darkMode ? 'text-sprout-muted' : 'text-gray-600'}`}>
          {showStarredOnly
            ? "You don't have any favorited events matching your current filters."
            : "Try widening the date range or clearing a filter."}
        </p>
        {emptyHints?.length > 0 && (
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {emptyHints.map((hint) => (
              <button
                key={hint.id}
                type="button"
                onClick={hint.onClick}
                className="pixel-btn px-3 py-2 text-sm"
              >
                {hint.label}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <>
      {totalEvents > 0 && (
        <p className={`font-pixel text-sm mb-3 ${darkMode ? 'text-sprout-muted' : 'text-gray-500'}`}>
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
          <p className={`font-pixel text-sm ${darkMode ? 'text-sprout-muted' : 'text-gray-400'}`}>
            End of results
          </p>
        )}
      </div>
    </>
  );
});

export default EventList;
