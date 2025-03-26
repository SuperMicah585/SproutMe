/**
 * Analytics utilities for tracking events in Google Analytics
 */

/**
 * Track an event in Google Analytics
 * @param {string} eventName - The name of the event to track
 * @param {Object} eventParams - Parameters to include with the event
 */
export const trackEvent = (eventName, eventParams = {}) => {
  try {
    if (typeof window === 'undefined' || typeof window.gtag !== 'function') {
      return false;
    }

    // Add timestamp to all events
    const params = {
      ...eventParams,
      timestamp: new Date().toISOString(),
    };

    window.gtag('event', eventName, params);
    return true;
  } catch (error) {
    console.error('Error tracking event:', error);
    return false;
  }
};

/**
 * Track a page view in Google Analytics
 * @param {string} pagePath - The path of the page
 * @param {string} pageTitle - The title of the page
 */
export const trackPageView = (pagePath, pageTitle) => {
  return trackEvent('page_view', {
    page_path: pagePath,
    page_title: pageTitle
  });
};

/**
 * Verify that Google Analytics is properly configured
 */
export const verifyAnalytics = () => {
  return {
    gtagAvailable: typeof window.gtag === 'function',
    dataLayerAvailable: Array.isArray(window.dataLayer),
    timestamp: new Date().toISOString()
  };
}; 