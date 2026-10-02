// Immediate script execution to force theme state before any React code runs
(function() {
  // Always default to dark mode on initial page load
  document.documentElement.classList.add('dark');
  document.documentElement.style.backgroundColor = '#242424';
  document.documentElement.style.color = 'rgba(255, 255, 255, 0.87)';
})();

// Import utility to prevent WebSocket errors in production
import './utils/disableHmrInProd';

import { StrictMode } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import './index.css';
import EnterNumber from './pages/EnterNumber';
import VerifyCode from './pages/VerifyCode.jsx';
import Dashboard from './pages/Dashboard.jsx';
import EventsPage from './pages/Events.jsx';
import NewUserPage from './pages/NewUserPage.jsx';
import FavoritedEvents from './pages/FavoritedEvents.jsx';
import PrivacyPolicy from './pages/PrivacyPolicy.jsx';
import TermsOfService from './pages/TermsOfService.jsx';
import SupportPage from './pages/SupportPage.jsx';
import { ToastContainer } from './pages/Components/ToastNotification.jsx';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Seo from './components/Seo';
import ChatGptWidget from './components/events/ChatGptWidget';

ReactDOM.createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <Router>
          <Seo />
          <Routes>
            {/* Redirect root to events page */}
            <Route path="/" element={<Navigate replace to="/events" />} />
            {/* Login flow routes */}
            <Route path="/login" element={<EnterNumber />} />
            <Route path="/verify" element={<VerifyCode />} />
            <Route path="/new-user" element={<NewUserPage />} />
            <Route path="/dashboard" element={<Dashboard />} />
            {/* Main pages */}
            <Route path="/events" element={<EventsPage />} />
            <Route path="/favorited_events/:phoneHash" element={<FavoritedEvents />} />
            <Route path="/privacy" element={<PrivacyPolicy />} />
            <Route path="/terms" element={<TermsOfService />} />
            <Route path="/support" element={<SupportPage />} />
          </Routes>
          <ChatGptWidget />
        </Router>
        <ToastContainer />
      </AuthProvider>
    </ThemeProvider>
  </StrictMode>
);
