/** Date presets + shareable /events query helpers. */

export const toLocalISODate = (date = new Date()) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};

export const getTonightRange = (now = new Date()) => {
  const day = toLocalISODate(now);
  return { start: day, end: day };
};

/** Fri–Sun of the current or upcoming weekend (local). */
export const getWeekendRange = (now = new Date()) => {
  const day = now.getDay(); // 0 Sun … 6 Sat
  const start = new Date(now);
  const end = new Date(now);

  if (day === 0) {
    // Sunday: Fri–Sun of this weekend
    start.setDate(now.getDate() - 2);
  } else if (day === 5 || day === 6) {
    // Fri/Sat: this weekend through Sunday
    const toSunday = 7 - day;
    end.setDate(now.getDate() + toSunday);
    if (day === 6) start.setDate(now.getDate() - 1); // Sat → from Fri
  } else {
    // Mon–Thu: upcoming Fri–Sun
    const toFriday = 5 - day;
    start.setDate(now.getDate() + toFriday);
    end.setDate(start.getDate() + 2);
  }

  return { start: toLocalISODate(start), end: toLocalISODate(end) };
};

/** Fri–Sun → tonight; Mon–Thu → this weekend. */
export const getDefaultDateRange = (now = new Date()) => {
  const day = now.getDay();
  if (day === 0 || day === 5 || day === 6) return getTonightRange(now);
  return getWeekendRange(now);
};

export const detectDatePreset = (dateRange, now = new Date()) => {
  const start = dateRange?.start || "";
  const end = dateRange?.end || "";
  if (!start && !end) return "all";
  const tonight = getTonightRange(now);
  if (start === tonight.start && end === tonight.end) return "tonight";
  const weekend = getWeekendRange(now);
  if (start === weekend.start && end === weekend.end) return "weekend";
  return "custom";
};

export const rangeForPreset = (preset, now = new Date()) => {
  if (preset === "tonight") return getTonightRange(now);
  if (preset === "weekend") return getWeekendRange(now);
  return { start: "", end: "" };
};

const multi = (params, key) =>
  params
    .getAll(key)
    .map((value) => String(value || "").trim())
    .filter(Boolean);

/** Parse /events?when=&city=&genre=&q=… into filter state. */
export const parseEventFilterParams = (params) => {
  const search = new URLSearchParams(params);
  const when = (search.get("when") || "").toLowerCase();
  let dateRange = { start: "", end: "" };
  let datePreset = "all";

  if (when === "tonight" || when === "weekend") {
    datePreset = when;
    dateRange = rangeForPreset(when);
  } else if (search.get("date_start") || search.get("date_end")) {
    dateRange = {
      start: search.get("date_start") || "",
      end: search.get("date_end") || "",
    };
    datePreset = detectDatePreset(dateRange);
  }

  const price = (search.get("price") || search.get("price_sort") || "").toLowerCase();
  const sort = (search.get("sort") || "").toLowerCase();
  let priceSort = "none";
  let scoreSort = "none";
  if (price === "asc" || price === "desc") priceSort = price;
  if (sort === "score" || sort === "score_desc") scoreSort = "desc";
  if (sort === "score_asc") scoreSort = "asc";
  if (sort === "rising" || sort === "hot") scoreSort = "rising";

  return {
    selectedCities: multi(search, "city"),
    selectedGenres: multi(search, "genre"),
    selectedVenues: multi(search, "venue"),
    selectedOrganizers: multi(search, "organizer"),
    searchTerm: (search.get("q") || "").trim(),
    dateRange,
    datePreset,
    priceSort,
    scoreSort,
    showStarredOnly: search.get("starred") === "1",
    hasExplicitParams: [...search.keys()].some((key) =>
      [
        "when",
        "city",
        "genre",
        "venue",
        "organizer",
        "q",
        "date_start",
        "date_end",
        "price",
        "price_sort",
        "sort",
        "starred",
      ].includes(key)
    ),
  };
};

/** Build query string for the current filter state (shareable). */
export const buildEventFilterParams = ({
  selectedCities = [],
  selectedGenres = [],
  selectedVenues = [],
  selectedOrganizers = [],
  searchTerm = "",
  dateRange = { start: "", end: "" },
  priceSort = "none",
  scoreSort = "none",
  showStarredOnly = false,
} = {}) => {
  const params = new URLSearchParams();
  const preset = detectDatePreset(dateRange);

  if (preset === "tonight" || preset === "weekend") {
    params.set("when", preset);
  } else if (dateRange.start || dateRange.end) {
    if (dateRange.start) params.set("date_start", dateRange.start);
    if (dateRange.end) params.set("date_end", dateRange.end);
  }

  selectedCities.forEach((city) => params.append("city", city));
  selectedGenres.forEach((genre) => params.append("genre", genre));
  selectedVenues.forEach((venue) => params.append("venue", venue));
  selectedOrganizers.forEach((organizer) => params.append("organizer", organizer));

  if (searchTerm.trim()) params.set("q", searchTerm.trim());
  if (priceSort === "asc" || priceSort === "desc") params.set("price", priceSort);
  if (scoreSort === "desc") params.set("sort", "score");
  if (scoreSort === "asc") params.set("sort", "score_asc");
  if (scoreSort === "rising") params.set("sort", "rising");
  if (showStarredOnly) params.set("starred", "1");

  return params;
};

export const buildSmsPrefill = ({
  selectedCities = [],
  selectedGenres = [],
  dateRange = { start: "", end: "" },
  searchTerm = "",
} = {}) => {
  const preset = detectDatePreset(dateRange);
  const when =
    preset === "tonight"
      ? "tonight"
      : preset === "weekend"
        ? "this weekend"
        : dateRange.start
          ? `around ${dateRange.start}`
          : "soon";
  const city = selectedCities[0] || "my city";
  const genre = selectedGenres.slice(0, 2).join(" / ");
  const bits = [`recs for ${city} ${when}`];
  if (genre) bits.push(genre);
  if (searchTerm.trim()) bits.push(searchTerm.trim());
  return bits.join(" — ");
};

export const smsHrefWithBody = (phoneNumber, body) => {
  const number = String(phoneNumber || "").replace(/\s/g, "");
  if (!body) return `sms:${number}`;
  // ?&body= works on iOS and most Android browsers
  return `sms:${number}?&body=${encodeURIComponent(body)}`;
};
