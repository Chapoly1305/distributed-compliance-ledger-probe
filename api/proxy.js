// Vercel Serverless Function (Node.js) - CORS Proxy for DCL nodes

export default async function handler(req, res) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const apiUrl = req.query.apiurl;

  if (!apiUrl) {
    return res.status(400).json({ error: 'Missing apiurl parameter' });
  }

  try {
    const response = await fetch(apiUrl, {
      method: req.method,
      headers: {
        'User-Agent': 'DCL-Network-Explorer/1.0',
        'Accept': 'application/json',
      },
    });

    const body = await response.text();

    res.setHeader('Content-Type', response.headers.get('Content-Type') || 'application/json');
    return res.status(response.status).send(body);
  } catch (error) {
    return res.status(502).json({ error: error.message });
  }
}
