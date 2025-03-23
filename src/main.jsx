import { StrictMode } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import './index.css';
import EnterNumber from './pages/EnterNumber';
import VerifyCode from './pages/VerifyCode.jsx';
import Dashboard from './pages/Dashboard.jsx';
import EventsPage from './pages/Events.jsx';
import NewUserPage from './pages/NewUserPage.jsx'; // Import the NewUserPage component
import FavoritedEvents from './pages/FavoritedEvents.jsx';
import { ToastContainer } from './pages/Components/ToastNotification.jsx';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';

ReactDOM.createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <Router>
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
          </Routes>
        </Router>
        <ToastContainer />
      </AuthProvider>
    </ThemeProvider>
  </StrictMode>
);