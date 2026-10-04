import React, { memo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext';
import { trackEvent } from '../../utils/analytics';
import { eventPath } from '../../utils/seoPaths';
import { CHATGPT_HREF } from './ChatGptWidget';

const EventCard = memo(({ event, index, onFavorite, readOnly = false }) => {
  const { darkMode } = useTheme();

  if (!event) {
    return (
      <div className={`pixel-panel p-4 min-h-[11.5rem] ${darkMode ? 'text-red-300' : 'text-red-600'}`}>
        <p className="font-read">Error: Event data is missing</p>
      </div>
    );
  }

  const safelyTrim = (str) => (str && typeof str === 'string') ? str.trim() : str;
  const eventName = safelyTrim(event.event_name) || 'Unnamed Event';
  const venue = safelyTrim(event.venue) || 'Unknown Venue';
  const date = safelyTrim(event.date) || 'Unknown Date';
  const ticketInfo = safelyTrim(event.ticket_info) || '';
  const genre = safelyTrim(event.genre) || '';
  const eventUrl = safelyTrim(event.event_url) || '';
  const imageUrl = safelyTrim(event.image_url) || '';
  const detailPath = event?.id != null ? eventPath(event) : null;
  const isFavorite = !!event.is_favorite;
  const genreTags = genre
    ? genre.split(/[,/;|]+/).map((g) => g.trim()).filter(Boolean).slice(0, 2)
    : [];

  const handleFavoriteClick = useCallback((e) => {
    e.stopPropagation();
    onFavorite(event, index, e);
  }, [event, index, onFavorite]);

  return (
    <div
      className={`pixel-panel h-full min-h-[11.5rem] p-3 sm:p-4 flex flex-col gap-2 overflow-hidden ${
        darkMode ? 'text-sprout-text' : 'text-gray-900'
      }`}
    >
      {imageUrl ? (
        <div className="-mx-3 sm:-mx-4 -mt-3 sm:-mt-4 mb-1 overflow-hidden border-b-2 border-sprout-border">
          <img
            src={imageUrl}
            alt=""
            loading="lazy"
            className="w-full h-28 sm:h-32 object-cover"
            onError={(e) => {
              e.currentTarget.parentElement.style.display = 'none';
            }}
          />
        </div>
      ) : null}

      <div className="flex items-center gap-2 min-w-0">
        <p
          className={`font-read flex-1 min-w-0 text-xs sm:text-sm truncate ${
            darkMode ? 'text-sprout-muted' : 'text-gray-600'
          }`}
          title={`${date} · ${venue}${ticketInfo && ticketInfo !== 'N/A' ? ` · ${ticketInfo}` : ''}`}
        >
          <span className={darkMode ? 'text-sprout-lime' : 'text-green-700'}>{date}</span>
          <span className="mx-1.5 opacity-40">·</span>
          <span>{venue}</span>
          {ticketInfo && ticketInfo !== 'N/A' && (
            <>
              <span className="mx-1.5 opacity-40">·</span>
              <span className={darkMode ? 'text-amber-200' : 'text-amber-800'}>{ticketInfo}</span>
            </>
          )}
        </p>
        {!readOnly && (
          <button
            onClick={handleFavoriteClick}
            className="focus:outline-none bg-transparent p-1 flex-shrink-0"
            aria-label={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
            data-favorite={isFavorite ? 'true' : 'false'}
            aria-pressed={isFavorite}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6"
              fill={isFavorite ? '#FBBF24' : 'none'}
              viewBox="0 0 24 24"
              stroke="#FBBF24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
            </svg>
          </button>
        )}
      </div>

      {detailPath ? (
        <Link
          to={detailPath}
          onClick={() =>
            trackEvent('select_content', {
              content_type: 'event',
              item_id: String(event.id),
            })
          }
          className={`font-read font-semibold text-base sm:text-lg leading-tight truncate hover:underline ${
            darkMode ? 'text-sprout-text' : 'text-gray-900'
          }`}
          title={eventName}
        >
          {eventName}
        </Link>
      ) : (
        <h3
          className={`font-read font-semibold text-base sm:text-lg leading-tight truncate ${
            darkMode ? 'text-sprout-text' : 'text-gray-900'
          }`}
          title={eventName}
        >
          {eventName}
        </h3>
      )}

      <div className="flex flex-nowrap gap-1.5 overflow-hidden min-h-[1.25rem]">
        {genreTags.map((tag) => (
          <span key={tag} className="pixel-tag truncate max-w-[9rem]" title={tag}>
            {tag}
          </span>
        ))}
      </div>

      <div className="mt-auto pt-1 flex gap-2 flex-nowrap">
        {eventUrl ? (
          <a
            href={eventUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => trackEvent('click', {
              outbound: true,
              link_url: eventUrl,
              link_text: eventName,
              content_type: 'event',
            })}
            className="pixel-btn inline-flex items-center justify-center px-3 py-2 text-sm flex-shrink-0"
          >
            Tickets
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="w-3.5 h-3.5 ml-1.5" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        ) : null}
        <a
          href={CHATGPT_HREF}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => trackEvent('generate_lead', { method: 'chatgpt', source: 'event_card' })}
          className={`font-pixel inline-flex items-center justify-center px-3 py-2 text-sm border-2 truncate ${
            darkMode
              ? 'border-sprout-sms text-sprout-sms hover:bg-purple-950/40'
              : 'border-purple-400 text-purple-800 hover:bg-purple-50'
          }`}
          style={{ borderRadius: 2 }}
          aria-label={`Ask ChatGPT about ${eventName}`}
        >
          Ask ChatGPT
        </a>
      </div>
    </div>
  );
}, (prevProps, nextProps) => (
  prevProps.readOnly === nextProps.readOnly &&
  prevProps.index === nextProps.index &&
  prevProps.event.is_favorite === nextProps.event.is_favorite &&
  prevProps.event.id === nextProps.event.id &&
  prevProps.event.event_name === nextProps.event.event_name &&
  prevProps.event.venue === nextProps.event.venue &&
  prevProps.event.date === nextProps.event.date &&
  prevProps.event.ticket_info === nextProps.event.ticket_info &&
  prevProps.event.genre === nextProps.event.genre &&
  prevProps.event.event_url === nextProps.event.event_url &&
  prevProps.event.image_url === nextProps.event.image_url
));

export default EventCard;
