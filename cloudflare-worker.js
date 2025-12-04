/**
 * DCL CORS Proxy - Cloudflare Worker
 * Proxies requests to DCL node RPC endpoints
 */

export default {
  async fetch(request, env, ctx) {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,HEAD,POST,OPTIONS",
      "Access-Control-Max-Age": "86400",
    };

    const url = new URL(request.url);

    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          ...corsHeaders,
          "Access-Control-Allow-Headers": request.headers.get("Access-Control-Request-Headers") || "*",
        },
      });
    }

    // Handle /corsproxy/ endpoint
    if (url.pathname.startsWith("/corsproxy/")) {
      const apiUrl = url.searchParams.get("apiurl");

      if (!apiUrl) {
        return new Response(JSON.stringify({ error: "Missing apiurl parameter" }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      try {
        // Use fetch with cf settings to bypass Cloudflare's IP blocking
        const response = await fetch(apiUrl, {
          method: request.method,
          headers: {
            "User-Agent": "DCL-Network-Explorer/1.0",
            "Accept": "application/json",
          },
          cf: {
            // Bypass Cloudflare's default behavior
            cacheTtl: 0,
            cacheEverything: false,
          },
        });

        const body = await response.text();

        return new Response(body, {
          status: response.status,
          headers: {
            "Content-Type": response.headers.get("Content-Type") || "application/json",
            ...corsHeaders,
          },
        });
      } catch (error) {
        return new Response(JSON.stringify({ error: error.message }), {
          status: 502,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }
    }

    // For all other requests, let assets handle it (returns undefined to fall through)
    return env.ASSETS.fetch(request);
  },
};
