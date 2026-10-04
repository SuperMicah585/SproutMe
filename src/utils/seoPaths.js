/** Slug + path helpers for crawlable city/genre/event URLs. */

export const SITE_URL = "https://sproutme-please.com";

export const slugify = (value) =>
  String(value || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);

/** "los-angeles" → "Los Angeles" when facets haven't resolved yet. */
export const unslugifyGuess = (slug) =>
  String(slug || "")
    .split("-")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");

/** Match a slug to a facet/display label (case-insensitive via slugify). */
export const matchLabelFromSlug = (slug, labels = []) => {
  const want = slugify(slug);
  if (!want) return null;
  const found = labels.find((label) => slugify(label) === want);
  return found || null;
};

export const cityHubPath = (city) => `/events/in/${slugify(city)}`;
export const genreHubPath = (genre) => `/events/genre/${slugify(genre)}`;
export const cityGenreHubPath = (city, genre) =>
  `/events/in/${slugify(city)}/genre/${slugify(genre)}`;

export const eventSlug = (event) => {
  const bits = [event?.event_name, event?.venue, event?.city].filter(Boolean);
  return slugify(bits.join(" ")) || "show";
};

export const eventPath = (event) => {
  const id = event?.id;
  if (id == null || id === "") return "/events";
  return `/event/${id}/${eventSlug(event)}`;
};

/**
 * Parse SEO hub path params from a pathname.
 * Returns { citySlug, genreSlug } or nulls.
 */
export const parseHubPathname = (pathname = "") => {
  const path = String(pathname || "").replace(/\/+$/, "") || "/";
  let match = path.match(/^\/events\/in\/([^/]+)\/genre\/([^/]+)$/i);
  if (match) {
    return { citySlug: decodeURIComponent(match[1]), genreSlug: decodeURIComponent(match[2]) };
  }
  match = path.match(/^\/events\/in\/([^/]+)$/i);
  if (match) {
    return { citySlug: decodeURIComponent(match[1]), genreSlug: null };
  }
  match = path.match(/^\/events\/genre\/([^/]+)$/i);
  if (match) {
    return { citySlug: null, genreSlug: decodeURIComponent(match[1]) };
  }
  return { citySlug: null, genreSlug: null };
};

/**
 * Build the preferred shareable location for the current filter state.
 * Single city and/or genre → path hub; otherwise `/events?...`.
 */
export const buildEventsLocation = ({
  selectedCities = [],
  selectedGenres = [],
  selectedVenues = [],
  selectedOrganizers = [],
  searchTerm = "",
  dateRange = { start: "", end: "" },
  priceSort = "none",
  scoreSort = "none",
  showStarredOnly = false,
  buildEventFilterParams,
} = {}) => {
  const cities = selectedCities.filter(Boolean);
  const genres = selectedGenres.filter(Boolean);
  const useCityPath = cities.length === 1;
  const useGenrePath = genres.length === 1;

  const queryCities = useCityPath ? [] : cities;
  const queryGenres = useGenrePath ? [] : genres;

  const params = buildEventFilterParams({
    selectedCities: queryCities,
    selectedGenres: queryGenres,
    selectedVenues,
    selectedOrganizers,
    searchTerm,
    dateRange,
    priceSort,
    scoreSort,
    showStarredOnly,
  });
  const search = params.toString();
  const suffix = search ? `?${search}` : "";

  if (useCityPath && useGenrePath) {
    return `${cityGenreHubPath(cities[0], genres[0])}${suffix}`;
  }
  if (useCityPath) {
    return `${cityHubPath(cities[0])}${suffix}`;
  }
  if (useGenrePath) {
    return `${genreHubPath(genres[0])}${suffix}`;
  }
  return `/events${suffix}`;
};

export const hubSeoMeta = ({ cityLabel, genreLabel } = {}) => {
  if (cityLabel && genreLabel) {
    return {
      title: `${genreLabel} Shows in ${cityLabel} | SproutMe`,
      description: `Find upcoming ${genreLabel} EDM shows and concerts in ${cityLabel}. Browse dates, venues, and tickets on SproutMe.`,
    };
  }
  if (cityLabel) {
    return {
      title: `EDM Shows in ${cityLabel} | SproutMe`,
      description: `Discover upcoming electronic music shows, concerts, and festivals in ${cityLabel}. Filter by date and genre on SproutMe.`,
    };
  }
  if (genreLabel) {
    return {
      title: `${genreLabel} Events | SproutMe`,
      description: `Find upcoming ${genreLabel} EDM shows and concerts across North America on SproutMe.`,
    };
  }
  return {
    title: "SproutMe - Find EDM Shows & Events",
    description:
      "Find the best EDM shows, concerts, and festivals across the United States and Canada. Discover upcoming electronic dance music events near you.",
  };
};

export const eventSeoMeta = (event) => {
  const name = event?.event_name || "EDM Show";
  const venue = event?.venue || "";
  const city = event?.city || "";
  const date = event?.date || event?.raw_date || "";
  const where = [venue, city].filter(Boolean).join(", ");
  const titleBits = [name];
  if (where) titleBits.push(`at ${where}`);
  if (date) titleBits.push(`— ${date}`);
  return {
    title: `${titleBits.join(" ")} | SproutMe`,
    description: [
      name,
      where && `at ${where}`,
      date && `on ${date}`,
      event?.genre && `(${event.genre})`,
      "— find tickets and more EDM shows on SproutMe.",
    ]
      .filter(Boolean)
      .join(" "),
  };
};
