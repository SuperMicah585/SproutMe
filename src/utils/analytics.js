const flattenParams = (params) => {
  const flat = {};
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value == null) return;
    if (typeof value === 'object' && !Array.isArray(value)) {
      Object.entries(value).forEach(([childKey, childValue]) => {
        if (typeof childValue === 'boolean') {
          flat[`${key}_${childKey}`] = childValue ? 1 : 0;
        } else if (childValue != null && typeof childValue !== 'object') {
          flat[`${key}_${childKey}`] = childValue;
        }
      });
      return;
    }
    flat[key] = value;
  });
  return flat;
};

export const trackEvent = (eventName, eventParams = {}) => {
  try {
    if (typeof window === 'undefined' || typeof window.gtag !== 'function') {
      return false;
    }
    window.gtag('event', eventName, flattenParams(eventParams));
    return true;
  } catch (error) {
    console.error('Error tracking event:', error);
    return false;
  }
};

let lastPageView = '';

export const trackPageView = (pagePath, pageTitle) => {
  if (typeof window === 'undefined' || typeof window.gtag !== 'function') {
    return false;
  }
  const path = pagePath || window.location.pathname;
  const key = `${path}|${pageTitle || document.title}`;
  if (lastPageView === key) return false;
  lastPageView = key;
  window.gtag('event', 'page_view', {
    page_title: pageTitle || document.title,
    page_path: path,
    page_location: `${window.location.origin}${path}${window.location.search}`,
  });
  return true;
};
