import { useEffect, useState } from "react";
import { Link, useParams, Navigate } from "react-router-dom";
import { useTheme } from "../context/ThemeContext";
import ContactFooter from "../components/events/ContactFooter";
import ThemeToggle from "../components/events/ThemeToggle";
import sproutIcon from "./Components/sprout_icon.png";
import { trackEvent } from "../utils/analytics";
import { applyDocumentSeo, upsertJsonLd, clearJsonLd } from "../components/Seo";
import {
  cityHubPath,
  eventPath,
  eventSeoMeta,
  eventSlug,
  SITE_URL,
} from "../utils/seoPaths";
import { CHATGPT_HREF } from "../components/events/ChatGptWidget";

const musicEventJsonLd = (event) => {
  if (!event) return null;
  const url = `${SITE_URL}${eventPath(event)}`;
  const data = {
    "@context": "https://schema.org",
    "@type": "MusicEvent",
    name: event.event_name || "EDM Show",
    url,
    eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
    eventStatus: "https://schema.org/EventScheduled",
  };
  if (event.date || event.raw_date) {
    data.startDate = event.raw_date || event.date;
  }
  if (event.genre) data.keywords = event.genre;
  if (event.venue || event.city) {
    data.location = {
      "@type": "Place",
      name: event.venue || event.city,
      address: event.city
        ? { "@type": "PostalAddress", addressLocality: event.city }
        : undefined,
    };
  }
  if (event.event_url) {
    data.offers = {
      "@type": "Offer",
      url: event.event_url,
      availability: "https://schema.org/InStock",
    };
  }
  if (event.organizer) {
    data.organizer = { "@type": "Organization", name: event.organizer };
  }
  return data;
};

const EventDetail = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const { id, slug } = useParams();
  const { darkMode } = useTheme();
  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const fetchEvent = async () => {
      setLoading(true);
      setError(null);
      setNotFound(false);
      try {
        const response = await fetch(`${apiUrl}/v1/events/${encodeURIComponent(id)}`);
        if (response.status === 404) {
          if (!cancelled) {
            setNotFound(true);
            setEvent(null);
          }
          return;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const row = data?.data || null;
        if (!cancelled) setEvent(row);
      } catch (err) {
        console.error("Failed to load event:", err);
        if (!cancelled) setError("Could not load this event.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    if (id) fetchEvent();
    else {
      setNotFound(true);
      setLoading(false);
    }
    return () => {
      cancelled = true;
    };
  }, [apiUrl, id]);

  useEffect(() => {
    if (!event) {
      clearJsonLd("event-jsonld");
      return undefined;
    }
    const meta = eventSeoMeta(event);
    const canonicalPath = eventPath(event);
    applyDocumentSeo({
      title: meta.title,
      description: meta.description,
      canonicalPath,
      robots: "index,follow",
    });
    upsertJsonLd("event-jsonld", musicEventJsonLd(event));

    const expectedSlug = eventSlug(event);
    if (slug && slug !== expectedSlug) {
      window.history.replaceState(null, "", canonicalPath);
    }

    return () => clearJsonLd("event-jsonld");
  }, [event, slug]);

  if (notFound) {
    return <Navigate replace to="/events" />;
  }

  return (
    <div
      className={`w-full max-w-full min-h-screen flex flex-col items-center pixel-grid ${
        darkMode ? "text-sprout-text" : "text-gray-900"
      }`}
    >
      <div
        className={`w-full border-b-2 ${
          darkMode ? "bg-sprout-panel border-sprout-border" : "bg-white border-gray-300"
        }`}
      >
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <Link to="/events" aria-label="SproutMe home" className="flex items-center min-w-0">
            <img src={sproutIcon} alt="" className="h-8 w-8 mr-2 flex-shrink-0" />
            <span
              className={`font-pixel text-lg truncate ${
                darkMode ? "text-sprout-lime" : "text-green-700"
              }`}
            >
              SproutMe
            </span>
          </Link>
          <ThemeToggle />
        </div>
      </div>

      <div className="w-full max-w-3xl px-4 py-6 flex-1">
        <Link
          to={event?.city ? cityHubPath(event.city) : "/events"}
          className={`font-read text-sm mb-4 inline-block ${
            darkMode ? "text-sprout-muted hover:text-sprout-lime" : "text-gray-600 hover:text-green-700"
          }`}
        >
          ← {event?.city ? `More in ${event.city}` : "All events"}
        </Link>

        {loading && (
          <div className="page-spinner mx-auto mt-12" aria-label="Loading event" />
        )}

        {error && !loading && (
          <p className={`font-read ${darkMode ? "text-red-300" : "text-red-600"}`}>{error}</p>
        )}

        {event && !loading && (
          <article className="pixel-panel p-5 sm:p-6 flex flex-col gap-4">
            <p
              className={`font-read text-sm ${
                darkMode ? "text-sprout-muted" : "text-gray-600"
              }`}
            >
              <span className={darkMode ? "text-sprout-lime" : "text-green-700"}>
                {event.date || event.raw_date || "Date TBA"}
              </span>
              {event.venue && (
                <>
                  <span className="mx-1.5 opacity-40">·</span>
                  <span>{event.venue}</span>
                </>
              )}
              {event.city && (
                <>
                  <span className="mx-1.5 opacity-40">·</span>
                  <span>{event.city}</span>
                </>
              )}
              {event.ticket_info && event.ticket_info !== "N/A" && (
                <>
                  <span className="mx-1.5 opacity-40">·</span>
                  <span className={darkMode ? "text-amber-200" : "text-amber-800"}>
                    {event.ticket_info}
                  </span>
                </>
              )}
            </p>

            <h1
              className={`font-read font-semibold text-2xl sm:text-3xl leading-tight ${
                darkMode ? "text-sprout-text" : "text-gray-900"
              }`}
            >
              {event.event_name || "Untitled event"}
            </h1>

            {event.genre && (
              <div className="flex flex-wrap gap-1.5">
                {event.genre
                  .split(/[,/;|]+/)
                  .map((g) => g.trim())
                  .filter(Boolean)
                  .slice(0, 4)
                  .map((tag) => (
                    <span key={tag} className="pixel-tag">
                      {tag}
                    </span>
                  ))}
              </div>
            )}

            {event.organizer && (
              <p className={`font-read text-sm ${darkMode ? "text-sprout-muted" : "text-gray-600"}`}>
                Presented by {event.organizer}
              </p>
            )}

            <div className="flex flex-wrap gap-2 pt-2">
              {event.event_url ? (
                <a
                  href={event.event_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() =>
                    trackEvent("click", {
                      outbound: true,
                      link_url: event.event_url,
                      link_text: event.event_name,
                      content_type: "event_detail",
                    })
                  }
                  className="pixel-btn inline-flex items-center justify-center px-4 py-2.5 text-sm"
                >
                  Get tickets
                </a>
              ) : null}
              <a
                href={CHATGPT_HREF}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() =>
                  trackEvent("generate_lead", { method: "chatgpt", source: "event_detail" })
                }
                className={`font-pixel inline-flex items-center justify-center px-4 py-2.5 text-sm border-2 ${
                  darkMode
                    ? "border-sprout-sms text-sprout-sms hover:bg-purple-950/40"
                    : "border-purple-400 text-purple-800 hover:bg-purple-50"
                }`}
                style={{ borderRadius: 2 }}
                aria-label="Ask ChatGPT about this show"
              >
                Ask ChatGPT
              </a>
            </div>
          </article>
        )}
      </div>

      <ContactFooter />
    </div>
  );
};

export default EventDetail;
