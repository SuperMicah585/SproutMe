import React, { createContext, useState, useContext, useEffect } from 'react';
import { hashPhoneNumber } from '../components/events/eventUtils';

// Create context
const AuthContext = createContext(null);

// Custom hook to use the auth context
export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState(null);
  const [phoneHash, setPhoneHash] = useState(null);
  const [userName, setUserName] = useState(null);
  
  useEffect(() => {
    // Check for authentication data in localStorage
    const storedPhoneNumber = localStorage.getItem('phoneNumber');
    const storedPhoneHash = localStorage.getItem('phoneHash');
    const storedUserName = localStorage.getItem('userName');
    
    if (storedPhoneNumber && storedPhoneHash) {
      setPhoneNumber(storedPhoneNumber);
      setPhoneHash(storedPhoneHash);
      setUserName(storedUserName || '');
      setIsLoggedIn(true);
    }
  }, []);
  
  // Login user
  const login = async (phoneNumberData, phoneHashData, userNameData = '') => {
    // Ensure phoneHashData is resolved if it's a Promise
    let resolvedPhoneHash = phoneHashData;
    
    // If phoneHashData is a Promise, resolve it
    if (phoneHashData && typeof phoneHashData.then === 'function') {
      try {
        console.log('Resolving phone hash promise...');
        resolvedPhoneHash = await phoneHashData;
      } catch (error) {
        console.error('Error resolving phone hash promise:', error);
        // Generate a new hash if needed
        if (phoneNumberData) {
          console.log('Generating new hash for phone number:', phoneNumberData);
          resolvedPhoneHash = await hashPhoneNumber(phoneNumberData);
        }
      }
    }
    
    // If we still don't have a valid hash, generate one from the phone number
    if (!resolvedPhoneHash && phoneNumberData) {
      console.log('No hash provided, generating from phone number:', phoneNumberData);
      resolvedPhoneHash = await hashPhoneNumber(phoneNumberData);
    }
    
    console.log('Final hash value:', resolvedPhoneHash);
    
    setPhoneNumber(phoneNumberData);
    setPhoneHash(resolvedPhoneHash);
    setUserName(userNameData);
    setIsLoggedIn(true);
    
    // Save to localStorage
    localStorage.setItem('phoneNumber', phoneNumberData);
    localStorage.setItem('phoneHash', resolvedPhoneHash);
    if (userNameData) localStorage.setItem('userName', userNameData);
  };
  
  // Logout user
  const logout = () => {
    setPhoneNumber(null);
    setPhoneHash(null);
    setUserName(null);
    setIsLoggedIn(false);
    
    // Remove from localStorage
    localStorage.removeItem('phoneNumber');
    localStorage.removeItem('phoneHash');
    localStorage.removeItem('userName');
  };
  
  // Update user name
  const updateName = (name) => {
    setUserName(name);
    localStorage.setItem('userName', name);
  };
  
  // Get hashed phone number (convenience method)
  const getPhoneHash = async () => {
    if (phoneHash) return phoneHash;
    
    if (phoneNumber) {
      const hash = await hashPhoneNumber(phoneNumber);
      setPhoneHash(hash);
      localStorage.setItem('phoneHash', hash);
      return hash;
    }
    
    return null;
  };
  
  // Provide context
  return (
    <AuthContext.Provider 
      value={{ 
        isLoggedIn, 
        phoneNumber, 
        phoneHash,
        userName,
        login, 
        logout,
        updateName,
        getPhoneHash
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext; 