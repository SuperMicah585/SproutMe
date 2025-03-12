import React from 'react';

const EnterButton = ({ text, height, width, color }) => {
  return (
    <button
      className={`bg-${color}-500 hover:bg-${color}-700 text-white font-bold py-${height} px-${width} rounded focus:outline-none focus:ring-2 focus:ring-${color}-500 focus:ring-opacity-50`}
    >
      {text}
    </button>
  );
};

export default EnterButton;
