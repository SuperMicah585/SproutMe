import React, { useState } from 'react';
import EnterButton from './Components/EnterButton';
import sproutIcon from './Components/sprout_icon.png';
import { useNavigate, useLocation } from "react-router-dom";
import { useToast } from "./Components/ToastNotification";

const NewUserPage = () => {
  const apiUrl = import.meta.env.VITE_API_URL;
  const [inputValue, setInputValue] = useState('');
  const navigate = useNavigate();
  const toast = useToast();
  const location = useLocation();
  const { phoneNumber } = location.state || {}; // Get phoneNumber from navigation state

  const handleInputChange = (e) => {
    setInputValue(e.target.value);
  };

  const handleClick = async () => {
    if (inputValue.length > 1 && inputValue.length <= 20) {
      // Call the API to update the user's name
      const updateResponse = await updateUserName(phoneNumber, inputValue);

      if (updateResponse.success) {
        toast.success('Name updated successfully!');
        navigate("/dashboard", { state: { phoneNumber: phoneNumber } });
      } else {
        toast.error('Failed to update name. Please try again.');
      }
    } else {
      toast.error('Name must be between 2 and 20 characters.');
    }
  };

  async function updateUserName(phoneNumber, name) {
    const url = `${apiUrl}/update_user_name`;

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ phone_number: phoneNumber, name: name }),
      });

      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error("Error updating user name:", error);
      return { success: false, message: "Failed to update user name" };
    }
  }

  return (
    <div className="w-screen h-screen flex items-center justify-center bg-white">
      <div className="p-10 w-96 shadow-lg border rounded-lg">
        <div className="flex flex-col gap-5 items-center">
          <div className="flex items-center">
            <div>
              <img src={sproutIcon} alt="Sprout Icon" />
            </div>
            <h1 className="font-unlock text-5xl text-green-500 font-bold">SproutMe</h1>
          </div>
          <h2 className="font-semibold mt-2 text-black">Welcome! Please Enter Your Name</h2>
          <input
            className="w-full border border-black h-14 bg-white text-black rounded-md pl-2 text-xl font-light focus:border-transparent focus:outline-none focus:ring-2 focus:ring-green-500"
            type="text"
            value={inputValue}
            onChange={handleInputChange}
            placeholder="Enter Your Name..."
          />
          <div onClick={handleClick}>
            <EnterButton text="Continue" height={3} width={28} color="green" />
          </div>
        </div>
      </div>
    </div>
  );
};

export default NewUserPage;