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

export const startOfLocalDay = (value = new Date()) => {
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split('-').map(Number);
    return new Date(year, month - 1, day);
  }
  const day = value instanceof Date ? new Date(value) : new Date(value);
  if (Number.isNaN(day.getTime())) return startOfLocalDay();
  day.setHours(0, 0, 0, 0);
  return day;
};

// Parse date string to Date object
export const parseEventDate = (rawDate) => {
  if (!rawDate || typeof rawDate !== 'string') return null;
  const match = rawDate.match(/(20\d{2})[-/](\d{1,2})[-/](\d{1,2})/);
  if (!match) return null;
  const parsed = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

export const compareEventsByDate = (left, right) => {
  const dateA = parseEventDate(left?.raw_date);
  const dateB = parseEventDate(right?.raw_date);
  if (!dateA && !dateB) return 0;
  if (!dateA) return 1;
  if (!dateB) return -1;
  const diff = dateA - dateB;
  if (diff !== 0) return diff;
  return String(left?.event_name || '').localeCompare(String(right?.event_name || ''));
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