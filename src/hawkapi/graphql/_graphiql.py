"""GraphiQL HTML template served for browser requests."""

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
    href="https://cdn.jsdelivr.net/npm/graphiql@3/graphiql.min.css" />
</head>
<body>
  <div id="graphiql">Loading&hellip;</div>
  <script
    crossorigin
    src="https://cdn.jsdelivr.net/npm/react@18/umd/react.production.min.js"
  ></script>
  <script
    crossorigin
    src="https://cdn.jsdelivr.net/npm/react-dom@18/umd/react-dom.production.min.js"
  ></script>
  <script
    crossorigin
    src="https://cdn.jsdelivr.net/npm/graphiql@3/graphiql.min.js"
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
