import SearchBar from "./Components/SearchBar";
import { useState, useEffect, useRef } from "react";
import EnterButton from "./Components/EnterButton"
import { useNavigate, useLocation } from "react-router-dom";
import { genres, cities } from "./Components/searchData";
const Dashboard = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const navigate = useNavigate();
  const location = useLocation();
  const phoneNumber = location.state?.phoneNumber || "Unknown Number";
  const [genreArray, setGenreArray] = useState([]);
  const [cityArray, setCityArray] = useState([]);
  const [name,setName] = useState("")
  
  // Add refs to track changes rather than initial renders
  const initialRender = useRef(true);
  const genreChanged = useRef(false);
  const cityChanged = useRef(false);

  // Function to add items
  const handleSelect = (item, setSelectedItems, selectedItems, changeRef) => {
    if (!selectedItems.includes(item)) {
      setSelectedItems((prev) => [...prev, item]);
      // Mark that we've changed this value ourselves (not initial load)
      if (!initialRender.current) {
        changeRef.current = true;
      }
    }
  };

  // Function to remove items
  const handleRemove = (item, setSelectedItems, changeRef) => {
    setSelectedItems((prev) => prev.filter((i) => i !== item));
    // Mark that we've changed this value ourselves (not initial load)
    changeRef.current = true;
  };

  const handleLogoutClick = () => {
    navigate("/");
  };

  const hashPhoneNumber = async (phoneNumber) => {
    // Convert the phone number to an ArrayBuffer
    const encoder = new TextEncoder();
    const data = encoder.encode(phoneNumber);
    
    // Hash the data using SHA-256
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    
    // Convert the hash to a hex string
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  };

  // Set initial render to false after component mounts
  useEffect(() => {
    // After first render, set initialRender to false
    initialRender.current = false;
    
    // Here you would add code to load initial genres and cities from API
    // This would replace the current implementation with an API call
    // Example:
    // fetchUserPreferences(phoneNumber);
    
    // For now we'll just leave the arrays empty
  }, []);

  // Only update genres when they've been explicitly changed by the user
  useEffect(() => {
    if (initialRender.current) return;
    
    if (genreChanged.current || genreArray.length > 0) {
      updateGenresForUser();
      // Reset the change flag
      genreChanged.current = false;
    }
  }, [genreArray]);

  // Only update cities when they've been explicitly changed by the user
  useEffect(() => {
    if (initialRender.current) return;
    
    if (cityChanged.current || cityArray.length > 0) {
      updateCitiesForUser();
      // Reset the change flag
      cityChanged.current = false;
    }
  }, [cityArray]);


  useEffect(() => {

    getUserData()
  }, []);


  async function getUserData() {
    if (!phoneNumber || phoneNumber === "Unknown Number") return;

    // Append phone_number as a query parameter
    const url = `${apiUrl}/user?phone_number=${encodeURIComponent(phoneNumber)}`;

    try {
        const response = await fetch(url, {
            method: "GET",
            headers: {
                "Content-Type": "application/json",
            },
        });

        if (!response.ok) {
            throw new Error(`Server responded with status ${response.status}`);
        }

        const data = await response.json();
        console.log(data)
        setGenreArray(data.data.genre_list)
        setCityArray(data.data.city_list)
        setName(data.data.name)
        return data;
    } catch (error) {
        console.error("Error getting user data:", error);
        return null;
    }
}




  async function updateGenresForUser() {
    if (!phoneNumber || phoneNumber === "Unknown Number") return;
    
    const url = `${apiUrl}/user/genres`;
  
    try {
      const response = await fetch(url, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          genre_list: genreArray,
          phone_number: phoneNumber
        }),
      });
  
      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }
  
      const data = await response.json();
      return data;
    } catch (error) {
      console.error("Error updating genres:", error);
      return null;
    }
  }

  const handleEventsClick = async () => {
    // Hash the phone number
    const phoneHash = await hashPhoneNumber(phoneNumber);

    // Open a new window with the events page using the hash
    const url = `/events/${encodeURIComponent(phoneHash)}`;
    window.open(url, "_blank"); // "_blank" opens the URL in a new tab/window
  };

  async function updateCitiesForUser() {
    if (!phoneNumber || phoneNumber === "Unknown Number") return;
    
    const url = `${apiUrl}/user/cities`;

    try {
      const response = await fetch(url, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        // Fixed the variable name from cityArray to city_list
        body: JSON.stringify({
          city_list: cityArray,
          phone_number: phoneNumber
        }),
      });
  
      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }
  
      const data = await response.json();
      return data;
    } catch (error) {
      console.error("Error updating cities:", error);
      return null;
    }
  }

  return (
    <div className="w-screen h-screen flex flex-col items-center bg-gray-50 p-6">
    <div 
      onClick={handleEventsClick} 
      className="absolute left-1 top-1" 
    >
      <EnterButton
        text="View Events"
        height={1} 
        width={3} 
        color="green"
      />
    </div>

      <div onClick={handleLogoutClick} className="absolute right-1 top-1">
        <EnterButton text="logout" height={1} width={2} color="green" />
      </div>
      <div className="text-4xl font-bold text-green-600 mb-2 mt-6">Add Genres and Cities</div>
      <div className="text-xl font-medium text-gray-700 mb-8">{`Changes will impact events for ${name}`}</div>
      
      <div className="flex flex-col lg:flex-row gap-8 w-full max-w-5xl px-4">
        {/* Genres Section */}
        <div className="w-full lg:w-1/2 bg-white p-6 rounded-xl shadow-lg border-2 border-green-200 transition-all hover:shadow-xl">
          <h3 className="font-bold text-xl text-gray-800 mb-4 flex items-center">
            <span className="inline-block w-2 h-6 bg-green-500 rounded mr-2"></span>
            Genres to Filter
          </h3>
          
          <SearchBar 
            options={genres.filter((item) => !genreArray.includes(item))}
            onSelect={(item) => handleSelect(item, setGenreArray, genreArray, genreChanged)}
            placeholder="Search for genres" 
          />
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-6">
            {genreArray.map((item, index) => (
              <div 
                key={index} 
                className="p-3 bg-green-50 border-2 border-green-300 rounded-lg cursor-pointer hover:bg-red-50 hover:border-red-300 transition-all duration-200 flex justify-between items-center shadow-sm"
                onClick={() => handleRemove(item, setGenreArray, genreChanged)}
              >
                <span className="font-semibold text-green-800">{item}</span> 
                <span className="text-red-500 font-bold ml-2 text-lg hover:scale-125 transition-transform">×</span>
              </div>
            ))}
          </div>
          
          {genreArray.length > 0 && (
            <div className="text-xs text-gray-500 mt-4 italic">
              Click on an item to remove it
            </div>
          )}
        </div>

        {/* Cities Section */}
        <div className="w-full lg:w-1/2 bg-white p-6 rounded-xl shadow-lg border-2 border-green-200 transition-all hover:shadow-xl">
          <h3 className="font-bold text-xl text-gray-800 mb-4 flex items-center">
            <span className="inline-block w-2 h-6 bg-green-500 rounded mr-2"></span>
            Cities to Filter
          </h3>
          
          <SearchBar 
            options={cities.filter((item) => !cityArray.includes(item))}
            onSelect={(item) => handleSelect(item, setCityArray, cityArray, cityChanged)} 
            placeholder="Search for cities" 
          />
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-6">
            {cityArray.map((item, index) => (
              <div 
                key={index} 
                className="p-3 bg-green-50 border-2 border-green-300 rounded-lg cursor-pointer hover:bg-red-50 hover:border-red-300 transition-all duration-200 flex justify-between items-center shadow-sm"
                onClick={() => handleRemove(item, setCityArray, cityChanged)}
              >
                <span className="font-semibold text-green-800">{item}</span> 
                <span className="text-red-500 font-bold ml-2 text-lg hover:scale-125 transition-transform">×</span>
              </div>
            ))}
          </div>
          
          {cityArray.length > 0 && (
            <div className="text-xs text-gray-500 mt-4 italic">
              Click on an item to remove it
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;