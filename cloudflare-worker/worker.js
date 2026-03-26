export default {
  async fetch(request) {
    const url = new URL(request.url);
    const method = request.method;
    
    // Support custom target host via header
    const targetHost = request.headers.get('x-target-host') || 'api.fyers.in';
    const targetUrl = `https://${targetHost}${url.pathname}${url.search}`;
    
    // Log for Cloudflare dashboard debugging
    console.log(`Proxying ${method} ${url.pathname} to ${targetUrl}`);
    
    // Handle CORS preflight
    if (method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization, Accept, x-target-host',
          'Access-Control-Max-Age': '86400',
        }
      });
    }

    // Forward essential headers
    const headers = new Headers();
    for (const [key, value] of request.headers.entries()) {
      const k = key.toLowerCase();
      if (!['host', 'cf-ray', 'cf-connecting-ip', 'cf-visitor', 'x-forwarded-for', 'x-real-ip', 'cf-ipcountry', 'cf-ray'].includes(k)) {
        headers.set(key, value);
      }
    }
    
    // Force specific headers for Fyers V3
    headers.set('Accept', 'application/json');
    if (!headers.has('User-Agent')) {
      headers.set('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    }

    try {
      let body = null;
      if (method === 'POST' || method === 'PUT') {
        body = await request.arrayBuffer();
      }
      
      const newRequest = new Request(targetUrl, {
        method: method,
        headers: headers,
        body: body,
        redirect: 'follow'
      });

      const response = await fetch(newRequest);
      
      // Clone response to add CORS headers
      const newResponse = new Response(response.body, response);
      newResponse.headers.set('Access-Control-Allow-Origin', '*');
      newResponse.headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      newResponse.headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept, x-target-host');
      
      return newResponse;
    } catch (e) {
      return new Response(JSON.stringify({ 
        error: e.message, 
        message: e.message, // Support legacy error structures
        s: 'error',
        code: 500,
        debug: { url: targetUrl, method: method }
      }), { 
        status: 500, 
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' } 
      });
    }
  }
}
