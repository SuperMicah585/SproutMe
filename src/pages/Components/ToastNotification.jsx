import React, { useState, useEffect } from 'react';

// Individual Toast component
const Toast = ({ message, type, onClose }) => {
  const bgColor = type === 'success' ? 'bg-green-100 border-green-500' : 'bg-red-100 border-red-500';
  const textColor = type === 'success' ? 'text-green-800' : 'text-red-800';
  
  return (
    <div className={`fixed top-4 right-4 p-4 rounded-lg shadow-lg border-l-4 ${bgColor} ${textColor} z-50`}>
      <div className="flex items-start justify-center">
        <p>{message}</p>
        <div onClick={onClose} className={`cursor-pointer ml-4 ${bgColor}`}>×</div>
      </div>
    </div>
  );
};

// Toast Container component
const ToastContainer = () => {
  const [toasts, setToasts] = useState([]);
  
  // Global event listener for adding toasts
  useEffect(() => {
    const handleAddToast = (e) => {
      const { message, type } = e.detail;
      const id = Date.now();
      setToasts(prev => [...prev, { id, message, type }]);
      
      // Auto-remove after 3 seconds
      setTimeout(() => {
        setToasts(prev => prev.filter(toast => toast.id !== id));
      }, 3000);
    };
    
    window.addEventListener('add-toast', handleAddToast);
    return () => window.removeEventListener('add-toast', handleAddToast);
  }, []);
  
  return (
    <>
      {toasts.map(toast => (
        <Toast 
          key={toast.id}
          message={toast.message}
          type={toast.type}
          onClose={() => setToasts(prev => prev.filter(t => t.id !== toast.id))}
        />
      ))}
    </>
  );
};

// Hook for using toasts
const useToast = () => {
  const success = (message) => {
    console.log('Success toast:', message);
    window.dispatchEvent(new CustomEvent('add-toast', { 
      detail: { message, type: 'success' } 
    }));
  };
  
  const error = (message) => {
    console.log('Error toast:', message);
    window.dispatchEvent(new CustomEvent('add-toast', { 
      detail: { message, type: 'error' } 
    }));
  };
  
  return { success, error };
};

export { ToastContainer, useToast };