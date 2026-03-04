# TypeScript SDK Generation

This guide covers generating type-safe TypeScript clients from HawkAPI's OpenAPI specification.

## Prerequisites

- Node.js 16+ and npm
- HawkAPI instance with OpenAPI schema exposed at `/openapi.json`

## Method 1: openapi-generator-cli with typescript-fetch

The fastest way to generate a complete, production-ready SDK.

### Installation

```bash
npm install @openapitools/openapi-generator-cli --save-dev
```

### Configuration

Create `.openapi-generator-config.json`:

```json
{
  "packageName": "hawkapi-client",
  "packageVersion": "1.0.0",
  "moduleName": "HawkAPIClient"
}
```

### Generate SDK

```bash
# From your HawkAPI instance
npx openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g typescript-fetch \
  -o ./sdk \
  -c .openapi-generator-config.json

# Or from a saved schema file
npx openapi-generator-cli generate \
  -i ./openapi.json \
  -g typescript-fetch \
  -o ./sdk
```

### Output Structure

```
sdk/
├── apis/          # Generated API classes
├── models/        # Generated type definitions
├── index.ts       # Main export
└── configuration.ts
```

### Usage

```typescript
import { DefaultApi, Configuration } from './sdk';

const config = new Configuration({
  basePath: 'http://localhost:8000',
});

const api = new DefaultApi(config);

// Call generated methods with full type safety
const users = await api.listUsers();
const newUser = await api.createUser({ name: 'Alice' });
```

### Customization Options

Add to `.openapi-generator-config.json`:

```json
{
  "packageName": "hawkapi-client",
  "packageVersion": "1.0.0",
  "supportsES6": true,
  "enumPropertyNaming": "PascalCase",
  "withSeparateModelsAndApi": true,
  "apiPackage": "api",
  "modelPackage": "models"
}
```

## Method 2: openapi-typescript for Type Generation

Lightweight alternative that generates only TypeScript types, letting you write your own fetch wrappers.

### Installation

```bash
npm install openapi-typescript @hey-api/openapi-ts --save-dev
```

### Generate Types

```bash
# Generate types from OpenAPI schema
npx openapi-typescript http://localhost:8000/openapi.json -o ./src/types/api.ts

# Or from file
npx openapi-typescript ./openapi.json -o ./src/types/api.ts
```

### Generated Types Example

```typescript
// src/types/api.ts (auto-generated)
export interface User {
  id: number;
  name: string;
  email: string;
}

export interface CreateUserRequest {
  name: string;
  email: string;
}

// ... all your API types
```

### Write Custom Fetch Wrapper

```typescript
// src/client.ts
import type { paths } from './types/api';

type GetUsersResponse = paths['/users']['get']['responses']['200']['content']['application/json'];
type CreateUserRequest = paths['/users']['post']['requestBody']['content']['application/json'];
type CreateUserResponse = paths['/users']['post']['responses']['201']['content']['application/json'];

export class HawkAPIClient {
  private baseURL: string;

  constructor(baseURL: string = 'http://localhost:8000') {
    this.baseURL = baseURL;
  }

  async listUsers(): Promise<GetUsersResponse> {
    const response = await fetch(`${this.baseURL}/users`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async createUser(data: CreateUserRequest): Promise<CreateUserResponse> {
    const response = await fetch(`${this.baseURL}/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
}
```

## Method 3: Manual Fetch Wrapper

For simpler APIs or when you want maximum control.

### Setup

```bash
npm install --save-dev @types/node
# or
npm install --save-dev --legacy-peer-deps @types/fetch-api
```

### Implementation

```typescript
// src/client.ts
interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  headers?: Record<string, string>;
  body?: unknown;
  query?: Record<string, string | number | boolean>;
}

interface Response<T> {
  data: T;
  status: number;
  headers: Record<string, string>;
}

export class HawkAPIClient {
  private baseURL: string;
  private timeout: number;

  constructor(baseURL: string = 'http://localhost:8000', timeout: number = 30000) {
    this.baseURL = baseURL;
    this.timeout = timeout;
  }

  private async request<T>(path: string, options: RequestOptions = {}): Promise<Response<T>> {
    const url = new URL(path, this.baseURL);

    if (options.query) {
      Object.entries(options.query).forEach(([key, value]) => {
        url.searchParams.set(key, String(value));
      });
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url.toString(), {
        method: options.method || 'GET',
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`HTTP ${response.status}: ${error}`);
      }

      const data = await response.json();
      return {
        data,
        status: response.status,
        headers: Object.fromEntries(response.headers),
      };
    } finally {
      clearTimeout(timeoutId);
    }
  }

  // API Methods
  async listUsers() {
    return this.request<User[]>('/users');
  }

  async getUser(id: number) {
    return this.request<User>(`/users/${id}`);
  }

  async createUser(data: CreateUserRequest) {
    return this.request<User>('/users', {
      method: 'POST',
      body: data,
    });
  }

  async updateUser(id: number, data: UpdateUserRequest) {
    return this.request<User>(`/users/${id}`, {
      method: 'PUT',
      body: data,
    });
  }

  async deleteUser(id: number) {
    return this.request<void>(`/users/${id}`, {
      method: 'DELETE',
    });
  }
}
```

### Usage

```typescript
const client = new HawkAPIClient('http://localhost:8000');

// Fetch users
const response = await client.listUsers();
console.log(response.data);

// Create user
const newUser = await client.createUser({
  name: 'Alice',
  email: 'alice@example.com',
});

console.log(newUser.data);
```

## Publishing to npm

Once generated, publish your SDK as a package:

```bash
# Build/transpile if needed
npm run build

# Test locally
npm link

# In another project
npm link hawkapi-client

# Publish to npm registry
npm publish
```

Create `package.json` scripts:

```json
{
  "scripts": {
    "generate:sdk": "openapi-generator-cli generate -i http://localhost:8000/openapi.json -g typescript-fetch -o ./sdk",
    "build": "tsc",
    "test": "jest"
  }
}
```

## Recommendations

- **Full SDK**: Use `openapi-generator-cli` with `typescript-fetch` for production applications
- **Types Only**: Use `openapi-typescript` if you prefer lightweight dependencies and custom logic
- **Custom Wrapper**: Use manual fetch wrapper for small/simple APIs or when you need maximum control
- **Type Safety**: Always regenerate types when your HawkAPI schema changes
- **Version Management**: Pin generated SDK versions and keep them in sync with your API

## Troubleshooting

### No types generated
- Ensure OpenAPI schema at `/openapi.json` is valid: `curl http://localhost:8000/openapi.json | jq`
- Check that HawkAPI is running and responding

### Import errors
- Ensure TypeScript `target` is set to `ES2015` or higher in `tsconfig.json`
- Install type definitions if using methods that require them

### API mismatches
- Regenerate types whenever HawkAPI schema changes
- Use version pinning to catch breaking changes
