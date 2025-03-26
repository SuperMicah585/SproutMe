/**
 * Analytics utilities for tracking events in Google Analytics
 */

/**
 * Track an event in Google Analytics with debug logging
 * @param {string} eventName - The name of the event to track
 * @param {Object} eventParams - Parameters to include with the event
 */
export const trackEvent = (eventName, eventParams = {}) => {
  try {
    if (typeof window === 'undefined') {
      console.log('Analytics: Window not available (SSR context)');
      return;
    }

    if (typeof window.gtag !== 'function') {
      console.error('Analytics: gtag is not available on window object');
      console.log('Analytics: Available window properties:', Object.keys(window).join(', '));
      return;
    }

    // Add timestamp to all events
    const params = {
      ...eventParams,
      timestamp: new Date().toISOString(),
    };

    console.log(`Analytics: Tracking "${eventName}" event with params:`, params);
    window.gtag('event', eventName, params);
    console.log(`Analytics: Successfully sent "${eventName}" event to GA`);
    
    return true;
  } catch (error) {
    console.error('Analytics: Error tracking event:', error);
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
  console.log('Analytics Verification:');
  console.log('- gtag available:', typeof window.gtag === 'function');
  console.log('- dataLayer available:', Array.isArray(window.dataLayer));
  console.log('- dataLayer length:', window.dataLayer?.length);
  
  // Send a test event
  trackEvent('analytics_test', {
    test_id: Date.now(),
    browser: navigator.userAgent
  });
  
  // Return status
  return {
    gtagAvailable: typeof window.gtag === 'function',
    dataLayerAvailable: Array.isArray(window.dataLayer),
    timestamp: new Date().toISOString()
  };
};

// Auto-verify on import in development
if (process.env.NODE_ENV !== 'production') {
  // Wait for DOM to be ready
  if (document.readyState === 'complete') {
    verifyAnalytics();
  } else {
    window.addEventListener('load', verifyAnalytics);
  }
} 