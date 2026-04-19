"""GraphiQL HTML template served for browser requests.

All CDN assets are pinned to exact versions and protected by Subresource
Integrity (SRI) hashes so a compromised CDN cannot inject arbitrary JS into
the developer's browser. Regenerate the hashes with::

    curl -sL <url> | openssl dgst -sha384 -binary | openssl base64 -A
"""

from __future__ import annotations

GRAPHIQL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>GraphiQL</title>
  <style>
    body { height: 100vh; margin: 0; overflow: hidden; }
    #graphiql { height: 100vh; }
  </style>
  <link rel="stylesheet"
    href="https://cdn.jsdelivr.net/npm/graphiql@3.0.9/graphiql.min.css"
    integrity="sha384-yz3/sqpuplkA7msMo0FE4ekg0xdwdvZ8JX9MVZREsxipqjU4h8IRfmAMRcb1QpUy"
    crossorigin="anonymous" />
</head>
<body>
  <div id="graphiql">Loading&hellip;</div>
  <script
    src="https://cdn.jsdelivr.net/npm/react@18.3.1/umd/react.production.min.js"
    integrity="sha384-DGyLxAyjq0f9SPpVevD6IgztCFlnMF6oW/XQGmfe+IsZ8TqEiDrcHkMLKI6fiB/Z"
    crossorigin="anonymous"
  ></script>
  <script
    src="https://cdn.jsdelivr.net/npm/react-dom@18.3.1/umd/react-dom.production.min.js"
    integrity="sha384-gTGxhz21lVGYNMcdJOyq01Edg0jhn/c22nsx0kyqP0TxaV5WVdsSH1fSDUf5YJj1"
    crossorigin="anonymous"
  ></script>
  <script
    src="https://cdn.jsdelivr.net/npm/graphiql@3.0.9/graphiql.min.js"
    integrity="sha384-Mjte+vxCWz1ZYCzszGHiJqJa5eAxiqI4mc3BErq7eDXnt+UGLXSEW7+i0wmfPiji"
    crossorigin="anonymous"
  ></script>
  <script>
    const root = ReactDOM.createRoot(document.getElementById('graphiql'));
    root.render(
      React.createElement(GraphiQL, {
        fetcher: GraphiQL.createFetcher({ url: window.location.pathname }),
      })
    );
  </script>
</body>
</html>
"""

__all__ = ["GRAPHIQL_HTML"]
