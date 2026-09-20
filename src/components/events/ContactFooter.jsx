import React from 'react';
import { useTheme } from '../../context/ThemeContext';
import { trackEvent } from '../../utils/analytics';
import { formatSmsNumber, getSmsNumber } from './SmsIntroModal';

const ContactFooter = () => {
  const { darkMode } = useTheme();

  return (
    <div className={`w-full py-4 mt-8 ${
      darkMode ? 'bg-gray-800' : 'bg-gray-100'
    } transition-colors duration-300`}>
      <div className="max-w-5xl mx-auto px-4 text-center">
        <p className={`text-sm ${
          darkMode ? 'text-gray-400' : 'text-gray-600'
        } transition-colors duration-300`}>
          Text{' '}
          <a
            href={`sms:${getSmsNumber()}`}
            onClick={() => trackEvent('generate_lead', { method: 'sms', source: 'footer' })}
            className={`${
              darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'
            } transition-colors duration-300`}
          >
            {formatSmsNumber(getSmsNumber())}
          </a>
          {' '}for show recs, or email{' '}
          <a 
            href="mailto:micahphlps@gmail.com"
            className={`${
              darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'
            } transition-colors duration-300`}
          >
            micahphlps@gmail.com
          </a>
        </p>
      </div>
    </div>
  );
};

export default ContactFooter; 