// Yahoo Finance crumb/cookie cache (persisted in-memory per isolate, ~5 min TTL)
let cachedCrumb = null;
let cachedCookie = null;
let crumbFetchedAt = 0;
const CRUMB_TTL_MS = 5 * 60 * 1000; // 5 minutes

async function getYahooCrumbAndCookie() {
  const now = Date.now();
  if (cachedCrumb && cachedCookie && (now - crumbFetchedAt) < CRUMB_TTL_MS) {
    return { crumb: cachedCrumb, cookie: cachedCookie };
  }

  try {
    // Step 1: Visit Yahoo Finance to get a consent/session cookie
    const consentRes = await fetch('https://fc.yahoo.com', {
      redirect: 'manual',
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
      }
    });

    let cookies = '';
    // Collect Set-Cookie headers
    const setCookieHeaders = consentRes.headers.getAll ? 
      consentRes.headers.getAll('set-cookie') : 
      [consentRes.headers.get('set-cookie')].filter(Boolean);
    
    for (const sc of setCookieHeaders) {
      if (sc) {
        const cookiePart = sc.split(';')[0];
        cookies += (cookies ? '; ' : '') + cookiePart;
      }
    }

    // Step 2: Fetch crumb using the cookie
    const crumbRes = await fetch('https://query2.finance.yahoo.com/v1/test/getcrumb', {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cookie': cookies
      }
    });

    if (crumbRes.ok) {
      const crumb = await crumbRes.text();
      if (crumb && crumb.length > 5 && crumb.length < 50) {
        cachedCrumb = crumb;
        cachedCookie = cookies;
        crumbFetchedAt = now;
        return { crumb: cachedCrumb, cookie: cachedCookie };
      }
    }
  } catch (e) {
    // Crumb fetch failed, continue without
    console.error('Crumb fetch error:', e.message);
  }

  return { crumb: null, cookie: null };
}

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
    
    // Force requirements
    headers.set('Host', targetHost);
    if (!headers.has('User-Agent')) {
      headers.set('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0');
    }

    // Yahoo Finance crumb injection for chart/quote endpoints
    const isYahoo = targetHost.includes('finance.yahoo.com');
    if (isYahoo && method === 'GET') {
      const { crumb, cookie } = await getYahooCrumbAndCookie();
      if (crumb && cookie) {
        headers.set('Cookie', cookie);
        // Inject crumb into URL if it's a chart or quoteSummary request that needs it
        const needsCrumb = url.pathname.includes('/v8/finance/chart/') || 
                          url.pathname.includes('/v7/finance/quote') ||
                          url.pathname.includes('/v10/finance/quoteSummary');
        if (needsCrumb) {
          const separator = url.search ? '&' : '?';
          const crumbUrl = `${targetUrl}${separator}crumb=${encodeURIComponent(crumb)}`;
          
          try {
            const response = await fetch(crumbUrl, {
              method: method,
              headers: headers,
              redirect: 'follow'
            });
            
            // If 401, invalidate crumb so next request re-fetches
            if (response.status === 401) {
              cachedCrumb = null;
              cachedCookie = null;
              crumbFetchedAt = 0;
            }

            const newResponse = new Response(response.body, response);
            newResponse.headers.set('Access-Control-Allow-Origin', '*');
            newResponse.headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
            newResponse.headers.set('Access-Control-Allow-Headers', '*');
            newResponse.headers.set('X-Proxy-Status', `YahooCrumb:${response.status}`);
            return newResponse;
          } catch (e) {
            // Fall through to normal proxy
          }
        }
      }
    }

    try {
      let body = null;
      if (method !== 'GET' && method !== 'HEAD') {
        body = await request.arrayBuffer();
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
