export default {
  async fetch(request) {
    const url = new URL(request.url);
    const method = request.method;
    
    const targetHost = request.headers.get('x-target-host') || 'api.fyers.in';
    const targetUrl = `https://${targetHost}${url.pathname}${url.search}`;
    
    // Handle CORS preflight
    if (method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': '*',
          'Access-Control-Max-Age': '86400',
        }
      });
    }

    // Mirror headers carefully
    const headers = new Headers();
    for (const [key, value] of request.headers.entries()) {
      const k = key.toLowerCase();
      // Mask Cloudflare/Internal headers
      if (!['host', 'cf-ray', 'cf-connecting-ip', 'cf-visitor', 'x-forwarded-for', 'x-real-ip', 'cf-ipcountry', 'cf-ray', 'cf-worker'].includes(k)) {
        headers.set(key, value);
      }
    }
    
    // Force Fyers requirements
    headers.set('Host', targetHost);
    if (!headers.has('User-Agent')) {
      headers.set('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0');
    }

    try {
      let body = null;
      if (method !== 'GET' && method !== 'HEAD') {
        body = await request.arrayBuffer();
        // If we have a body, ensure Content-Length is set if possible (Cloudflare usually handles this but we're being safe)
        headers.set('Content-Length', body.byteLength.toString());
      }
      
      const response = await fetch(targetUrl, {
        method: method,
        headers: headers,
        body: body,
        redirect: 'follow'
      });

      // Mirror response headers
      const newResponse = new Response(response.body, response);
      newResponse.headers.set('Access-Control-Allow-Origin', '*');
      newResponse.headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      newResponse.headers.set('Access-Control-Allow-Headers', '*');
      newResponse.headers.set('X-Proxy-Status', `Mirror:${response.status}`);
      
      return newResponse;
    } catch (e) {
      return new Response(JSON.stringify({ 
        error: e.message, 
        message: "Proxy Internal Error: " + e.message,
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
