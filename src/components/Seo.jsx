import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { trackPageView } from '../utils/analytics';
import { parseHubPathname, unslugifyGuess, hubSeoMeta, SITE_URL } from '../utils/seoPaths';

export { SITE_URL };

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
  '/privacy': {
    title: 'Privacy Policy | SproutMe',
    description: 'How SproutMe collects, uses, and shares information when you use the site and ChatGPT plugin.',
    robots: 'index,follow',
  },
  '/terms': {
    title: 'Terms of Service | SproutMe',
    description: 'Terms governing use of SproutMe, including the website and ChatGPT plugin.',
    robots: 'index,follow',
  },
  '/support': {
    title: 'Support | SproutMe',
    description: 'Get help with SproutMe on the web and in ChatGPT.',
    robots: 'index,follow',
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

export const applyDocumentSeo = ({
  title,
  description,
  canonicalPath,
  robots = 'index,follow',
  track = true,
} = {}) => {
  const path = canonicalPath || '/events';
  const canonical = path.startsWith('http') ? path : `${SITE_URL}${path}`;
  const pageTitle = title || ROUTES['/events'].title;
  const pageDescription = description || DEFAULT_DESCRIPTION;

  document.title = pageTitle;
  upsertMeta('meta[name="description"]', { name: 'description', content: pageDescription });
  upsertMeta('meta[name="robots"]', { name: 'robots', content: robots });
  upsertMeta('meta[property="og:title"]', { property: 'og:title', content: pageTitle });
  upsertMeta('meta[property="og:description"]', { property: 'og:description', content: pageDescription });
  upsertMeta('meta[property="og:url"]', { property: 'og:url', content: canonical });
  upsertMeta('meta[name="twitter:title"]', { name: 'twitter:title', content: pageTitle });
  upsertMeta('meta[name="twitter:description"]', { name: 'twitter:description', content: pageDescription });
  upsertMeta('meta[name="twitter:url"]', { name: 'twitter:url', content: canonical });
  upsertLink('canonical', canonical);
  if (track) {
    const trackPath = path.startsWith('http') ? new URL(path).pathname : path;
    trackPageView(trackPath, pageTitle);
  }
};

export const upsertJsonLd = (id, data) => {
  if (!data) return;
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement('script');
    el.type = 'application/ld+json';
    el.id = id;
    document.head.appendChild(el);
  }
  el.textContent = JSON.stringify(data);
};

export const clearJsonLd = (id) => {
  const el = document.getElementById(id);
  if (el) el.remove();
};

const resolveRouteMeta = (pathname) => {
  if (pathname.startsWith('/favorited_events')) {
    return { ...ROUTES['/favorited_events'], canonicalPath: pathname };
  }
  if (pathname.startsWith('/event/')) {
    // EventDetail applies precise meta once the event loads.
    return {
      title: 'EDM Show | SproutMe',
      description: DEFAULT_DESCRIPTION,
      robots: 'index,follow',
      canonicalPath: pathname,
    };
  }

  const hub = parseHubPathname(pathname);
  if (hub.citySlug || hub.genreSlug) {
    const cityLabel = hub.citySlug ? unslugifyGuess(hub.citySlug) : null;
    const genreLabel = hub.genreSlug ? unslugifyGuess(hub.genreSlug) : null;
    const meta = hubSeoMeta({ cityLabel, genreLabel });
    return {
      ...meta,
      robots: 'index,follow',
      canonicalPath: pathname,
    };
  }

  const routeKey = ROUTES[pathname] ? pathname : '/events';
  return {
    ...ROUTES[routeKey],
    canonicalPath: pathname === '/' ? '/events' : pathname,
  };
};

const Seo = () => {
  const { pathname } = useLocation();

  useEffect(() => {
    // Event detail owns its SEO after fetch.
    if (pathname.startsWith('/event/')) return undefined;
    const meta = resolveRouteMeta(pathname);
    applyDocumentSeo({
      title: meta.title,
      description: meta.description,
      canonicalPath: meta.canonicalPath,
      robots: meta.robots,
    });
    return undefined;
  }, [pathname]);

  return null;
};

export default Seo;
