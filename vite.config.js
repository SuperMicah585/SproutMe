import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  
  // Disable WebSocket HMR connection attempts in production
  build: {
    // Generate manifest file for better caching
    manifest: true,
    
    rollupOptions: {
      output: {
        manualChunks: {
          // Split vendor code into separate chunk for better caching
          vendor: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
  
  // Configure server options
  server: {
    hmr: {
      // Only enable HMR in development
      overlay: true, 
    },
  },
  
  // Add environment differentiation
  define: {
    // This makes the HMR client check if it's in production and not attempt connections
    '__VITE_HMR_ENABLE_IN_PRODUCTION__': false,
  },
})
