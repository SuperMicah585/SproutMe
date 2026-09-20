import React, { useEffect, useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { trackEvent } from '../../utils/analytics';

export const SMS_STORAGE_KEY = 'hideSmsIntro';
export const DEFAULT_SMS_NUMBER = '+12603084566';

export const getSmsNumber = () =>
  import.meta.env.VITE_SMS_NUMBER || DEFAULT_SMS_NUMBER;

export const formatSmsNumber = (value) => {
  const digits = String(value || '').replace(/\D/g, '');
  if (digits.length === 11 && digits.startsWith('1')) {
    return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  if (digits.length === 10) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  return value;
};

const benefits = [
  'Text a city, genre, or budget and get 1–3 real shows with links.',
  'Ask for tonight, this weekend, or a later date.',
  'If nothing is on tonight, it tells you what is coming later this month.',
  'The chat stays for 24 hours, so you can say cheaper or tomorrow. Text RESET to start over.',
];

const SmsIntroModal = ({ open, onClose }) => {
  const { darkMode } = useTheme();
  const smsNumber = getSmsNumber();
  const displayNumber = formatSmsNumber(smsNumber);
  const smsHref = `sms:${smsNumber}`;
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    trackEvent('sms_intro_shown');
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

  const copyNumber = async () => {
    try {
      await navigator.clipboard.writeText(displayNumber);
      setCopied(true);
      trackEvent('sms_intro_copy');
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black bg-opacity-60"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sms-intro-title"
        onClick={(e) => e.stopPropagation()}
        className={`w-full max-w-md rounded-xl shadow-2xl border p-5 ${
          darkMode ? 'bg-gray-800 border-green-600 text-gray-100' : 'bg-white border-green-300 text-gray-900'
        }`}
      >
        <h2 id="sms-intro-title" className={`text-lg font-bold mb-1 ${darkMode ? 'text-green-400' : 'text-green-600'}`}>
          Plan your night over text
        </h2>
        <p className={`text-sm mb-4 ${darkMode ? 'text-gray-300' : 'text-gray-600'}`}>
          SproutMe texts back real shows. No app, no account, just a few messages while you are getting ready.
        </p>

        <div
          className={`rounded-lg px-4 py-3 mb-4 text-center ${
            darkMode ? 'bg-gray-900 border border-green-700' : 'bg-green-50 border border-green-200'
          }`}
        >
          <p className={`text-xs uppercase tracking-wide mb-1 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
            Text this number
          </p>
          <a
            href={smsHref}
            className={`block text-2xl font-bold tracking-wide ${darkMode ? 'text-green-400' : 'text-green-700'}`}
            onClick={() => trackEvent('sms_intro_text_tap')}
          >
            {displayNumber}
          </a>
        </div>

        <ul className={`text-sm space-y-2 mb-4 ${darkMode ? 'text-gray-300' : 'text-gray-600'}`}>
          {benefits.map((item) => (
            <li key={item} className="flex gap-2">
              <span className={darkMode ? 'text-green-400' : 'text-green-600'}>•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>

        <p className={`text-xs mb-4 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
          Try: hardstyle in Portland, or $30 tonight Seattle.
        </p>

        <div className="flex flex-wrap justify-end gap-2">
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
            onClick={copyNumber}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              darkMode ? 'bg-gray-700 hover:bg-gray-600 text-gray-200' : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
            }`}
          >
            {copied ? 'Copied' : 'Copy number'}
          </button>
          <a
            href={smsHref}
            onClick={() => {
              trackEvent('sms_intro_text_click');
              onClose();
            }}
            className={`${
              darkMode ? 'bg-purple-700 hover:bg-purple-600' : 'bg-purple-600 hover:bg-purple-500'
            } text-white px-4 py-2 rounded-lg text-sm font-medium inline-flex items-center justify-center`}
          >
            Text us
          </a>
        </div>
      </div>
    </div>
  );
};

export default SmsIntroModal;
