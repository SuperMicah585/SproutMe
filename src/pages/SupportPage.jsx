import { Link } from 'react-router-dom';
import sproutIcon from './Components/sprout_icon.png';
import { useTheme } from '../context/ThemeContext';
import ContactFooter from '../components/events/ContactFooter';

const SUPPORT_EMAIL = 'micahphlps@gmail.com';

const SupportPage = () => {
  const { darkMode } = useTheme();

  return (
    <div
      className={`min-h-screen flex flex-col ${
        darkMode ? 'bg-gray-900 text-gray-100' : 'bg-gray-50 text-gray-900'
      }`}
    >
      <header
        className={`sticky top-0 z-10 border-b px-4 py-3 ${
          darkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
        }`}
      >
        <div className="max-w-3xl mx-auto flex items-center justify-between gap-4">
          <Link to="/events" className="flex items-center gap-2 min-w-0">
            <img src={sproutIcon} alt="" className="w-8 h-8 shrink-0" />
            <span
              className={`text-xl font-bold truncate ${
                darkMode ? 'text-green-400' : 'text-green-600'
              }`}
            >
              SproutMe
            </span>
          </Link>
          <Link
            to="/events"
            className={`text-sm shrink-0 ${
              darkMode ? 'text-gray-300 hover:text-white' : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            ← Events
          </Link>
        </div>
      </header>

      <main className="flex-1 w-full max-w-3xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-2">Support</h1>
        <p className={`text-sm mb-8 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
          Help with SproutMe on the web and in ChatGPT
        </p>

        <div
          className={`space-y-6 text-sm leading-relaxed ${
            darkMode ? 'text-gray-300' : 'text-gray-700'
          }`}
        >
          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Contact
            </h2>
            <p>
              Email{' '}
              <a
                href={`mailto:${SUPPORT_EMAIL}`}
                className={darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'}
              >
                {SUPPORT_EMAIL}
              </a>
              . We usually reply within a few business days.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Common questions
            </h2>
            <ul className="list-disc pl-5 space-y-3">
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Browse shows</strong>
                {' '}— Use{' '}
                <a
                  href="https://sproutme-please.com/events"
                  className={darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'}
                >
                  sproutme-please.com/events
                </a>
                {' '}or ask ChatGPT with the SproutMe plugin.
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Login / SMS codes</strong>
                {' '}— Sign-in uses a one-time text. Check that the number can receive SMS and try again
                after a minute if the code doesn’t arrive.
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Favorites</strong>
                {' '}— Log in on the site or via ChatGPT SMS login, then star shows. Favorites sync to
                your account.
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Wrong or missing event</strong>
                {' '}— Listings come from public sources and user submissions. Email us the event name,
                city, and a link if something looks off.
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Delete my data</strong>
                {' '}— Email us from the phone number or account email you use and ask for deletion.
                See our{' '}
                <Link
                  to="/privacy"
                  className={darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'}
                >
                  Privacy Policy
                </Link>
                .
              </li>
            </ul>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Policies
            </h2>
            <p>
              <Link
                to="/privacy"
                className={darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'}
              >
                Privacy Policy
              </Link>
              {' · '}
              <Link
                to="/terms"
                className={darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'}
              >
                Terms of Service
              </Link>
            </p>
          </section>
        </div>
      </main>

      <ContactFooter />
    </div>
  );
};

export default SupportPage;
