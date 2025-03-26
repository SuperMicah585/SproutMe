/**
 * Utility to disable WebSocket HMR connection attempts in production
 * This prevents the "WebSocket connection to ws://localhost:5173 failed" error
 */

// Check if we're in production
if (import.meta.env.PROD) {
  // Save original WebSocket
  const OrigWebSocket = window.WebSocket;
  
  // Override WebSocket constructor to block connections to localhost development server
  window.WebSocket = function(url, protocols) {
    // Block connection attempts to localhost development server
    if (url.includes('localhost:5173') || url.includes('ws://localhost')) {
      console.debug('Blocking WebSocket connection to development server in production');
      // Return a non-functional WebSocket that doesn't attempt to connect
      return {
        send: () => {},
        close: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        readyState: 3, // CLOSED
      };
    }
    
    // Allow all other WebSocket connections
    return new OrigWebSocket(url, protocols);
  };
  
  // Copy properties from original WebSocket
  for (const prop in OrigWebSocket) {
    if (OrigWebSocket.hasOwnProperty(prop)) {
      window.WebSocket[prop] = OrigWebSocket[prop];
    }
  }
} 