export default {
  async fetch(request) {
    const url = new URL(request.url);
    
    // Support custom target host via header
    const targetHost = request.headers.get('x-target-host') || 'api.fyers.in';
    const targetUrl = `https://${targetHost}${url.pathname}${url.search}`;
    
    // Forward essential headers
    const headers = new Headers();
    for (const [key, value] of request.headers.entries()) {
      const k = key.toLowerCase();
      if (!['host', 'cf-ray', 'cf-connecting-ip', 'cf-visitor', 'x-forwarded-for', 'x-real-ip'].includes(k)) {
        headers.set(key, value);
      }
    }
    
    // Ensure critical headers for Fyers
    headers.set('Accept', 'application/json');
    if (!headers.has('User-Agent')) {
      headers.set('User-Agent', 'FyersAuthProxy/1.1');
    }

    try {
      // Correctly handle body for POST requests
      let body = null;
      if (request.method === 'POST' || request.method === 'PUT') {
        body = await request.arrayBuffer();
      }
      
      const newRequest = new Request(targetUrl, {
        method: request.method,
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
        s: 'error',
        code: 500,
        debug: {
          url: targetUrl,
          method: request.method
        }
      }), { 
        status: 500, 
        headers: { 'Content-Type': 'application/json' } 
      });
    }
  }
}
