import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext';

const LoginPrompt = ({ open, onClose }) => {
  const { darkMode } = useTheme();
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black bg-opacity-60"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="login-prompt-title"
        onClick={(e) => e.stopPropagation()}
        className={`w-full max-w-sm rounded-xl shadow-2xl border p-5 ${
          darkMode ? 'bg-gray-800 border-green-600 text-gray-100' : 'bg-white border-green-300 text-gray-900'
        }`}
      >
        <h2 id="login-prompt-title" className={`text-lg font-bold mb-2 ${darkMode ? 'text-green-400' : 'text-green-600'}`}>
          Log in to save this event
        </h2>
        <p className={`text-sm mb-5 ${darkMode ? 'text-gray-300' : 'text-gray-600'}`}>
          Star events to keep them in your favorites. You need to log in first.
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              darkMode ? 'bg-gray-700 hover:bg-gray-600 text-gray-200' : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
            }`}
          >
            Not now
          </button>
          <button
            type="button"
            onClick={() => {
              onClose();
              navigate('/login');
            }}
            className={`${
              darkMode ? 'bg-purple-700 hover:bg-purple-600' : 'bg-purple-600 hover:bg-purple-500'
            } text-white px-4 py-2 rounded-lg text-sm font-medium`}
          >
            Log in
          </button>
        </div>
      </div>
    </div>
  );
};

export default LoginPrompt;
