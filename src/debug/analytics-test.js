/**
 * This is a debug script to manually test the Google Analytics implementation.
 * You can run this in the browser console to verify the tracking is working.
 */

(function() {
  console.group('Google Analytics Debug Test');
  
  // Check if GA is loaded
  console.log('1. Checking if Google Analytics is loaded');
  const gtagAvailable = typeof window.gtag === 'function';
  const dataLayerAvailable = Array.isArray(window.dataLayer);
  
  console.log('- gtag function available:', gtagAvailable);
  console.log('- dataLayer available:', dataLayerAvailable);
  console.log('- dataLayer contents:', window.dataLayer);
  
  if (!gtagAvailable) {
    console.error('ERROR: gtag function is not available. Google Analytics is not properly loaded.');
    console.log('Make sure the Google Analytics script is loaded before this test runs.');
    console.groupEnd();
    return;
  }
  
  // Send a test event directly
  console.log('\n2. Sending direct test event');
  try {
    window.gtag('event', 'debug_test_direct', {
      test_id: 'direct-' + Date.now(),
      timestamp: new Date().toISOString()
    });
    console.log('- Direct test event sent successfully');
  } catch (error) {
    console.error('- Error sending direct test event:', error);
  }
  
  // Test the analytics utility if available
  console.log('\n3. Testing analytics utility');
  if (typeof window.trackEvent === 'function') {
    console.log('- trackEvent function is globally available');
    try {
      window.trackEvent('debug_test_util', {
        test_id: 'util-' + Date.now(),
        timestamp: new Date().toISOString()
      });
      console.log('- Utility test event sent successfully');
    } catch (error) {
      console.error('- Error sending utility test event:', error);
    }
  } else {
    console.log('- trackEvent function is not globally available');
    console.log('- Trying to import from module...');
    
    // Import module dynamically
    import('/src/utils/analytics.js').then(module => {
      console.log('- Analytics module imported successfully');
      try {
        module.trackEvent('debug_test_module', {
          test_id: 'module-' + Date.now(),
          timestamp: new Date().toISOString()
        });
        console.log('- Module test event sent successfully');
        
        // Verify analytics
        const status = module.verifyAnalytics();
        console.log('- Analytics verification status:', status);
      } catch (error) {
        console.error('- Error using imported module:', error);
      }
    }).catch(error => {
      console.error('- Error importing analytics module:', error);
    });
  }
  
  // Check network requests
  console.log('\n4. Check Network tab in DevTools');
  console.log('- Look for requests to https://www.google-analytics.com/g/collect');
  console.log('- These requests indicate events are being sent to Google Analytics');
  
  console.log('\n5. Next steps:');
  console.log('- It may take up to 24-48 hours for events to appear in Google Analytics');
  console.log('- Check Debug View in Google Analytics for real-time events');
  console.log('- Ensure your Measurement ID (G-65SH3S3S35) is correct');
  console.log('- Make sure AdBlockers are disabled when testing');
  
  console.groupEnd();
})(); 