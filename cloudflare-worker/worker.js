export default {
  async fetch(request) {
    const url = new URL(request.url);
    const targetUrl = 'https://api.fyers.in' + url.pathname + url.search;
    
    // Only forward essential headers to avoid "tainted" or restricted headers
    // that might trigger security blocks (like cf-ray, cf-connecting-ip, etc.)
    const headers = new Headers();
    headers.set('Content-Type', request.headers.get('Content-Type') || 'application/json');
    headers.set('Accept', 'application/json');
    headers.set('User-Agent', 'FyersAuthProxy/1.0');

    // Create a new request based on the original one
    const newRequest = new Request(targetUrl, {
      method: request.method,
      headers: headers,
      // Forward the body for POST/PUT requests
      body: request.method !== 'GET' && request.method !== 'HEAD' ? await request.arrayBuffer() : null,
      redirect: 'follow'
    });

    try {
      const response = await fetch(newRequest);
      
      // Clone response to add CORS headers
      const newResponse = new Response(response.body, response);
      newResponse.headers.set('Access-Control-Allow-Origin', '*');
      newResponse.headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      newResponse.headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept');
      
      return newResponse;
    } catch (e) {
      return new Response(JSON.stringify({ 
        error: e.message, 
        s: 'error',
        code: 500
      }), { 
        status: 500, 
        headers: { 'Content-Type': 'application/json' } 
      });
    }
  }
}
