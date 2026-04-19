# Client SDK Codegen

HawkAPI ships a built-in client generator that turns your OpenAPI 3.1 spec into a
single-file, zero-dependency client SDK — no `openapi-generator-cli`, no Java, no Node
required.

## When to use

| Situation | Recommendation |
|-----------|---------------|
| You own both the server and the consumers | `hawkapi gen-client` — regenerate on every schema change |
| You need a quick typed client for a third-party API | `hawkapi gen-client --spec file.json` |
| You already rely on `openapi-generator-cli` | Migrate: the output is simpler and has no extra deps |
| Your API is large (100+ operations) | Still works; single-file output is intentional |

The generated Python client uses **`httpx` + `msgspec`** (same deps as HawkAPI itself).
The generated TypeScript client uses **native `fetch`** — no axios, no node-fetch.

## CLI usage

```bash
# From a live app (imports module, calls app.openapi())
hawkapi gen-client python --app myapp.main:app --out ./sdk/

# From a spec file
hawkapi gen-client python     --spec openapi.json --out ./sdk/
hawkapi gen-client typescript --spec openapi.json --out ./sdk/
```

Both commands write a single file (`client.py` or `client.ts`) to `--out` and print
the absolute path.

```
/absolute/path/to/sdk/client.py
```

## Generated Python client

```python
# sdk/client.py  (generated — do not edit)
from __future__ import annotations
from typing import Any, Literal
import httpx
import msgspec

class Item(msgspec.Struct):
    id: int
    name: str
    description: str | None = None

class Client:
    def __init__(self, base_url: str, *, headers: dict[str, str] | None = None) -> None: ...
    async def list_items(self, *, q: str | None = None) -> list[Item]: ...
    async def create_item(self, *, body: Item | None = None) -> Item: ...
    async def get_item(self, id: int) -> Item: ...
```

Usage with `async with`:

```python
import asyncio
from sdk.client import Client, Item

async def main() -> None:
    async with Client("https://api.example.com") as client:
        items = await client.list_items(q="hawk")
        print(items)

        new_item = await client.create_item(body=Item(id=0, name="hawk"))
        print(new_item)

asyncio.run(main())
```

The `Client` constructor also accepts a pre-built `httpx.AsyncClient`:

```python
import httpx
from sdk.client import Client

transport = httpx.AsyncHTTPTransport(retries=3)
async with Client(
    "https://api.example.com",
    client=httpx.AsyncClient(transport=transport),
) as c:
    item = await c.get_item(42)
```

## Generated TypeScript client

```ts
// sdk/client.ts  (generated — do not edit)

export interface Item {
  id: number;
  name: string;
  description?: string;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) { ... }
}

export interface ClientOptions {
  baseUrl: string;
  headers?: Record<string, string>;
  fetch?: typeof fetch;
}

export class Client {
  constructor(options: ClientOptions) { ... }
  async listItems(params?: { q?: string }): Promise<Item[]> { ... }
  async createItem(params?: { body?: Item }): Promise<Item> { ... }
  async getItem(params?: { id: number }): Promise<Item> { ... }
}
```

Usage in a TypeScript / ESM project:

```ts
import { Client } from "./sdk/client.js";

const client = new Client({ baseUrl: "https://api.example.com" });

const items = await client.listItems({ q: "hawk" });
console.log(items);
```

Pass a custom `fetch` (e.g. for testing or Node 18 polyfills):

```ts
import { Client } from "./sdk/client.js";

const client = new Client({
  baseUrl: "https://api.example.com",
  fetch: globalThis.fetch,   // or node-fetch, undici, etc.
});
```

## Regeneration workflow

Schema-driven regeneration keeps clients in sync automatically.

### justfile

```make
gen-client:
    hawkapi gen-client python     --app myapp.main:app --out sdk/python/
    hawkapi gen-client typescript --app myapp.main:app --out sdk/typescript/
    git add sdk/
```

### npm script (monorepo)

```json
{
  "scripts": {
    "gen-client": "hawkapi gen-client typescript --spec openapi.json --out src/api/"
  }
}
```

### Pre-commit hook

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: gen-client
      name: Regenerate API clients
      language: system
      entry: bash -c 'hawkapi gen-client python --app myapp.main:app --out sdk/'
      pass_filenames: false
```

### CI on schema change

```yaml
# .github/workflows/codegen.yml
on:
  push:
    paths:
      - "src/**/*.py"
jobs:
  regen:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: uv run hawkapi gen-client typescript --app myapp.main:app --out sdk/ts/
      - uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "chore: regenerate API clients"
```

## Known limitations (v1)

The following items are out of scope for the initial release and will be addressed
in later tiers:

- **No `$ref` chasing across external files** — only inline and `#/components/schemas/...`
  refs are resolved.
- **No `allOf` / deep composition** — composite schemas fall back to `Any` / `unknown`.
- **No multipart/form-data bodies** — only `application/json` request bodies are handled.
- **No authentication helpers** — `securitySchemes` are parsed but no auth header
  injection is generated automatically.
- **No streaming/SSE support** — responses are assumed to be fully-buffered JSON.
- **TypeScript: no `tsc` validation at generation time** — the output is well-formed but
  is not type-checked during codegen (no Node required at generation time).
- **Single server URL only** — only `servers[0].url` is used as `base_url`.
