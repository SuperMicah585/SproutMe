import React, { memo, useEffect, useRef } from 'react';
import EventCard from './EventCard';

const getEventKey = (event, index) => {
  return `${event.event_name}-${event.venue}-${event.date}-${event.is_favorite ? 'fav' : 'nofav'}-${index}`;
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
  totalCount = 0,
}) => {
  const sentinelRef = useRef(null);
  const loadingMoreRef = useRef(loadingMore);
  const hasMoreRef = useRef(hasMore);

  useEffect(() => {
    loadingMoreRef.current = loadingMore;
  }, [loadingMore]);

  useEffect(() => {
    hasMoreRef.current = hasMore;
  }, [hasMore]);

  useEffect(() => {
    if (loading || !onLoadMore) return undefined;
    const node = sentinelRef.current;
    if (!node) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry?.isIntersecting) return;
        if (!hasMoreRef.current || loadingMoreRef.current) return;
        onLoadMore();
      },
      { root: null, rootMargin: '400px', threshold: 0 }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [loading, onLoadMore, events.length]);

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

      <div ref={sentinelRef} className="w-full py-4 flex flex-col items-center gap-2">
        {loadingMore && (
          <div className="w-8 h-8 border-4 border-green-500 border-t-transparent rounded-full animate-spin" />
        )}
        {!hasMore && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Showing all {totalCount || events.length} events
          </p>
        )}
      </div>
    </>
  );
});

export default EventList;
