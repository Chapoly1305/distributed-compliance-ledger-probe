/**
 * DCL CORS Proxy - Cloudflare Worker
 *
 * Deploy: https://dash.cloudflare.com/ -> Workers & Pages -> Create
 * Usage: https://your-worker.workers.dev/corsproxy/?apiurl=http://13.52.115.12:26657/net_info
 */

export default {
  async fetch(request) {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,HEAD,POST,OPTIONS",
      "Access-Control-Max-Age": "86400",
    };

    const PROXY_ENDPOINT = "/corsproxy/";

    async function handleRequest(request) {
      const url = new URL(request.url);
      const apiUrl = url.searchParams.get("apiurl");

      if (!apiUrl) {
        return new Response(JSON.stringify({ error: "Missing apiurl parameter" }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      // Rewrite request to point to API URL
      const newRequest = new Request(apiUrl, {
        method: request.method,
        headers: { "Origin": new URL(apiUrl).origin },
      });

      let response = await fetch(newRequest);
      response = new Response(response.body, response);
      response.headers.set("Access-Control-Allow-Origin", "*");
      response.headers.append("Vary", "Origin");

      return response;
    }

    function handleOptions(request) {
      return new Response(null, {
        headers: {
          ...corsHeaders,
          "Access-Control-Allow-Headers": request.headers.get("Access-Control-Request-Headers") || "*",
        },
      });
    }

    const url = new URL(request.url);

    if (url.pathname.startsWith(PROXY_ENDPOINT)) {
      if (request.method === "OPTIONS") {
        return handleOptions(request);
      }
      return handleRequest(request);
    }

    // Landing page
    return new Response(`DCL CORS Proxy\n\nUsage: ${url.origin}${PROXY_ENDPOINT}?apiurl=<target_url>`, {
      headers: { "Content-Type": "text/plain" },
    });
  },
};
