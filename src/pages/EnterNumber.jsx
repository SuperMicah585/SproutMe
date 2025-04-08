import React, { useState, useEffect } from 'react';
import EnterButton from './Components/EnterButton';
import sproutIcon from './Components/sprout_icon.png';
import { useNavigate } from "react-router-dom";
import { useToast } from "./Components/ToastNotification";
import { useAuth } from "../context/AuthContext";
import { trackEvent, trackPageView, verifyAnalytics } from "../utils/analytics";

const EnterNumber = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const [inputValue, setInputValue] = useState('');
  const navigate = useNavigate();
  const toast = useToast();
  const { isLoggedIn } = useAuth();
  
  // Track page view when component mounts
  useEffect(() => {
    // Track page view
    trackPageView('/login', 'Login Page');
  }, []);
  
  // If already logged in, redirect to events page
  useEffect(() => {
    if (isLoggedIn) {
      navigate('/events');
    }
  }, [isLoggedIn, navigate]);
  
  const handleInputChange = (e) => {
    // Only allow digits and format the phone number
    const value = e.target.value.replace(/\D/g, '');
    
    // Format the phone number as (XXX) XXX-XXXX
    let formattedValue = '';
    if (value.length > 0) {
      formattedValue = '(' + value.substring(0, 3);
      if (value.length > 3) {
        formattedValue += ') ' + value.substring(3, 6);
        if (value.length > 6) {
          formattedValue += '-' + value.substring(6, 10);
        }
      }
    }
    
    setInputValue(formattedValue);
  };

  const handleClick = async () => {
    if (inputValue.length > 0) {
      const response = await validatePhoneNumber(inputValue, "US");
      if (response.valid === true) {
        // Track successful phone number submission
        trackEvent('login_attempt', {
          'method': 'phone_number',
          'success': true
        });
        
        toast.success('Please input the code sent to your Phone Number');
        await send2fa(response.phone_number);
        
        // Navigate with state
        navigate("/verify", { state: { phoneNumber: response.phone_number } });
      } else {
        // Track failed phone number submission
        trackEvent('login_attempt', {
          'method': 'phone_number',
          'success': false,
          'error': 'invalid_number'
        });
        
        toast.error('Please enter a valid number');
      }
    } else {
      // Track empty phone number submission
      trackEvent('login_attempt', {
        'method': 'phone_number',
        'success': false,
        'error': 'empty_input'
      });
      
      toast.error('Please enter a valid number');
    }
  };
  


  async function validatePhoneNumber(phoneNumber, region = "US") {
    const url = `${apiUrl}/validate-phone`;

    try {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ phone_number: phoneNumber, region: region }),
        });

        if (!response.ok) {
            throw new Error(`Server responded with status ${response.status}`);
        }

        const data = await response.json();
        
   
        return data;
    } catch (error) {
        return null;
    }
}


async function send2fa(phoneNumber) {
  const url = `${apiUrl}/send_2fa`;

  try {
      const response = await fetch(url, {
          method: "POST",
          headers: {
              "Content-Type": "application/json",
          },
          body: JSON.stringify({ phone_number: phoneNumber}),
      });

      if (!response.ok) {
          throw new Error(`Server responded with status ${response.status}`);
      }

      const data = await response.json();
      return data;
  } catch (error) {
      return null;
  }
}

  return (
    <div className = 'w-screen h-screen flex items-center justify-center bg-white'> 
    <div className = 'p-10 w-96 shadow-lg border rounded-lg'> 
    <div className='flex flex-col gap-5 items-center'>
      <div className ='flex items-center'> 
      <div>
      <img src={sproutIcon} alt="Sprout Icon" />
    </div>
    <h1 className = "font-unlock text-5xl text-green-500 font-bold">SproutMe</h1>
    </div>
      <h2 className = "font-semibold mt-2 text-black">Log In/Signup</h2>
      <div className="w-full relative">
        <input 
          className="w-full border border-black h-14 rounded-md pl-10 text-xl font-semibold bg-white text-black focus:border-transparent focus:outline-none focus:ring-2 focus:ring-green-500 font-sans"
          type="tel" 
          value={inputValue} 
          onChange={handleInputChange} 
          placeholder="(555) 555-5555" 
          maxLength="14"
        />
        <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-500">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
          </svg>
        </div>
      </div>
      <p className="text-xs text-gray-500 text-center">
        Your phone number will only be used to verify you are a real person and will not be shared with third parties.
      </p>
      <div onClick ={()=>handleClick()}> 
      <EnterButton text="Continue" height={3} width={28} color="green" />
      </div>
    </div>
    </div>
    </div>
  );
};

export default EnterNumber;
