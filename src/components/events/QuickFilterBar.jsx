import React from "react";
import { useTheme } from "../../context/ThemeContext";
import { detectDatePreset } from "../../utils/eventFilters";

const chipBase = (darkMode, active) =>
  `font-pixel text-sm px-3 py-1.5 border-2 ${
    active
      ? darkMode
        ? "bg-sprout-lime text-gray-900 border-sprout-lime"
        : "bg-green-600 text-white border-green-600"
      : darkMode
        ? "bg-sprout-panel text-sprout-text border-sprout-border hover:border-sprout-lime"
        : "bg-white text-gray-800 border-gray-300 hover:border-green-600"
  }`;

const summaryBtn = (darkMode, active) =>
  `font-pixel min-w-0 flex-1 truncate text-sm px-3 py-2.5 border-2 ${
    active
      ? darkMode
        ? "bg-sprout-panel-2 text-sprout-lime border-sprout-lime"
        : "bg-green-50 text-green-900 border-green-500"
      : darkMode
        ? "bg-sprout-panel text-sprout-text border-sprout-border"
        : "bg-white text-gray-800 border-gray-300"
  }`;

/**
 * Compact on mobile; richer chip row on desktop. Pixel chrome, readable elsewhere.
 */
const QuickFilterBar = ({
  dateRange,
  onDatePreset,
  selectedCities = [],
  onRemoveCity,
  onOpenCities,
  selectedGenres = [],
  onRemoveGenre,
  onOpenGenres,
  onOpenFilters,
  filterCount = 0,
  onClear,
  chatgptHref,
}) => {
  const { darkMode } = useTheme();
  const preset = detectDatePreset(dateRange);
  const cityLabel =
    selectedCities.length === 0
      ? "City"
      : selectedCities.length === 1
        ? selectedCities[0]
        : `${selectedCities[0]} +${selectedCities.length - 1}`;
  const genreLabel =
    selectedGenres.length === 0
      ? "Genre"
      : selectedGenres.length === 1
        ? selectedGenres[0]
        : `${selectedGenres[0]} +${selectedGenres.length - 1}`;

  const whenOptions = [
    { id: "tonight", label: "Tonight", short: "Tonight" },
    { id: "weekend", label: "Weekend", short: "Weekend" },
    { id: "all", label: "All dates", short: "All" },
  ];

  return (
    <div
      className={`w-full border-b-2 ${
        darkMode ? "bg-sprout-void border-sprout-border" : "bg-[#f4f7f5] border-gray-300"
      }`}
    >
      <div className="w-full max-w-5xl mx-auto px-3 sm:px-4 py-2.5 sm:py-3">
        {/* Mobile */}
        <div className="md:hidden flex flex-col gap-2">
          <div
            className={`grid grid-cols-3 gap-0.5 p-0.5 border-2 ${
              darkMode ? "bg-sprout-panel border-sprout-border" : "bg-gray-200 border-gray-300"
            }`}
            role="group"
            aria-label="Date range"
          >
            {whenOptions.map(({ id, short }) => {
              const active = preset === id || (id === "all" && preset === "custom");
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => onDatePreset(id === "all" && preset === "custom" ? "all" : id)}
                  className={`font-pixel py-2 text-sm ${
                    active
                      ? darkMode
                        ? "bg-sprout-lime text-gray-900"
                        : "bg-white text-green-800"
                      : darkMode
                        ? "text-sprout-muted"
                        : "text-gray-600"
                  }`}
                  aria-pressed={active}
                >
                  {short}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onOpenCities}
              className={summaryBtn(darkMode, selectedCities.length > 0)}
              title={selectedCities.join(", ") || "Pick a city"}
            >
              {cityLabel}
            </button>
            <button
              type="button"
              onClick={onOpenGenres}
              className={summaryBtn(darkMode, selectedGenres.length > 0)}
              title={selectedGenres.join(", ") || "Pick genres"}
            >
              {genreLabel}
            </button>
            <button
              type="button"
              onClick={onOpenFilters}
              className={`font-pixel flex-shrink-0 text-sm px-3 py-2.5 border-2 flex items-center gap-1.5 ${
                darkMode
                  ? "bg-sprout-panel text-sprout-text border-sprout-border"
                  : "bg-white text-gray-800 border-gray-300"
              }`}
              aria-label="More filters"
            >
              Filters
              {filterCount > 0 && (
                <span className="min-w-[1.25rem] h-5 px-1 text-xs font-bold flex items-center justify-center bg-sprout-lime text-gray-900">
                  {filterCount}
                </span>
              )}
            </button>
          </div>

          {filterCount > 0 && (
            <button
              type="button"
              onClick={onClear}
              className={`font-pixel self-start text-xs px-1 ${
                darkMode ? "text-amber-300" : "text-amber-700"
              }`}
            >
              Clear all filters
            </button>
          )}
        </div>

        {/* Desktop */}
        <div className="hidden md:flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`font-pixel text-xs uppercase tracking-wide ${darkMode ? "text-sprout-muted" : "text-gray-400"}`}>
              When
            </span>
            {whenOptions.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => onDatePreset(id)}
                className={chipBase(darkMode, preset === id)}
                aria-pressed={preset === id}
              >
                {label}
              </button>
            ))}
            {preset === "custom" && (
              <span className={`font-pixel text-sm px-3 py-1.5 border-2 ${
                darkMode
                  ? "text-sprout-lime border-sprout-lime"
                  : "text-green-800 border-green-400"
              }`}>
                Custom dates
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className={`font-pixel text-xs uppercase tracking-wide ${darkMode ? "text-sprout-muted" : "text-gray-400"}`}>
              City
            </span>
            {selectedCities.length === 0 ? (
              <button
                type="button"
                onClick={onOpenCities}
                className={`font-pixel text-sm px-3 py-1.5 border-2 border-dashed ${
                  darkMode ? "border-sprout-border text-sprout-muted" : "border-gray-400 text-gray-600"
                }`}
              >
                Near me / pick city
              </button>
            ) : (
              selectedCities.map((city) => (
                <button
                  key={city}
                  type="button"
                  onClick={() => onRemoveCity(city)}
                  className={`${chipBase(darkMode, true)} flex items-center gap-1`}
                  aria-label={`Remove ${city}`}
                >
                  <span className="font-read">{city}</span>
                  <span aria-hidden="true">×</span>
                </button>
              ))
            )}
            <button
              type="button"
              onClick={onOpenCities}
              className={`font-pixel text-sm px-2 py-1.5 border-2 ${
                darkMode ? "border-sprout-border text-sprout-muted" : "border-gray-300 text-gray-500"
              }`}
              aria-label="Add city filter"
            >
              +
            </button>

            <span className={`ml-1 font-pixel text-xs uppercase tracking-wide ${darkMode ? "text-sprout-muted" : "text-gray-400"}`}>
              Genre
            </span>
            {selectedGenres.slice(0, 4).map((genre) => (
              <button
                key={genre}
                type="button"
                onClick={() => onRemoveGenre(genre)}
                className="pixel-tag flex items-center gap-1"
                aria-label={`Remove ${genre}`}
              >
                <span>{genre}</span>
                <span aria-hidden="true">×</span>
              </button>
            ))}
            <button
              type="button"
              onClick={onOpenGenres}
              className={`font-pixel text-sm px-3 py-1.5 border-2 border-dashed ${
                darkMode ? "border-sprout-border text-sprout-muted" : "border-gray-400 text-gray-600"
              }`}
            >
              {selectedGenres.length ? "+" : "Genre"}
            </button>

            <div className="flex-1 min-w-[0.5rem]" />

            <button
              type="button"
              onClick={onOpenFilters}
              className={`font-pixel text-sm px-3 py-1.5 border-2 flex items-center gap-1 ${
                darkMode
                  ? "bg-sprout-panel text-sprout-text border-sprout-border"
                  : "bg-white text-gray-800 border-gray-300"
              }`}
            >
              More
              {filterCount > 0 && (
                <span className="w-5 h-5 text-xs font-bold flex items-center justify-center bg-sprout-lime text-gray-900">
                  {filterCount}
                </span>
              )}
            </button>

            {filterCount > 0 && (
              <button
                type="button"
                onClick={onClear}
                className={`font-pixel text-sm px-3 py-1.5 ${
                  darkMode ? "text-amber-300" : "text-amber-700"
                }`}
              >
                Clear
              </button>
            )}

            {chatgptHref && (
              <a
                href={chatgptHref}
                target="_blank"
                rel="noopener noreferrer"
                className={`font-pixel text-sm px-3 py-1.5 border-2 ${
                  darkMode
                    ? "border-sprout-sms text-sprout-sms"
                    : "border-purple-500 text-purple-800"
                }`}
              >
                Ask ChatGPT
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default QuickFilterBar;
