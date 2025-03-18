import { StrictMode } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './index.css';
import EnterNumber from './pages/EnterNumber';
import VerifyCode from './pages/VerifyCode.jsx';
import Dashboard from './pages/Dashboard.jsx';
import EventsPage from './pages/Events.jsx';
import NewUserPage from './pages/NewUserPage.jsx'; // Import the NewUserPage component
import { ToastContainer } from './pages/Components/ToastNotification.jsx';

ReactDOM.createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Router>
      <Routes>
        <Route path="/" element={<EnterNumber />} />
        <Route path="/verify" element={<VerifyCode />} />
        <Route path="/new-user" element={<NewUserPage />} /> {/* Add the NewUserPage route */}
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/events/:phoneHash" element={<EventsPage />} />
      </Routes>
    </Router>
    <ToastContainer />
  </StrictMode>
);