// Hash phone number using WebCrypto API
export const hashPhoneNumber = async (phoneNumber) => {
  try {
    // Convert the phone number to an ArrayBuffer
    const encoder = new TextEncoder();
    const data = encoder.encode(phoneNumber);
    
    // Hash the data using SHA-256
    const hashBuffer = await window.crypto.subtle.digest('SHA-256', data);
    
    // Convert the hash to a hex string
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashString = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    
    console.log('Generated hash:', hashString);
    return hashString;
  } catch (error) {
    console.error('Error generating hash:', error);
    throw error;
  }
};

// Verify a phone hash against a phone number
export const verifyPhoneHash = async (phoneNumber, hash) => {
  const generatedHash = await hashPhoneNumber(phoneNumber);
  return generatedHash === hash;
};

// Parse date string to Date object
export const parseEventDate = (rawDate) => {
  const [year, month, day] = rawDate.split('/').map(Number);
  return new Date(year, month - 1, day);
};

// Extract ticket price from ticket_info string
export const extractPrice = (ticketInfo) => {
  const priceMatch = ticketInfo.match(/\$(\d+(?:-\d+)?)/);
  if (priceMatch) {
    const priceStr = priceMatch[1];
    if (priceStr.includes('-')) {
      return parseFloat(priceStr.split('-')[0]);
    }
    return parseFloat(priceStr);
  }
  return 0; // Default price if no price found
};

// Toggle an item in an array (add if not present, remove if present)
export const toggleArrayItem = (array, item) => {
  return array.includes(item)
    ? array.filter(i => i !== item)
    : [...array, item];
};

// Extract city from venue string format "Venue Name (City)"
export const extractCityFromVenue = (venueString) => {
  if (!venueString) return null;
  
  const match = venueString.match(/\(([^)]+)\)/);
  if (match && match[1]) {
    return match[1].trim();
  }
  return null;
}; 