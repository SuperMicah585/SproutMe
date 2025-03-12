import React, { useState } from 'react';
import EnterButton from './Components/EnterButton';
import { useNavigate, useLocation } from "react-router-dom";
import {useToast} from "./Components/ToastNotification"
const VerifyCode = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const [inputValue, setInputValue] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
    const toast = useToast();
  const phoneNumber = location.state?.phoneNumber || "Unknown Number"; // Retrieve phone number from state


  async function sendCode(code) {
    const url = `${apiUrl}/verify_2fa`;
  
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ phone_number:phoneNumber, verification_code: code}),
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

  async function createUser(phoneNumber) {
    const url = `${apiUrl}/user`;
  
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



  const handleInputChange = (e) => {
    setInputValue(e.target.value);
  };

  const handleClick = async () => {
    try {
      const response = await sendCode(inputValue);
  
      if (response.valid) {
        const createUserIfNeeded = await createUser(phoneNumber)
        console.log("user",createUserIfNeeded)
        if(createUserIfNeeded.success){
        navigate("/dashboard", { state: { phoneNumber: response.phone_number } });
        }
        else{
          toast.error("something went wrong")
        }
      } else {
        toast.success('Valid Code!');
      }
    } catch (error) {
      toast.error('Please enter a valid code');
    }
  };
  
  return (
    <div className='w-screen h-screen flex items-center justify-center'> 
      <div className='p-10 w-96 shadow-lg border rounded-lg'> 
        <div className='flex flex-col gap-5 items-center'>
          <h2 className="font-semibold mt-2">Verify the Code Sent to</h2>
          <p className="text-green-500 font-bold">{phoneNumber}</p> {/* Display the phone number */}
          <input 
            className='w-full border border-black h-14 rounded-md pl-2 text-xl font-light focus:border-transparent focus:outline-none focus:ring-2 focus:ring-green-500'
            type="text" 
            value={inputValue} 
            onChange={handleInputChange} 
            placeholder="Input code here..." 
          />
          <div onClick={handleClick}> 
            <EnterButton text="Continue" height={3} width={28} color="green" />
          </div>
        </div>
      </div>
    </div>
  );
};

export default VerifyCode;
