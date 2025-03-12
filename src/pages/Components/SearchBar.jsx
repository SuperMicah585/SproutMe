import { useState } from "react";

const SearchBar = ({ options, onSelect, placeholder }) => {
  const [query, setQuery] = useState("");
  const [filteredOptions, setFilteredOptions] = useState([]);
  const [isFocused, setIsFocused] = useState(false);

  const handleSearch = (e) => {
    const value = e.target.value;
    setQuery(value);
    setFilteredOptions(
      options.filter((option) => option.toLowerCase().includes(value.toLowerCase()))
    );
  };

  return (
    <div className="relative w-full">
      <label htmlFor="search" className="sr-only">Search</label>
      <div className={`flex items-center relative ${isFocused ? "ring-2 ring-green-400" : ""}`}>
        <span className="absolute left-3 text-green-500">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </span>
        <input
          id="search"
          type="text"
          placeholder={placeholder}
          value={query}
          onChange={handleSearch}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setTimeout(() => setIsFocused(false), 100)}
          className="border border-green-300 p-2 pl-10 w-full rounded-md focus:outline-none focus:border-green-500 bg-white"
        />
      </div>
      
      {query && filteredOptions.length > 0 && (
        <div className="absolute bg-white border border-green-200 w-full mt-1 z-10 rounded-md shadow-lg max-h-60 overflow-y-auto">
          {filteredOptions.map((option, index) => (
            <div
              key={index}
              className="p-3 hover:bg-green-50 cursor-pointer border-b border-green-100 last:border-b-0"
              onClick={() => {
                onSelect(option);
                setQuery(""); // Clear input
                setFilteredOptions([]); // Close dropdown
              }}
            >
              {option}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SearchBar;