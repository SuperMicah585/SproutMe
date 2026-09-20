import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext';
import { trackEvent } from '../../utils/analytics';
import { formatSmsNumber, getSmsNumber } from './SmsIntroModal';

const COLLAPSE_KEY = 'sproutme_sms_widget_collapsed';

const SmsWidget = () => {
  const { pathname } = useLocation();
  const { darkMode } = useTheme();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return sessionStorage.getItem(COLLAPSE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  if (pathname !== '/events' && !pathname.startsWith('/favorited_events')) {
    return null;
  }

  const smsNumber = getSmsNumber();
  const displayNumber = formatSmsNumber(smsNumber);
  const smsHref = `sms:${smsNumber}`;

  const setCollapsedState = (next) => {
    setCollapsed(next);
    try {
      sessionStorage.setItem(COLLAPSE_KEY, String(next));
    } catch {
      // ignore storage errors
    }
  };

  const shellClass = `fixed z-30 bottom-4 right-4 ${
    darkMode ? 'bg-gray-800 border-green-700 text-gray-100' : 'bg-white border-green-300 text-gray-900'
  }`;
  const safeBottom = { marginBottom: 'env(safe-area-inset-bottom)' };

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsedState(false)}
        aria-label={`Show SproutMe text number ${displayNumber}`}
        className={`${shellClass} h-14 w-14 rounded-full shadow-lg border flex items-center justify-center`}
        style={safeBottom}
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className={`h-6 w-6 ${darkMode ? 'text-green-400' : 'text-green-600'}`} aria-hidden="true">
          <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z" />
        </svg>
      </button>
    );
  }

  return (
    <div className={`${shellClass} max-w-[calc(100vw-2rem)] rounded-2xl shadow-2xl border`} style={safeBottom}>
      <div className="flex items-stretch">
        <a
          href={smsHref}
          onClick={() => trackEvent('generate_lead', { method: 'sms', source: 'widget' })}
          className="flex items-center gap-3 pl-3 pr-2 py-2.5 min-w-0"
        >
          <span
            className={`flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center ${
              darkMode ? 'bg-purple-700 text-white' : 'bg-purple-600 text-white'
            }`}
            aria-hidden="true"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5">
              <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z" />
            </svg>
          </span>
          <span className="min-w-0">
            <span className={`block text-[11px] uppercase tracking-wide ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
              Text for show recs
            </span>
            <span className={`block text-sm font-bold tabular-nums ${darkMode ? 'text-green-400' : 'text-green-700'}`}>
              {displayNumber}
            </span>
          </span>
        </a>
        <button
          type="button"
          onClick={() => setCollapsedState(true)}
          aria-label="Minimize text-us widget"
          className={`px-2 ${darkMode ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-800'}`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M5 10a1 1 0 011-1h8a1 1 0 110 2H6a1 1 0 01-1-1z" clipRule="evenodd" />
          </svg>
        </button>
      </div>
    </div>
  );
};

export default SmsWidget;
