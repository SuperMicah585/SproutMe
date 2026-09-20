import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { trackPageView } from '../utils/analytics';

export const SITE_URL = 'https://sproutme-please.com';

const DEFAULT_DESCRIPTION =
  'Find the best EDM shows, concerts, and festivals across the United States and Canada. Discover upcoming electronic dance music events near you.';

const ROUTES = {
  '/events': {
    title: 'SproutMe - Find EDM Shows & Events',
    description: DEFAULT_DESCRIPTION,
    robots: 'index,follow',
  },
  '/login': {
    title: 'Log in | SproutMe',
    description: 'Log in to save favorite EDM shows on SproutMe.',
    robots: 'noindex,nofollow',
  },
  '/verify': {
    title: 'Verify | SproutMe',
    description: 'Verify your phone number to use SproutMe.',
    robots: 'noindex,nofollow',
  },
  '/new-user': {
    title: 'Welcome | SproutMe',
    description: 'Finish setting up your SproutMe account.',
    robots: 'noindex,nofollow',
  },
  '/dashboard': {
    title: 'Dashboard | SproutMe',
    description: 'Manage your SproutMe preferences.',
    robots: 'noindex,nofollow',
  },
  '/favorited_events': {
    title: 'Favorite Events | SproutMe',
    description: 'Saved EDM shows on SproutMe.',
    robots: 'noindex,nofollow',
  },
};

const upsertMeta = (selector, attributes) => {
  let el = document.head.querySelector(selector);
  if (!el) {
    el = document.createElement('meta');
    document.head.appendChild(el);
  }
  Object.entries(attributes).forEach(([key, value]) => el.setAttribute(key, value));
};

const upsertLink = (rel, href) => {
  let el = document.head.querySelector(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement('link');
    el.setAttribute('rel', rel);
    document.head.appendChild(el);
  }
  el.setAttribute('href', href);
};

const Seo = () => {
  const { pathname } = useLocation();

  useEffect(() => {
    const routeKey = pathname.startsWith('/favorited_events') ? '/favorited_events' : pathname;
    const meta = ROUTES[routeKey] || ROUTES['/events'];
    const canonicalPath = pathname === '/' ? '/events' : pathname;
    const canonical = `${SITE_URL}${canonicalPath}`;

    document.title = meta.title;
    upsertMeta('meta[name="description"]', { name: 'description', content: meta.description });
    upsertMeta('meta[name="robots"]', { name: 'robots', content: meta.robots });
    upsertMeta('meta[property="og:title"]', { property: 'og:title', content: meta.title });
    upsertMeta('meta[property="og:description"]', { property: 'og:description', content: meta.description });
    upsertMeta('meta[property="og:url"]', { property: 'og:url', content: canonical });
    upsertMeta('meta[name="twitter:title"]', { name: 'twitter:title', content: meta.title });
    upsertMeta('meta[name="twitter:description"]', { name: 'twitter:description', content: meta.description });
    upsertMeta('meta[name="twitter:url"]', { name: 'twitter:url', content: canonical });
    upsertLink('canonical', canonical);
    trackPageView(canonicalPath, meta.title);
  }, [pathname]);

  return null;
};

export default Seo;
