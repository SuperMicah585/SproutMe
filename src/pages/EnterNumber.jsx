import React, { useState } from 'react';
import EnterButton from './Components/EnterButton';
import sproutIcon from './Components/sprout_icon.png';
import { useNavigate } from "react-router-dom";
import {useToast} from "./Components/ToastNotification"

const EnterNumber = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const [inputValue, setInputValue] = useState('');
  const navigate = useNavigate();
  const toast = useToast();
  const handleInputChange = (e) => {
    setInputValue(e.target.value);
  };

  const handleClick = async () => {
    if (inputValue.length > 0) {
      const response = await validatePhoneNumber(inputValue, "US");
      if (response.valid === true) {
        toast.success('Please input the code sent to your Phone Number');
        await send2fa(response.phone_number);
        
        // Navigate with state
        navigate("/verify", { state: { phoneNumber: response.phone_number } });
      } else {
        toast.error('Please enter a valid number');
      }
    } else {
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
        console.error("Error validating phone number:", error);
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
      console.log("Response:", data);
      return data;
  } catch (error) {
      console.error("Error validating phone number:", error);
      return null;
  }
}

  return (
<div className='w-screen h-screen flex items-center justify-center'> 
  <div className='p-6 sm:p-10 w-full max-w-xs sm:w-96 shadow-lg border rounded-lg mx-4'> 
    <div className='flex flex-col gap-3 sm:gap-5 items-center'>
    <div className='flex items-center'> 
  <div className="flex items-center justify-center  w-12 h-12 sm:w-16 sm:h-16">
    <img src={sproutIcon} alt="Sprout Icon" className="w-auto h-auto max-h-full object-contain" />
  </div>
  <h1 className="font-unlock text-4xl sm:text-5xl text-green-500 font-bold">SproutMe</h1>
</div>
      <h2 className="font-semibold mt-1 sm:mt-2">Log In/Signup</h2>
      <input 
        className='w-full border border-black h-12 sm:h-14 rounded-md pl-2 text-lg sm:text-xl font-light focus:border-transparent focus:outline-none focus:ring-2 focus:ring-green-500'
        type="text" 
        value={inputValue} 
        onChange={handleInputChange} 
        placeholder="Input phone number..." 
      />
      <div onClick={() => handleClick()} className="w-full flex justify-center"> 
        <EnterButton text="Continue" height={3} width={28} color="green" />
      </div>
    </div>
  </div>
</div>
  );
};

export default EnterNumber;
