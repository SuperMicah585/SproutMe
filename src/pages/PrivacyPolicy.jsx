import { Link } from 'react-router-dom';
import sproutIcon from './Components/sprout_icon.png';
import { useTheme } from '../context/ThemeContext';
import ContactFooter from '../components/events/ContactFooter';

const LAST_UPDATED = 'October 1, 2026';
const SUPPORT_EMAIL = 'micahphlps@gmail.com';

const PrivacyPolicy = () => {
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
        <h1 className="text-3xl font-bold mb-2">Privacy Policy</h1>
        <p className={`text-sm mb-8 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`}>
          Last updated: {LAST_UPDATED}
        </p>

        <div
          className={`space-y-6 text-sm leading-relaxed ${
            darkMode ? 'text-gray-300' : 'text-gray-700'
          }`}
        >
          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Overview
            </h2>
            <p>
              SproutMe (“we,” “us,” or “our”) helps you discover electronic dance music (EDM)
              events. This Privacy Policy explains what information we collect, how we use it, and
              your choices. By using sproutme-please.com, our ChatGPT plugin / MCP tools, or related
              services (together, the “Service”), you agree to this policy.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Information we collect
            </h2>
            <ul className="list-disc pl-5 space-y-2">
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Account data.</strong>{' '}
                If you sign in, we collect your phone number and a display name you choose. We use
                SMS one-time codes (via Twilio) to verify your number.
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Favorites &amp; preferences.</strong>{' '}
                Events you star, and any genre or city preferences you save.
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>User-submitted events.</strong>{' '}
                Details you submit when adding a show (name, venue, date, link, etc.).
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>ChatGPT / MCP sessions.</strong>{' '}
                If you connect through ChatGPT or our MCP endpoint, we may store a session token
                tied to your verified phone so favorites tools work across chats.
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Usage &amp; device data.</strong>{' '}
                We use Google Analytics to collect approximate location, device/browser type, pages
                viewed, and similar analytics. We may also use approximate location (with your
                browser’s permission) to suggest nearby cities.
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Communications.</strong>{' '}
                If you email us, we keep the content of that correspondence.
              </li>
            </ul>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              How we use information
            </h2>
            <ul className="list-disc pl-5 space-y-2">
              <li>Provide, operate, and improve the Service (catalog, search, favorites, login).</li>
              <li>Send SMS verification codes and related account security messages.</li>
              <li>Power ChatGPT / MCP tools that read public event data and your favorites when you are logged in.</li>
              <li>Understand usage and fix bugs (analytics).</li>
              <li>Respond to support requests and protect against abuse.</li>
            </ul>
            <p className="mt-3">
              We do not sell your personal information. We do not use your phone number for marketing
              SMS unless you separately opt in to a future marketing program.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Sharing
            </h2>
            <p className="mb-2">We share data only as needed to run the Service, including:</p>
            <ul className="list-disc pl-5 space-y-2">
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Twilio</strong> — SMS
                verification.
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Supabase / hosting providers</strong>{' '}
                — database and application hosting (e.g. Railway).
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>Google Analytics</strong> —
                usage analytics.
              </li>
              <li>
                <strong className={darkMode ? 'text-white' : 'text-gray-900'}>OpenAI / ChatGPT</strong> —
                when you use our plugin, prompts and tool results flow through ChatGPT according to
                OpenAI’s policies. We only return data our tools are designed to expose.
              </li>
              <li>
                Legal or safety needs (e.g. valid legal process, preventing harm or fraud).
              </li>
            </ul>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Retention
            </h2>
            <p>
              We keep account, favorites, and related data while your account is active or as needed
              to provide the Service. Analytics data follows Google Analytics retention settings.
              Session tokens for ChatGPT/MCP may persist until you disconnect or we rotate them.
              You can ask us to delete your account data (see Contact).
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Security
            </h2>
            <p>
              We use industry-standard measures such as HTTPS and hashed identifiers where
              appropriate. No method of transmission or storage is 100% secure.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Children
            </h2>
            <p>
              The Service is not directed to children under 13, and we do not knowingly collect
              personal information from them. If you believe we have, contact us and we will delete it.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Your choices
            </h2>
            <ul className="list-disc pl-5 space-y-2">
              <li>Do not create an account if you prefer not to share a phone number.</li>
              <li>Deny browser location permission; the Service still works without it.</li>
              <li>Use browser or OS controls to limit analytics/cookies where available.</li>
              <li>
                Email{' '}
                <a
                  href={`mailto:${SUPPORT_EMAIL}`}
                  className={darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'}
                >
                  {SUPPORT_EMAIL}
                </a>{' '}
                to access, correct, or delete your account data.
              </li>
            </ul>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Changes
            </h2>
            <p>
              We may update this policy from time to time. The “Last updated” date at the top will
              change when we do. Continued use of the Service after changes means you accept the
              updated policy.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Contact
            </h2>
            <p>
              Questions about privacy:{' '}
              <a
                href={`mailto:${SUPPORT_EMAIL}`}
                className={darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'}
              >
                {SUPPORT_EMAIL}
              </a>
              . See also our{' '}
              <Link
                to="/terms"
                className={darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'}
              >
                Terms of Service
              </Link>
              .
            </p>
          </section>
        </div>
      </main>

      <ContactFooter />
    </div>
  );
};

export default PrivacyPolicy;
