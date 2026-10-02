import { Link } from 'react-router-dom';
import sproutIcon from './Components/sprout_icon.png';
import { useTheme } from '../context/ThemeContext';
import ContactFooter from '../components/events/ContactFooter';

const LAST_UPDATED = 'October 1, 2026';
const SUPPORT_EMAIL = 'micahphlps@gmail.com';

const TermsOfService = () => {
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
        <h1 className="text-3xl font-bold mb-2">Terms of Service</h1>
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
              Agreement
            </h2>
            <p>
              These Terms of Service (“Terms”) govern your use of SproutMe at sproutme-please.com,
              our ChatGPT plugin / MCP tools, and related services (the “Service”). By accessing or
              using the Service, you agree to these Terms and our{' '}
              <Link
                to="/privacy"
                className={darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'}
              >
                Privacy Policy
              </Link>
              . If you do not agree, do not use the Service.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              The Service
            </h2>
            <p>
              SproutMe provides tools to browse and discover EDM events, save favorites, submit
              events, and (optionally) query the catalog through ChatGPT or MCP. Event listings are
              aggregated from public sources and user submissions. Information may be incomplete,
              outdated, or inaccurate.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Eligibility &amp; accounts
            </h2>
            <ul className="list-disc pl-5 space-y-2">
              <li>You must be able to form a binding contract in your jurisdiction.</li>
              <li>
                Phone login uses SMS verification. You confirm you own or control the number you
                provide and that receiving verification texts is lawful for you.
              </li>
              <li>You are responsible for activity under your account.</li>
            </ul>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Acceptable use
            </h2>
            <p className="mb-2">You agree not to:</p>
            <ul className="list-disc pl-5 space-y-2">
              <li>Scrape, overload, or disrupt the Service or its infrastructure beyond normal use.</li>
              <li>Attempt unauthorized access to accounts, data, or systems.</li>
              <li>Submit false, harmful, illegal, or infringing content (including fake events).</li>
              <li>Use the Service to spam, harass, or violate applicable law.</li>
              <li>Misrepresent affiliation with SproutMe or use our branding without permission.</li>
            </ul>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Third-party links &amp; tickets
            </h2>
            <p>
              Event pages may link to venues, promoters, or ticket sellers. We do not sell tickets
              ourselves and are not responsible for third-party sites, pricing, availability,
              refunds, or purchases. Always verify details with the source before buying.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              ChatGPT / MCP
            </h2>
            <p>
              When you use SproutMe through ChatGPT or compatible MCP clients, your use of those
              platforms is also governed by their terms. Tool outputs reflect our catalog and your
              account data when authenticated; they are not guarantees of show quality, safety, or
              ticket success.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Intellectual property
            </h2>
            <p>
              SproutMe branding, software, and original content are owned by us or our licensors.
              Event names, artwork, and venue details remain the property of their respective owners.
              You retain rights to content you submit, and grant us a non-exclusive license to host
              and display it in connection with the Service.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Disclaimers
            </h2>
            <p>
              THE SERVICE IS PROVIDED “AS IS” AND “AS AVAILABLE” WITHOUT WARRANTIES OF ANY KIND,
              WHETHER EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY, FITNESS FOR A PARTICULAR
              PURPOSE, AND NON-INFRINGEMENT. WE DO NOT WARRANT THAT LISTINGS ARE COMPLETE, CURRENT,
              OR ERROR-FREE, OR THAT THE SERVICE WILL BE UNINTERRUPTED OR SECURE.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Limitation of liability
            </h2>
            <p>
              TO THE MAXIMUM EXTENT PERMITTED BY LAW, SPROUTME AND ITS OPERATORS WILL NOT BE LIABLE
              FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS
              OF PROFITS, DATA, OR GOODWILL, ARISING FROM YOUR USE OF THE SERVICE OR RELIANCE ON
              EVENT INFORMATION. OUR TOTAL LIABILITY FOR ANY CLAIM RELATED TO THE SERVICE WILL NOT
              EXCEED THE GREATER OF ONE HUNDRED U.S. DOLLARS (US $100) OR THE AMOUNT YOU PAID US (IF
              ANY) IN THE TWELVE MONTHS BEFORE THE CLAIM.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Indemnity
            </h2>
            <p>
              You agree to indemnify and hold harmless SproutMe and its operators from claims,
              damages, and expenses (including reasonable attorneys’ fees) arising from your use of
              the Service, your content, or your violation of these Terms.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Changes &amp; termination
            </h2>
            <p>
              We may modify or discontinue the Service at any time. We may update these Terms; the
              “Last updated” date will change when we do. Continued use after changes means you
              accept the new Terms. We may suspend or terminate access for conduct we reasonably
              believe violates these Terms or harms the Service or others.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Governing law
            </h2>
            <p>
              These Terms are governed by the laws of the State of Washington, USA, without regard
              to conflict-of-law rules, except where your local mandatory consumer laws require
              otherwise.
            </p>
          </section>

          <section>
            <h2 className={`text-lg font-bold mb-2 ${darkMode ? 'text-white' : 'text-gray-900'}`}>
              Contact
            </h2>
            <p>
              Questions:{' '}
              <a
                href={`mailto:${SUPPORT_EMAIL}`}
                className={darkMode ? 'text-green-400 hover:text-green-300' : 'text-green-600 hover:text-green-700'}
              >
                {SUPPORT_EMAIL}
              </a>
              .
            </p>
          </section>
        </div>
      </main>

      <ContactFooter />
    </div>
  );
};

export default TermsOfService;
