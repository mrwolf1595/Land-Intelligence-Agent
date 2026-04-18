const puppeteer = require('puppeteer');
const fs = require('fs');

(async () => {
    console.log('Launching browser...');
    const browser = await puppeteer.launch({ headless: false }); // Launch visible to "open the browser"
    const page = await browser.newPage();
    
    // Store captured requests
    const capturedApiCalls = [];

    // Listen to network responses
    page.on('response', async (response) => {
        const url = response.url();
        // Look for API calls. Often ejar index uses some specific endpoints. We'll catch everything containing 'api' or 'graphql'
        if (url.includes('/api/') || url.includes('/graphql') || url.includes('ejar') || url.includes('index')) {
            if (response.request().resourceType() === 'fetch' || response.request().resourceType() === 'xhr') {
                try {
                    const req = response.request();
                    let payload = null;
                    if (req.postData()) {
                        payload = req.postData();
                    }
                    
                    const buffer = await response.buffer();
                    const text = buffer.toString('utf-8');
                    
                    capturedApiCalls.push({
                        url: url,
                        method: req.method(),
                        payload: payload,
                        status: response.status(),
                        responseLength: text.length,
                        responsePreview: text.substring(0, 500)
                    });
                    console.log(`Captured API: ${url} [Status: ${response.status()}]`);
                } catch (e) {
                    console.log(`Failed to read response for ${url}: ${e.message}`);
                }
            }
        }
    });

    console.log('Navigating to Ejar Index...');
    await page.goto('https://www.ejar.sa/ar/ejar-index', { waitUntil: 'networkidle2', timeout: 60000 });
    
    // Wait for the page to fully load and maybe some scripts to run
    await new Promise(r => setTimeout(r, 8000));
    
    // Let's try to click on a city or dropdown if it exists to trigger more requests
    // However, just getting the initial index load is usually enough to find the endpoint.
    console.log('Saving captured APIs...');
    fs.writeFileSync('scratch/ejar_apis.json', JSON.stringify(capturedApiCalls, null, 2));

    await browser.close();
    console.log('Browser closed. Done.');
})();
