import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
// Remove the Node.js crypto import
// import crypto from "crypto"; ❌

// Update the hash function to use browser's WebCrypto API
export const hashPhoneNumber = async (phoneNumber) => {
  // Convert the phone number to an ArrayBuffer
  const encoder = new TextEncoder();
  const data = encoder.encode(phoneNumber);
  
  // Hash the data using SHA-256
  const hashBuffer = await window.crypto.subtle.digest('SHA-256', data);
  
  // Convert the hash to a hex string
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
};

// Update the verification function to be async as well
export const verifyPhoneHash = async (phoneNumber, hash) => {
  const generatedHash = await hashPhoneNumber(phoneNumber);
  return generatedHash === hash;
};

const EventsPage = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const { phoneHash } = useParams(); // Changed from phoneNumber to phoneHash
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actualPhoneNumber, setActualPhoneNumber] = useState(null);
  const [name,setName] = useState("")

  useEffect(() => {
    if(phoneHash){
    fetchEvents();
    getNameByPhoneHash(phoneHash)
    }
  }, [phoneHash]);

  async function fetchEvents() {
    if (!phoneHash) {
      setError("Phone hash not provided");
      setLoading(false);
      return;
    }

    try {
      // Option 1: Send the hash to the backend, and let the backend handle the lookup
      const url = `${apiUrl}/events?phone_hash=${encodeURIComponent(phoneHash)}`;
      
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
      setEvents(data.data || []);
      
      // If your backend returns the actual phone number along with the events,
      // you can set it here for display purposes
      if (data.phoneNumber) {
        setActualPhoneNumber(data.phoneNumber);
      }
      
      setLoading(false);
    } catch (error) {
      console.error("Error fetching events:", error);
      setError("Failed to fetch events. Please try again later.");
      setLoading(false);
    }
  }


  async function getNameByPhoneHash(phoneHash) {
    const url = `${apiUrl}/get_name`;
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ phone_hash: phoneHash }),
        });

        const data = await response.json();

        if (response.ok) {
            setName(data.name + "'s")  // Return the name if found
        } else {
            throw new Error(data.error || 'Error retrieving name');
        }
    } catch (error) {
        console.error('Error:', error);
        return null;  // Return null or handle the error accordingly
    }
}

  return (
    <div className="w-screen h-screen flex flex-col items-center bg-gray-50 p-6 overflow-y-scroll">
      <div className="text-4xl font-bold text-green-600 mb-2 mt-6">Upcoming Events</div>
      <div className="text-xl font-medium text-gray-700 mb-8">
        {actualPhoneNumber ? `Events for ${actualPhoneNumber}` : `${name} events for the next week`}
      </div>
      
      <div className="w-full max-w-5xl px-4">
        {loading ? (
          <div className="flex justify-center">
            <div className="w-12 h-12 border-4 border-green-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : error ? (
          <div className="bg-red-100 border-2 border-red-300 text-red-700 p-4 rounded-lg">
            {error}
          </div>
        ) : events.length === 0 ? (
          <div className="bg-yellow-50 border-2 border-yellow-300 text-yellow-700 p-6 rounded-xl text-center">
            <p className="text-lg font-medium">No events found for your preferences.</p>
            <p className="mt-2">Try adding more genres or cities to get event notifications.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {events.map((event, index) => (
            <div
                key={index}
                className="bg-white p-6 rounded-xl shadow-lg border-2 border-green-200 transition-all hover:shadow-xl hover:border-green-400"
            >
                <h3 className="font-bold text-xl text-gray-800 mb-3">{event.event_name.trim()}</h3>
                
                <div className="space-y-2 mb-4">
                <div className="flex">
                    <span className="font-medium text-gray-600 w-24">Date:</span>
                    <span className="text-gray-800">{event.date.trim()}</span>
                </div>
                
                <div className="flex">
                    <span className="font-medium text-gray-600 w-24">Venue:</span>
                    <span className="text-gray-800">{event.venue.trim()}</span>
                </div>
                
                <div className="flex">
                    <span className="font-medium text-gray-600 w-24">Genre:</span>
                    <span className="bg-green-100 text-green-800 px-2 py-1 rounded-md text-sm">{event.genre.trim()}</span>
                </div>

                <div className="flex">
                    <span className="font-medium text-gray-600 w-24">Tickets:</span>
                    <span className="text-gray-800">{event.ticket_info.trim()}</span>
                </div>

                <div className="flex">
                    <span className="font-medium text-gray-600 w-24">Organizer:</span>
                    <span className="text-gray-800">{event.organizer.trim()}</span>
                </div>
                </div>
                
                {event.event_link_url && (
                <a
                    href={event.event_url.trim()}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block w-full text-center bg-green-500 hover:bg-green-600 text-white font-medium py-2 rounded-lg transition-colors mt-4"
                >
                    View Event
                </a>
                )}
            </div>
            ))}

          </div>
        )}
      </div>
    </div>
  );
};

export default EventsPage;