import React, { useState, useRef, useEffect } from 'react';
import EnterButton from './Components/EnterButton';
import { useNavigate, useLocation } from "react-router-dom";
import { useToast } from "./Components/ToastNotification";
import { useAuth } from "../context/AuthContext";
import { hashPhoneNumber } from "../components/events/eventUtils";

const VerifyCode = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const [code, setCode] = useState(['', '', '', '', '', '']); // Array for 6 digits
  const inputRefs = useRef([]);
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const { login } = useAuth();
  const phoneNumber = location.state?.phoneNumber || "Unknown Number"; // Retrieve phone number from state

  // Initialize refs for each input
  useEffect(() => {
    inputRefs.current = inputRefs.current.slice(0, 6);
  }, []);

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
        return data;
    } catch (error) {
        console.error("Error validating phone number:", error);
        return null;
    }
  }

  const handleInputChange = (index, value) => {
    // Only allow digits
    if (!/^\d*$/.test(value)) return;
    
    // Update the code array
    const newCode = [...code];
    newCode[index] = value;
    setCode(newCode);
    
    // Auto-focus next input if a digit was entered
    if (value && index < 5) {
      inputRefs.current[index + 1].focus();
    }
  };

  const handleKeyDown = (index, e) => {
    // Handle backspace to go to previous input
    if (e.key === 'Backspace' && !code[index] && index > 0) {
      inputRefs.current[index - 1].focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    
    if (pastedData) {
      const newCode = [...code];
      for (let i = 0; i < pastedData.length; i++) {
        newCode[i] = pastedData[i];
      }
      setCode(newCode);
      
      // Focus the next empty input or the last one
      const nextEmptyIndex = newCode.findIndex(digit => !digit);
      if (nextEmptyIndex !== -1 && nextEmptyIndex < 6) {
        inputRefs.current[nextEmptyIndex].focus();
      } else if (nextEmptyIndex === -1 && inputRefs.current[5]) {
        inputRefs.current[5].focus();
      }
    }
  };

  const handleClick = async () => {
    try {
      // Join the code array into a single string
      const codeString = code.join('');
      
      if (codeString.length !== 6) {
        toast.error("Please enter all 6 digits");
        return;
      }
      
      const response = await sendCode(codeString);
  
      if (response.valid) {
        const createUserIfNeeded = await createUser(phoneNumber);
        console.log("user", createUserIfNeeded);
  
        if (createUserIfNeeded.success) {
          // Construct the URL for the new check_user endpoint
          const url = `${apiUrl}/check_user`;
          console.log(url);
  
          // Fetch data from the Flask endpoint to check the user
          const checkUserResponse = await fetch(url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ phone_number: phoneNumber }),
          });
  
          const checkUserData = await checkUserResponse.json();
  
          if (checkUserData.success) {
            // Generate phone hash for authentication
            const phoneHashValue = await hashPhoneNumber(phoneNumber);
            
            // Log the user in using AuthContext - now this is async
            await login(phoneNumber, phoneHashValue, checkUserData.data?.name || null);
            
            // Check the user data's name field to navigate accordingly
            if (checkUserData.data && checkUserData.data.name === null) {
              // If name is null, navigate to the NewUserPage
              navigate("/new-user", { state: { phoneNumber: phoneNumber } });
            } else {
              // If name is not null, navigate to the dashboard or events page
              navigate("/events");
            }
          } else {
            // Handle failure in checking the user name
            toast.error("Failed to check user name");
          }
        } else {
          toast.error("Something went wrong");
        }
      } else {
        toast.error("Invalid Code!");
      }
    } catch (error) {
      toast.error("Please enter a valid code");
    }
  };
  
  return (
    <div className='w-screen h-screen flex items-center justify-center bg-white'> 
      <div className='p-10 w-96 shadow-lg border rounded-lg'> 
        <div className='flex flex-col gap-5 items-center'>
          <h2 className="font-semibold mt-2 text-black">Verify the Code Sent to</h2>
          <p className="text-green-500 font-bold">{phoneNumber}</p> {/* Display the phone number */}
          
          <div className="flex justify-center space-x-2 w-full" onPaste={handlePaste}>
            {code.map((digit, index) => (
              <input
                key={index}
                ref={el => inputRefs.current[index] = el}
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={1}
                value={digit}
                onChange={(e) => handleInputChange(index, e.target.value)}
                onKeyDown={(e) => handleKeyDown(index, e)}
                onPaste={handlePaste}
                className="w-12 h-14 border border-black rounded-md text-center text-xl font-semibold bg-white text-black focus:border-transparent focus:outline-none focus:ring-2 focus:ring-green-500 font-sans"
                aria-label={`Verification code digit ${index + 1}`}
              />
            ))}
          </div>
          
          <p className="text-xs text-gray-500 text-center">
            Your phone number is only used for verification and will not be shared with third parties.
          </p>
          
          <div onClick={handleClick}> 
            <EnterButton text="Continue" height={3} width={28} color="green" />
          </div>
        </div>
      </div>
    </div>
  );
};

export default VerifyCode;
