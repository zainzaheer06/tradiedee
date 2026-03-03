# NevoxAI API Key System - Complete Documentation

**Version:** 1.1
**Last Updated:** February 13, 2026
**Author:** System Documentation

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Database Schema](#3-database-schema)
4. [Service Layer](#4-service-layer)
5. [API Routes](#5-api-routes)
6. [Authentication Flow](#6-authentication-flow)
7. [Security Implementation](#7-security-implementation)
8. [User Interface](#8-user-interface)
9. [Migration Scripts](#9-migration-scripts)
10. [Usage Examples](#10-usage-examples)
11. [Line-by-Line Code Explanations](#11-line-by-line-code-explanations)

---

## 1. System Overview

### Purpose
The NevoxAI API Key System provides secure authentication for external integrations to programmatically initiate voice calls through the platform.

### Key Features
- ✅ **One key per user** - Each user has a single active API key
- ✅ **Secure storage** - Keys are hashed with SHA-256 (never stored in plain text)
- ✅ **Usage tracking** - Tracks total calls and last usage timestamp
- ✅ **Revocable** - Keys can be revoked and regenerated
- ✅ **Prefix display** - Shows first 12 characters for identification
- ✅ **Web UI** - User-friendly management interface
- ✅ **Rate limiting** - Redis-backed per-user rate limiting (200 calls/hour)
- ✅ **Rate limit headers** - Standard `X-RateLimit-*` headers on every response

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     NevoxAI Platform                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐      ┌──────────────┐     ┌───────────┐ │
│  │   Database   │◄────►│   Service    │◄───►│  Routes   │ │
│  │  (ApiKey)    │      │   Layer      │     │ (api_v1)  │ │
│  └──────────────┘      └──────────────┘     └───────────┘ │
│         ▲                      ▲                    ▲       │
│         │                      │                    │       │
│         └──────────────────────┴────────────────────┘       │
│                                                              │
│  ┌──────────────┐      ┌──────────────────────────────┐    │
│  │    Redis     │◄────►│  Authentication + Rate Limit  │    │
│  │ (Rate Limit) │      │     @require_api_key          │    │
│  └──────────────┘      └──────────────────────────────┘    │
│                           ▲                                 │
└───────────────────────────┼─────────────────────────────────┘
                            │
                            │ X-API-Key: nvx_abc123...
                            │
                   ┌────────┴────────┐
                   │  External API   │
                   │   Integration   │
                   └─────────────────┘
```

---

## 2. Architecture

### Design Patterns

**1. Service Layer Pattern**
- Business logic separated from routes
- `ApiKeyService` handles all key operations
- Single responsibility principle

**2. Decorator Pattern**
- `@require_api_key` decorator for route protection
- Reusable across multiple endpoints
- Clean separation of concerns

**3. Repository Pattern**
- SQLAlchemy ORM for database operations
- Model layer abstracts database structure

### File Structure

```
nevoxai-project/
├── models.py                          # Database models
│   └── class ApiKey                   # API key data model
│
├── services/
│   ├── api_key_service.py            # Business logic layer
│   │   └── class ApiKeyService       # Key generation, validation
│   └── api_rate_limiter.py           # Redis-based rate limiting
│       └── class APIRateLimiter      # Per-user sliding window counter
│
├── routes/
│   ├── api_v1.py                     # API endpoints
│   │   ├── @require_api_key          # Auth + rate limit decorator
│   │   ├── add_rate_limit_headers()  # Response header middleware
│   │   ├── POST /api/v1/calls/outbound
│   │   ├── GET  /api/v1/agents
│   │   └── Settings UI routes
│   │
│   └── public_api.py                 # Public endpoints (different auth)
│
├── templates/
│   └── settings/
│       └── api_keys.html             # Management UI
│
└── scripts/
    ├── migrations/
    │   └── migrate_apikey.py         # SQLite migration
    └── db/
        └── add_apikey_table.py       # PostgreSQL migration
```

---

## 3. Database Schema

### ApiKey Model

**File:** `models.py` (lines 233-262)

```python
class ApiKey(db.Model):
    """
    API Keys for external integrations
    One key per user - used for /api/v1/* endpoints
    """
    __tablename__ = 'api_key'

    # Primary Key
    id = db.Column(db.Integer, primary_key=True)

    # Foreign Key (One-to-One with User)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'),
                       nullable=False, unique=True)

    # Security Fields
    key_hash = db.Column(db.String(64), unique=True, nullable=False)
    key_prefix = db.Column(db.String(12), nullable=False)

    # Metadata
    name = db.Column(db.String(100), default='Default API Key')
    is_active = db.Column(db.Boolean, default=True)

    # Usage Tracking
    last_used_at = db.Column(db.DateTime, nullable=True)
    total_calls = db.Column(db.Integer, default=0)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    revoked_at = db.Column(db.DateTime, nullable=True)

    # Relationship
    user = db.relationship('User', backref=db.backref('api_key', uselist=False))
```

### Field Explanations

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `id` | Integer | Primary key | `1` |
| `user_id` | Integer | Links to user (UNIQUE) | `42` |
| `key_hash` | String(64) | SHA-256 hash of full key | `a1b2c3...` (64 chars) |
| `key_prefix` | String(12) | Display prefix | `nvx_a1b2c3...` |
| `name` | String(100) | User-defined name | `"Production API Key"` |
| `is_active` | Boolean | Key active status | `True`/`False` |
| `last_used_at` | DateTime | Last API call timestamp | `2026-02-12 13:45:00` |
| `total_calls` | Integer | Total API calls made | `1234` |
| `created_at` | DateTime | Key creation time | `2026-02-10 09:00:00` |
| `revoked_at` | DateTime | Revocation timestamp | `2026-02-12 14:00:00` or `NULL` |

### Database Constraints

1. **Primary Key:** `id` (auto-increment)
2. **Unique Constraints:**
   - `user_id` - One key per user
   - `key_hash` - Prevents duplicate keys
3. **Foreign Key:** `user_id` → `user(id)` ON DELETE CASCADE
4. **Indexes:**
   - `idx_api_key_user_id` on `user_id`
   - `idx_api_key_hash` on `key_hash`
   - `idx_api_key_active` on `is_active`

---

## 4. Service Layer

### ApiKeyService Class

**File:** `services/api_key_service.py`

#### Class Overview

```python
class ApiKeyService:
    """
    Service for managing API keys

    Key Format: nvx_{32_random_chars}
    Storage: SHA-256 hash (never store raw key)
    """

    PREFIX = "nvx_"
    KEY_LENGTH = 32  # Characters after prefix
```

### Method: `generate_key()`

**Lines:** 25-47

**Purpose:** Generate a new cryptographically secure API key

**Process:**
```
1. Generate 32 random hex characters using secrets.token_hex()
2. Prepend prefix "nvx_" → "nvx_a1b2c3d4..."
3. Hash full key with SHA-256 → Store in database
4. Create display prefix (first 12 chars) → "nvx_a1b2c3..."
5. Return (raw_key, hash, prefix)
```

**Returns:**
- `raw_key`: Full key (show ONCE to user)
- `key_hash`: SHA-256 hash for database
- `key_prefix`: Display identifier

**Example:**
```python
raw_key = "nvx_a1b2c3d4e5f6789012345678901234"
key_hash = "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d"
key_prefix = "nvx_a1b2c3d4..."
```

---

### Method: `_hash_key(raw_key)`

**Lines:** 49-59

**Purpose:** Hash an API key using SHA-256

**Security Note:**
- Uses SHA-256 (one-way hash)
- Cannot reverse hash to get original key
- Protects against database breaches

**Code:**
```python
def _hash_key(self, raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()
```

---

### Method: `validate_key(raw_key)`

**Lines:** 61-106

**Purpose:** Validate an incoming API key and return the associated user

**Process Flow:**
```
1. Check if key exists
   ├─ No → Return None
   └─ Yes → Continue

2. Check if key starts with "nvx_"
   ├─ No → Return None (invalid format)
   └─ Yes → Continue

3. Hash the incoming key
   └─ Generate SHA-256 hash

4. Query database
   └─ SELECT * FROM api_key WHERE key_hash=? AND is_active=True

5. If found:
   ├─ Update last_used_at = now()
   ├─ Increment total_calls += 1
   ├─ Commit changes
   └─ Return user object

6. If not found:
   └─ Return None
```

**Usage Tracking:**
```python
api_key.last_used_at = datetime.utcnow()
api_key.total_calls += 1
db.session.commit()
```

---

### Method: `create_key_for_user(user_id, name)`

**Lines:** 108-150

**Purpose:** Create a new API key for a user (replaces existing key)

**Important Behavior:** **ONE KEY PER USER**
- If user has an existing key → Mark it as revoked
- Generate new key
- Store in database

**Process:**
```python
1. Check for existing key
   └─ SELECT * FROM api_key WHERE user_id=?

2. If exists:
   ├─ Set is_active = False
   ├─ Set revoked_at = now()
   └─ Commit changes

3. Generate new key
   └─ Call generate_key()

4. Create new ApiKey record
   ├─ user_id = user_id
   ├─ key_hash = generated hash
   ├─ key_prefix = generated prefix
   ├─ name = provided name
   └─ is_active = True

5. Insert into database
   └─ db.session.add(new_key)
   └─ db.session.commit()

6. Return raw key (show to user ONCE)
```

**Security:** Raw key is only returned ONCE. Never stored.

---

### Method: `revoke_key(user_id)`

**Lines:** 152-180

**Purpose:** Revoke (deactivate) a user's API key

**Process:**
```python
1. Find active key
   └─ SELECT * FROM api_key WHERE user_id=? AND is_active=True

2. If found:
   ├─ Set is_active = False
   ├─ Set revoked_at = now()
   └─ Return True

3. If not found:
   └─ Return False
```

**Note:** Key is NOT deleted, only marked inactive for audit trail.

---

### Method: `get_key_info(user_id)`

**Lines:** 182-208

**Purpose:** Get API key information for display (NEVER returns raw key)

**Returns:**
```python
{
    'id': 1,
    'key_prefix': 'nvx_a1b2c3...',
    'name': 'Production Key',
    'is_active': True,
    'created_at': datetime(2026, 2, 10, 9, 0, 0),
    'last_used_at': datetime(2026, 2, 12, 13, 45, 0),
    'total_calls': 1234,
    'revoked_at': None
}
```

**Security:** Only returns prefix, never full key.

---

### Singleton Instance

**Line:** 212

```python
api_key_service = ApiKeyService()
```

**Usage:** Import and use everywhere
```python
from services.api_key_service import api_key_service

# Generate key
raw_key = api_key_service.create_key_for_user(user_id=42)

# Validate key
user = api_key_service.validate_key("nvx_abc123...")
```

---

## 5. API Routes

### File: `routes/api_v1.py`

### Authentication Decorator: `@require_api_key`

**Lines:** 29-98

**Purpose:** Protect API endpoints with key authentication **and** per-user rate limiting

**How It Works:**

```python
@api_v1_bp.route('/calls/outbound', methods=['POST'])
@require_api_key  # ← Auth + rate limit applied here
def create_outbound_call():
    from flask import g
    user = g.current_user  # ← User is set by decorator
    # ... rest of endpoint logic
```

**Process Flow:**

```
1. Extract API key from HTTP header
   └─ X-API-Key: nvx_abc123...

2. Check if header exists
   ├─ No → Return 401 "API key required"
   └─ Yes → Continue

3. Validate key using api_key_service.validate_key()
   ├─ Invalid → Return 401 "Invalid API key"
   └─ Valid → user object returned

4. Check if user is approved
   ├─ Not approved → Return 403 "Account not approved"
   └─ Approved → Continue

5. Check rate limit (Redis: api_rate:{user_id})
   ├─ Exceeded → Return 429 with Retry-After header
   └─ Within limit → Continue

6. Store user + rate limit info in Flask's g object
   └─ g.current_user = user
   └─ g.rate_limit, g.rate_limit_remaining, g.rate_limit_reset

7. Execute the route function
   └─ Route can access g.current_user
```

**Code:**
```python
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import g

        # Extract API key from header
        api_key = request.headers.get('X-API-Key')

        if not api_key:
            return jsonify({'error': 'API key required', 'code': 'MISSING_API_KEY'}), 401

        # Validate key
        user = api_key_service.validate_key(api_key)

        if not user:
            return jsonify({'error': 'Invalid API key', 'code': 'INVALID_API_KEY'}), 401

        # Check approval
        if not user.is_approved:
            return jsonify({'error': 'Account not approved', 'code': 'ACCOUNT_NOT_APPROVED'}), 403

        # ---- Rate Limiting (per-user, Redis-backed) ----
        allowed, remaining, limit, reset_seconds = api_rate_limiter.check_and_increment(user.id)

        g.rate_limit = limit
        g.rate_limit_remaining = remaining
        g.rate_limit_reset = reset_seconds

        if not allowed:
            resp = jsonify({
                'error': 'Rate limit exceeded. Try again later.',
                'code': 'RATE_LIMIT_EXCEEDED',
                'retry_after_seconds': reset_seconds
            })
            resp.headers['Retry-After'] = str(reset_seconds)
            resp.headers['X-RateLimit-Limit'] = str(limit)
            resp.headers['X-RateLimit-Remaining'] = '0'
            resp.headers['X-RateLimit-Reset'] = str(reset_seconds)
            return resp, 429

        # Store user in Flask context
        g.current_user = user
        return f(*args, **kwargs)

    return decorated_function
```

### Response Header Middleware: `add_rate_limit_headers()`

**Purpose:** Attach rate limit and version headers to every API v1 response

**Code:**
```python
@api_v1_bp.after_request
def add_rate_limit_headers(response):
    from flask import g

    if hasattr(g, 'rate_limit'):
        response.headers['X-RateLimit-Limit'] = str(g.rate_limit)
        response.headers['X-RateLimit-Remaining'] = str(g.rate_limit_remaining)
        response.headers['X-RateLimit-Reset'] = str(g.rate_limit_reset)

    response.headers['X-API-Version'] = '1.0'
    return response
```

**Response Headers (added to every authenticated response):**

| Header | Example | Meaning |
|--------|---------|--------|
| `X-RateLimit-Limit` | `200` | Max requests per window |
| `X-RateLimit-Remaining` | `187` | Requests left in current window |
| `X-RateLimit-Reset` | `2847` | Seconds until window resets |
| `X-API-Version` | `1.0` | API version |
| `Retry-After` | `2847` | (429 only) Seconds to wait before retrying |

---

### Endpoint: `POST /api/v1/calls/outbound`

**Lines:** 143-287

**Purpose:** Initiate an outbound voice call via API

**Authentication:** Requires API key (`@require_api_key`)

**Request:**
```json
{
  "agent_id": 12,
  "phone_number": "+966501234567",
  "context": {
    "customer_name": "Ahmed",
    "order_id": "ORD-456"
  }
}
```

**Headers:**
```
Content-Type: application/json
X-API-Key: nvx_abc123def456...
```

**Process Flow:**

```
1. Authenticate user (via @require_api_key)
   └─ user = g.current_user

2. Parse request body
   └─ Extract: agent_id, phone_number, context

3. Validate required fields
   ├─ Missing agent_id → 400 error
   └─ Missing phone_number → 400 error

4. Verify agent ownership
   └─ SELECT * FROM agent WHERE id=? AND user_id=?
   ├─ Not found → 404 error
   └─ Found → Continue

5. Check user minutes balance
   └─ user.minutes_balance <= 0 → 402 error

6. Format phone number
   └─ +966501234567 or 966501234567

7. Get outbound trunk ID
   └─ user.outbound_trunk_id or ENV variable

8. Generate unique room name
   └─ "call-{agent_id}-api-{username}-{timestamp}"

9. Make LiveKit call
   └─ asyncio.run(make_livekit_call(...))

10. Create call log entry
    └─ INSERT INTO call_log (...)

11. Return success response
```

**Response (Success):**
```json
{
  "success": true,
  "call_id": 789,
  "room_name": "call-12-api-john-1707654321",
  "status": "initiated",
  "agent_id": 12,
  "phone_number": "966501234567"
}
```

**Error Responses:**

| Code | Error | Meaning |
|------|-------|---------|
| 400 | `MISSING_AGENT_ID` | agent_id not in request |
| 400 | `MISSING_PHONE_NUMBER` | phone_number not in request |
| 401 | `MISSING_API_KEY` | No X-API-Key header |
| 401 | `INVALID_API_KEY` | API key invalid/revoked |
| 402 | `INSUFFICIENT_MINUTES` | No minutes remaining |
| 403 | `ACCOUNT_NOT_APPROVED` | User not approved |
| 404 | `AGENT_NOT_FOUND` | Agent doesn't exist or access denied |
| 500 | `NO_TRUNK_CONFIGURED` | No SIP trunk configured |
| 500 | `CALL_FAILED` | LiveKit error |

---

### Endpoint: `GET /api/v1/agents`

**Lines:** 300-331

**Purpose:** List all agents available to the authenticated user

**Authentication:** Requires API key

**Response:**
```json
{
  "success": true,
  "agents": [
    {
      "id": 1,
      "name": "Sales Agent",
      "voice_name": "Fatima",
      "created_at": "2026-02-10T09:00:00"
    },
    {
      "id": 2,
      "name": "Support Agent",
      "voice_name": "Ahmed",
      "created_at": "2026-02-11T14:30:00"
    }
  ]
}
```

---

### Endpoint: `GET /api/v1/health`

**Lines:** 290-297

**Purpose:** Health check endpoint (NO authentication required)

**Response:**
```json
{
  "status": "healthy",
  "service": "NevoxAI API v1",
  "timestamp": "2026-02-12T13:45:00+03:00"
}
```

---

### UI Endpoints (Settings Page)

**1. GET `/api/v1/settings/api-keys`** (Lines 340-355)
- Display API key management page
- Requires login + approval
- Shows key info, usage stats
- Handles "new key" flash from session

**2. POST `/api/v1/settings/api-keys/generate`** (Lines 358-376)
- Generate or regenerate API key
- Stores raw key in session (show once)
- Redirects to settings page

**3. POST `/api/v1/settings/api-keys/revoke`** (Lines 379-393)
- Revoke current API key
- Marks as inactive
- Redirects to settings page

---

## 6. Authentication Flow

### Complete Authentication Sequence

```
┌─────────────┐
│   Client    │
│  (External  │
│   System)   │
└──────┬──────┘
       │
       │ 1. HTTP Request
       │    POST /api/v1/calls/outbound
       │    Headers:
       │      X-API-Key: nvx_abc123...
       │
       ▼
┌─────────────────────────────────────────┐
│      Flask Application                  │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │  @require_api_key Decorator       │ │
│  │                                   │ │
│  │  2. Extract header                │ │
│  │     api_key = request.headers.get│ │
│  │               ('X-API-Key')       │ │
│  │                                   │ │
│  │  3. Validate key                  │ │
│  │     user = api_key_service        │ │
│  │            .validate_key(api_key) │ │
│  └──────────┬────────────────────────┘ │
│             │                           │
│             ▼                           │
│  ┌───────────────────────────────────┐ │
│  │  ApiKeyService                    │ │
│  │                                   │ │
│  │  4. Check prefix                  │ │
│  │     if not key.startswith("nvx_")│ │
│  │        return None                │ │
│  │                                   │ │
│  │  5. Hash key                      │ │
│  │     hash = sha256(api_key)        │ │
│  │                                   │ │
│  │  6. Query database                │ │
│  │     SELECT * FROM api_key         │ │
│  │     WHERE key_hash=? AND          │ │
│  │           is_active=True          │ │
│  └──────────┬────────────────────────┘ │
│             │                           │
│             ▼                           │
│  ┌───────────────────────────────────┐ │
│  │  Database (PostgreSQL/SQLite)     │ │
│  │                                   │ │
│  │  api_key table:                   │ │
│  │  ┌───┬────────┬──────────┬────┐  │ │
│  │  │id │user_id │key_hash  │act.│  │ │
│  │  ├───┼────────┼──────────┼────┤  │ │
│  │  │1  │42      │ef2d127...│ T  │  │ │
│  │  └───┴────────┴──────────┴────┘  │ │
│  │                                   │ │
│  │  7. Return user if found          │ │
│  └──────────┬────────────────────────┘ │
│             │                           │
│             ▼                           │
│  ┌───────────────────────────────────┐ │
│  │  Back to Decorator                │ │
│  │                                   │ │
│  │  8. Check user approval           │ │
│  │     if not user.is_approved:      │ │
│  │        return 403                 │ │
│  │                                   │ │
│  │  9. Rate limit check (Redis)      │ │
│  │     api_rate_limiter              │ │
│  │       .check_and_increment()      │ │
│  │     key: api_rate:{user_id}       │ │
│  │     if exceeded → return 429      │ │
│  │                                   │ │
│  │  10. Store in Flask context       │ │
│  │      g.current_user = user        │ │
│  │      g.rate_limit = limit         │ │
│  │      g.rate_limit_remaining       │ │
│  │                                   │ │
│  │  11. Update usage stats           │ │
│  │      last_used_at = now()         │ │
│  │      total_calls += 1             │ │
│  └──────────┬────────────────────────┘ │
│             │                           │
│             ▼                           │
│  ┌───────────────────────────────────┐ │
│  │  Route Handler                    │ │
│  │  create_outbound_call()           │ │
│  │                                   │ │
│  │  12. Access authenticated user    │ │
│  │      user = g.current_user        │ │
│  │                                   │ │
│  │  13. Execute business logic       │ │
│  │      - Validate agent ownership   │ │
│  │      - Check minutes balance      │ │
│  │      - Initiate call              │ │
│  └──────────┬────────────────────────┘ │
│             │                           │
│             ▼                           │
│  ┌───────────────────────────────────┐ │
│  │  after_request: Headers           │ │
│  │                                   │ │
│  │  X-RateLimit-Limit: 200          │ │
│  │  X-RateLimit-Remaining: 187      │ │
│  │  X-RateLimit-Reset: 2847         │ │
│  │  X-API-Version: 1.0              │ │
│  └──────────┬────────────────────────┘ │
│             │                           │
└─────────────┼───────────────────────────┘
              │
              ▼
       ┌─────────────┐
       │  Response   │
       │  200 OK     │
       └─────────────┘
```

---

## 7. Security Implementation

### 1. Key Storage Security

**Problem:** Storing API keys in plain text is a security risk

**Solution:** Hash keys with SHA-256

```python
# NEVER store this
raw_key = "nvx_abc123def456..."

# ALWAYS store this (one-way hash)
key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
# Result: "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d"
```

**Benefits:**
- ✅ Database breach doesn't expose keys
- ✅ Cannot reverse-engineer original key
- ✅ Same security model as password hashing

---

### 2. Cryptographic Key Generation

**Uses `secrets` module** (not `random`)

```python
# GOOD ✅
random_part = secrets.token_hex(16)  # Cryptographically secure
# Result: "a1b2c3d4e5f6789012345678901234"

# BAD ❌
random_part = ''.join(random.choices(string.ascii_lowercase, k=32))
# Predictable, not secure
```

**Why `secrets`?**
- Designed for security-sensitive operations
- Uses OS-provided randomness
- Unpredictable and cryptographically strong

---

### 3. Prefix Validation

**Prevents invalid key formats**

```python
if not raw_key.startswith(self.PREFIX):
    return None
```

**Benefits:**
- Fast rejection of invalid keys
- No database query for malformed keys
- Prevents brute force attempts

---

### 4. Active Status Check

```python
api_key = ApiKey.query.filter_by(
    key_hash=key_hash,
    is_active=True  # ← Only active keys
).first()
```

**Revoked keys cannot be used** even if hash matches

---

### 5. User Approval Check

```python
if not user.is_approved:
    return jsonify({'error': 'Account not approved'}), 403
```

**Prevents unauthorized API access** before admin approval

---

### 6. One Key Per User

```python
user_id = db.Column(db.Integer, ..., unique=True)
```

**Database constraint** prevents multiple active keys

**Benefits:**
- Simplified key management
- Easy revocation
- Clear audit trail

---

### 7. Audit Trail

Keys are **never deleted**, only revoked:

```python
api_key.is_active = False
api_key.revoked_at = datetime.utcnow()
```

**Maintains history for:**
- Security audits
- Compliance requirements
- Incident investigation

---

### 8. Rate Limiting (Implemented)

**File:** `services/api_rate_limiter.py`

**Type:** Redis-backed sliding window counter (per user)

**Configuration:**
- Default limit: **200 calls per hour** per user
- Window: 3600 seconds (1 hour)
- Fail-open: If Redis is unavailable, all requests pass

**How It Works:**

```python
from services.api_rate_limiter import api_rate_limiter

# Check and increment (called inside @require_api_key)
allowed, remaining, limit, reset_seconds = api_rate_limiter.check_and_increment(user.id)

# Get usage info (for display/debugging)
usage = api_rate_limiter.get_usage(user.id)
# {'current': 13, 'limit': 200, 'remaining': 187, 'reset_seconds': 2847, 'redis_available': True}

# Admin reset
api_rate_limiter.reset(user.id)
```

**Redis Key Pattern:**
```
api_rate:{user_id}    TTL: 3600s (auto-expires)
```

**Example:**
```
# User 42 makes their 1st call
Redis: INCR api_rate:42 → 1
Redis: EXPIRE api_rate:42 3600
→ allowed=True, remaining=199

# User 42 makes their 200th call
Redis: INCR api_rate:42 → 200
→ allowed=True, remaining=0

# User 42 makes their 201st call
Redis: INCR api_rate:42 → 201
→ allowed=False, remaining=0
→ HTTP 429 with Retry-After header
```

**Response when rate limited (HTTP 429):**
```json
{
  "success": false,
  "error": "Rate limit exceeded. Try again later.",
  "code": "RATE_LIMIT_EXCEEDED",
  "retry_after_seconds": 2847
}
```

**Headers:**
```
Retry-After: 2847
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 2847
```

**Design Decisions:**
- Uses existing `redis_service` singleton (no new dependencies)
- Fail-open: Redis down = no rate limiting (app keeps working)
- Sliding window counter via `INCR` + `EXPIRE` (atomic, fast)
- Per-user, not per-key (since one key per user)

---

## 8. User Interface

### File: `templates/settings/api_keys.html`

### Page Structure

```
┌────────────────────────────────────────────┐
│           API Keys - Nevox AI              │
├────────────────────────────────────────────┤
│                                            │
│  ┌──────────────────────────────────────┐ │
│  │  🔑 Default API Key                  │ │
│  │  Created Feb 10, 2026    [Active]    │ │
│  │                                       │ │
│  │  API Key: nvx_a1b2c3...              │ │
│  │                                       │ │
│  │  Total API Calls: 1234                │ │
│  │  Last Used: Feb 12, 2026 13:45       │ │
│  │                                       │ │
│  │  [Regenerate Key]  [Revoke]          │ │
│  └──────────────────────────────────────┘ │
│                                            │
│  ┌──────────────────────────────────────┐ │
│  │  API Usage                            │ │
│  │  Endpoint: POST /api/v1/calls/outbound│ │
│  │                                       │ │
│  │  cURL Example:                        │ │
│  │  curl -X POST ...                     │ │
│  │                                       │ │
│  │  Python Example:                      │ │
│  │  import requests ...                  │ │
│  └──────────────────────────────────────┘ │
│                                            │
│  ┌──────────────────────────────────────┐ │
│  │  Response Codes                       │ │
│  │  200 - Success                        │ │
│  │  401 - Invalid API key                │ │
│  │  402 - Insufficient minutes           │ │
│  └──────────────────────────────────────┘ │
└────────────────────────────────────────────┘
```

### Key Generation Modal

**Shown once after generating key:**

```
┌─────────────────────────────────────────┐
│  ✓ API Key Generated                    │
│  Copy it now - you won't see it again!  │
│                                         │
│  ⚠️  Important: This is the only time   │
│     you'll see the full API key.        │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ nvx_abc123def456...               │ │
│  │                          [Copy]   │ │
│  └───────────────────────────────────┘ │
│                                         │
│  [I've Saved My Key]                    │
└─────────────────────────────────────────┘
```

**JavaScript Copy Function:**

```javascript
function copyApiKey() {
    const keyValue = document.getElementById('api-key-value').textContent;
    navigator.clipboard.writeText(keyValue).then(() => {
        // Show "Copied!" feedback
        btn.innerHTML = '<i class="bi bi-check mr-1"></i>Copied!';
        btn.classList.add('bg-green-600');
    });
}
```

---

### UI Features

**1. Status Badges**
```html
{% if api_key_info.is_active %}
    <span class="badge-success">Active</span>
{% else %}
    <span class="badge-danger">Revoked</span>
{% endif %}
```

**2. Usage Stats Display**
```html
<p class="text-2xl font-bold">{{ api_key_info.total_calls or 0 }}</p>
```

**3. Confirmation Dialogs**
```javascript
onclick="return confirm('This will invalidate your current key. Continue?')"
```

**4. Key Prefix Display**
```html
<code class="text-lg font-mono">{{ api_key_info.key_prefix }}</code>
```

**5. Live Examples**
```html
<pre><code>curl -X POST {{ request.host_url }}api/v1/calls/outbound \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{...}'</code></pre>
```

---

## 9. Migration Scripts

### SQLite Migration

**File:** `scripts/migrations/migrate_apikey.py`

**Purpose:** Add api_key table to local/development SQLite database

**Usage:**
```bash
cd /root/nevoxai-project-2
python scripts/migrations/migrate_apikey.py
```

**What it does:**
1. Checks if database exists
2. Creates `api_key` table if missing
3. Adds indexes
4. Verifies table structure
5. **Safe to run multiple times**

**Output:**
```
Database: /root/nevoxai-project-2/instance/voice_agent.db
✓ api_key table exists (created if missing)
✓ Index exists: idx_api_key_user_id
✓ Index exists: idx_api_key_hash
✓ Index exists: idx_api_key_active
  Existing columns: 10
  ✓ All required columns present

✓ Migration complete!
```

---

### PostgreSQL Migration

**File:** `add_apikey_table.py`

**Purpose:** Add api_key table to production PostgreSQL database

**Usage:**
```bash
python add_apikey_table.py
```

**Configuration:**
```python
DB_URL = "postgresql://nevox_prod:tdQJ%40u57SrVZg4v@pgm-...5432/nevox_prod"
```

**Note:** `@` symbol in password must be URL-encoded as `%40`

**Process:**
1. Connects to PostgreSQL
2. Creates table with constraints
3. Adds indexes
4. Verifies structure
5. Shows detailed column information

**Output:**
```
🔌 Connecting to production database...
📝 Creating api_key table...
✅ Table created successfully!
🔍 Creating indexes...
✅ Indexes created successfully!

📋 Verifying table structure:
================================================================================
Column Name          Data Type            Max Length      Nullable
================================================================================
id                   integer              N/A             NO
user_id              integer              N/A             NO
key_hash             character varying    64              NO
key_prefix           character varying    12              NO
...
================================================================================

🔗 Checking foreign key constraints:
  - api_key_key_hash_key: UNIQUE
  - api_key_pkey: PRIMARY KEY
  - api_key_user_id_key: UNIQUE
  - fk_api_key_user: FOREIGN KEY

✅ API Key table setup complete!
```

---

## 10. Usage Examples

### Example 1: cURL

```bash
curl -X POST https://nevoxai.com/api/v1/calls/outbound \
  -H "Content-Type: application/json" \
  -H "X-API-Key: nvx_abc123def456789012345678901234" \
  -d '{
    "agent_id": 12,
    "phone_number": "+966501234567",
    "context": {
      "customer_name": "Ahmed Al-Saud",
      "order_id": "ORD-789",
      "order_total": "299.99 SAR"
    }
  }'
```

**Response:**
```json
{
  "success": true,
  "call_id": 1234,
  "room_name": "call-12-api-john-1707654321",
  "status": "initiated",
  "agent_id": 12,
  "phone_number": "966501234567"
}
```

---

### Example 2: Python

```python
import requests

# API Configuration
API_URL = "https://nevoxai.com/api/v1/calls/outbound"
API_KEY = "nvx_abc123def456789012345678901234"

# Call data
payload = {
    "agent_id": 12,
    "phone_number": "+966501234567",
    "context": {
        "customer_name": "Ahmed Al-Saud",
        "order_id": "ORD-789",
        "delivery_status": "shipped"
    }
}

# Make request
response = requests.post(
    API_URL,
    headers={"X-API-Key": API_KEY},
    json=payload
)

# Handle response
if response.status_code == 200:
    data = response.json()
    print(f"✅ Call initiated: {data['call_id']}")
    print(f"   Room: {data['room_name']}")
else:
    print(f"❌ Error: {response.json()['error']}")
```

---

### Example 3: Node.js

```javascript
const axios = require('axios');

const API_URL = 'https://nevoxai.com/api/v1/calls/outbound';
const API_KEY = 'nvx_abc123def456789012345678901234';

async function makeCall() {
  try {
    const response = await axios.post(API_URL, {
      agent_id: 12,
      phone_number: '+966501234567',
      context: {
        customer_name: 'Ahmed Al-Saud',
        order_id: 'ORD-789'
      }
    }, {
      headers: {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json'
      }
    });

    console.log('✅ Call initiated:', response.data.call_id);
    console.log('   Room:', response.data.room_name);
  } catch (error) {
    console.error('❌ Error:', error.response.data.error);
  }
}

makeCall();
```

---

### Example 4: PHP

```php
<?php
$api_url = 'https://nevoxai.com/api/v1/calls/outbound';
$api_key = 'nvx_abc123def456789012345678901234';

$data = [
    'agent_id' => 12,
    'phone_number' => '+966501234567',
    'context' => [
        'customer_name' => 'Ahmed Al-Saud',
        'order_id' => 'ORD-789'
    ]
];

$ch = curl_init($api_url);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Content-Type: application/json',
    'X-API-Key: ' . $api_key
]);

$response = curl_exec($ch);
$result = json_decode($response, true);

if ($result['success']) {
    echo "✅ Call initiated: " . $result['call_id'] . "\n";
} else {
    echo "❌ Error: " . $result['error'] . "\n";
}

curl_close($ch);
?>
```

---

### Example 5: List Agents

```bash
curl -X GET https://nevoxai.com/api/v1/agents \
  -H "X-API-Key: nvx_abc123def456789012345678901234"
```

**Response:**
```json
{
  "success": true,
  "agents": [
    {
      "id": 12,
      "name": "Sales Agent",
      "voice_name": "Fatima",
      "created_at": "2026-02-10T09:00:00"
    },
    {
      "id": 15,
      "name": "Support Agent",
      "voice_name": "Ahmed",
      "created_at": "2026-02-11T14:30:00"
    }
  ]
}
```

---

## 11. Line-by-Line Code Explanations

### models.py - ApiKey Model

```python
# Line 233-234
class ApiKey(db.Model):
    """API Keys for external integrations"""
```
**Explanation:** Defines the ApiKey SQLAlchemy model class that maps to the `api_key` database table.

---

```python
# Line 238
__tablename__ = 'api_key'
```
**Explanation:** Explicitly sets the table name to `api_key` (without this, SQLAlchemy would use `api_key` anyway, but explicit is better).

---

```python
# Line 240
id = db.Column(db.Integer, primary_key=True)
```
**Explanation:**
- Primary key column
- Auto-increments
- Unique identifier for each API key record

---

```python
# Line 241-242
user_id = db.Column(db.Integer, db.ForeignKey('user.id'),
                   nullable=False, unique=True)
```
**Explanation:**
- Foreign key to `user` table
- `nullable=False` → User ID is required
- `unique=True` → **ONE KEY PER USER** (database enforces this)
- Links to `user.id` column

---

```python
# Line 244
key_hash = db.Column(db.String(64), unique=True, nullable=False)
```
**Explanation:**
- Stores SHA-256 hash of API key (64 hex characters)
- `unique=True` → No duplicate keys
- `nullable=False` → Hash is required
- **Never stores the raw key**

---

```python
# Line 245
key_prefix = db.Column(db.String(12), nullable=False)
```
**Explanation:**
- Stores first 12 characters for display (e.g., "nvx_a1b2c3...")
- Used in UI to identify keys
- Safe to show (doesn't reveal full key)

---

```python
# Line 247
name = db.Column(db.String(100), default='Default API Key')
```
**Explanation:**
- User-defined name for the key
- Default value if not provided
- Helps users identify keys in UI

---

```python
# Line 248
is_active = db.Column(db.Boolean, default=True)
```
**Explanation:**
- Key status (active or revoked)
- Default: `True` (active when created)
- Used in authentication check

---

```python
# Line 251
last_used_at = db.Column(db.DateTime, nullable=True)
```
**Explanation:**
- Timestamp of last API call using this key
- `nullable=True` → NULL if never used
- Updated automatically during validation

---

```python
# Line 252
total_calls = db.Column(db.Integer, default=0)
```
**Explanation:**
- Counter for total API calls made
- Starts at 0
- Incremented on each successful authentication

---

```python
# Line 254
created_at = db.Column(db.DateTime,
    default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
```
**Explanation:**
- Key creation timestamp
- Uses Saudi Arabia timezone (UTC+3)
- `replace(tzinfo=None)` → Stores as naive datetime (for compatibility)
- Set automatically on creation

---

```python
# Line 255
revoked_at = db.Column(db.DateTime, nullable=True)
```
**Explanation:**
- Timestamp when key was revoked
- `nullable=True` → NULL if still active
- Used for audit trail

---

```python
# Line 258
user = db.relationship('User', backref=db.backref('api_key', uselist=False))
```
**Explanation:**
- Creates relationship to User model
- `user` → Access user from ApiKey: `api_key.user`
- `backref='api_key'` → Access key from User: `user.api_key`
- `uselist=False` → One-to-one relationship (returns single object, not list)

---

### services/api_key_service.py

```python
# Line 22-23
PREFIX = "nvx_"
KEY_LENGTH = 32
```
**Explanation:**
- Class constants
- `PREFIX` → All keys start with "nvx_"
- `KEY_LENGTH` → 32 hex characters after prefix
- Total key length: 36 characters ("nvx_" + 32 chars)

---

```python
# Line 36
random_part = secrets.token_hex(self.KEY_LENGTH // 2)
```
**Explanation:**
- `secrets.token_hex(16)` → Generates 16 random bytes
- Converts to 32 hexadecimal characters
- Why `// 2`? Each byte = 2 hex chars
- Cryptographically secure randomness

---

```python
# Line 37
raw_key = f"{self.PREFIX}{random_part}"
```
**Explanation:**
- Concatenates prefix + random part
- Example: "nvx_" + "a1b2c3..." = "nvx_a1b2c3..."
- This is the full key (shown to user ONCE)

---

```python
# Line 40
key_hash = self._hash_key(raw_key)
```
**Explanation:**
- Calls `_hash_key()` method to generate SHA-256 hash
- This hash is stored in database
- Original key is NOT stored

---

```python
# Line 43
key_prefix = raw_key[:12] + "..."
```
**Explanation:**
- Takes first 12 characters
- Adds "..." to indicate truncation
- Example: "nvx_a1b2c3d4..."
- Safe to display in UI

---

```python
# Line 59
return hashlib.sha256(raw_key.encode()).hexdigest()
```
**Explanation:**
- `.encode()` → Converts string to bytes
- `sha256()` → Generates SHA-256 hash
- `.hexdigest()` → Returns hash as 64-character hex string
- One-way function (cannot reverse)

---

```python
# Line 76-78
if not raw_key.startswith(self.PREFIX):
    logger.warning(f"API key validation failed: Invalid prefix")
    return None
```
**Explanation:**
- **Fast rejection** of invalid keys
- Checks if key starts with "nvx_"
- No database query needed
- Prevents brute force attempts

---

```python
# Line 86-89
api_key = ApiKey.query.filter_by(
    key_hash=key_hash,
    is_active=True
).first()
```
**Explanation:**
- Queries database for matching hash
- `filter_by(key_hash=key_hash)` → Find key with matching hash
- `is_active=True` → Only active keys
- `.first()` → Returns first match or None

---

```python
# Line 96-97
api_key.last_used_at = datetime.utcnow()
api_key.total_calls += 1
```
**Explanation:**
- **Automatic usage tracking**
- Updates timestamp to current time
- Increments call counter
- Committed to database immediately

---

```python
# Line 122
existing_key = ApiKey.query.filter_by(user_id=user_id).first()
```
**Explanation:**
- Checks if user already has a key
- Returns key object or None
- Used to implement "one key per user" policy

---

```python
# Line 124-128
if existing_key:
    existing_key.is_active = False
    existing_key.revoked_at = datetime.utcnow()
    logger.info(f"Revoked existing API key for user_id={user_id}")
```
**Explanation:**
- If key exists, revoke it first
- Sets `is_active` to False
- Records revocation timestamp
- **Key is not deleted** (audit trail preserved)

---

```python
# Line 131
raw_key, key_hash, key_prefix = self.generate_key()
```
**Explanation:**
- Generates new key
- Returns tuple of (raw_key, hash, prefix)
- Uses unpacking to assign to separate variables

---

```python
# Line 134-140
new_key = ApiKey(
    user_id=user_id,
    key_hash=key_hash,
    key_prefix=key_prefix,
    name=name,
    is_active=True
)
```
**Explanation:**
- Creates new ApiKey object
- Sets all required fields
- `is_active=True` → New key is active by default
- Does NOT set `created_at` (set by database default)

---

```python
# Line 143-144
db.session.add(new_key)
db.session.commit()
```
**Explanation:**
- `add()` → Adds object to session (prepares for save)
- `commit()` → Saves to database
- Two-phase commit pattern

---

```python
# Line 212
api_key_service = ApiKeyService()
```
**Explanation:**
- **Singleton pattern**
- Create single instance
- Imported and used throughout application
- Stateless service (no instance variables)

---

### routes/api_v1.py - Authentication Decorator

```python
# Line 28-29
def require_api_key(f):
    @wraps(f)
```
**Explanation:**
- `@wraps(f)` → Preserves original function metadata
- Without it, Flask would lose function name/docstring
- Important for routing and debugging

---

```python
# Line 39
api_key = request.headers.get('X-API-Key')
```
**Explanation:**
- Extracts API key from HTTP request header
- Header name: `X-API-Key`
- Returns None if header doesn't exist

---

```python
# Line 42-47
if not api_key:
    logger.warning(f"API request without key from IP: {request.remote_addr}")
    return jsonify({
        'success': False,
        'error': 'API key required',
        'code': 'MISSING_API_KEY'
    }), 401
```
**Explanation:**
- Check if header exists
- Log attempt with IP address (security monitoring)
- Return 401 Unauthorized
- Include error code for programmatic handling

---

```python
# Line 49
user = api_key_service.validate_key(api_key)
```
**Explanation:**
- Calls service layer to validate key
- Returns User object if valid, None if invalid
- Handles hashing and database query

---

```python
# Line 60-65
if not user.is_approved:
    return jsonify({
        'success': False,
        'error': 'Account not approved',
        'code': 'ACCOUNT_NOT_APPROVED'
    }), 403
```
**Explanation:**
- **Additional security check**
- Even with valid key, user must be approved
- Returns 403 Forbidden (different from 401)
- Prevents unapproved users from using API

---

```python
# Line 70-78 (Rate Limiting)
allowed, remaining, limit, reset_seconds = api_rate_limiter.check_and_increment(user.id)

g.rate_limit = limit
g.rate_limit_remaining = remaining
g.rate_limit_reset = reset_seconds

if not allowed:
    # Return 429 Too Many Requests
```
**Explanation:**
- **Per-user rate limiting** via Redis
- `check_and_increment()` atomically checks count and increments
- Stores rate limit info in Flask `g` for response headers
- If exceeded → returns 429 with `Retry-After` header
- Redis key: `api_rate:{user_id}` with 3600s TTL

---

```python
# Line 93
g.current_user = user
```
**Explanation:**
- Stores user in Flask's `g` object
- `g` → Request-scoped storage
- Available throughout request lifecycle
- Accessed in route: `user = g.current_user`

---

```python
# Line 94
return f(*args, **kwargs)
```
**Explanation:**
- Executes the decorated function
- Passes all arguments through
- Authentication + rate limit check succeeded, run actual route handler

---

```python
# Line 98-109 (Response Header Middleware)
@api_v1_bp.after_request
def add_rate_limit_headers(response):
    if hasattr(g, 'rate_limit'):
        response.headers['X-RateLimit-Limit'] = str(g.rate_limit)
        response.headers['X-RateLimit-Remaining'] = str(g.rate_limit_remaining)
        response.headers['X-RateLimit-Reset'] = str(g.rate_limit_reset)
    response.headers['X-API-Version'] = '1.0'
    return response
```
**Explanation:**
- Runs **after every API v1 response** (success or error)
- Adds standard `X-RateLimit-*` headers so clients can track usage
- Also adds `X-API-Version` for version discovery
- Only adds rate limit headers if authentication was processed (via `hasattr` check)

---

### routes/api_v1.py - Outbound Call Endpoint

```python
# Line 143-145
@api_v1_bp.route('/calls/outbound', methods=['POST'])
@require_api_key
def create_outbound_call():
```
**Explanation:**
- Route decorator: `/api/v1/calls/outbound`
- Only accepts POST requests
- `@require_api_key` → Authentication required
- Decorator runs BEFORE function

---

```python
# Line 172
user = g.current_user
```
**Explanation:**
- Retrieves authenticated user from Flask context
- Set by `@require_api_key` decorator
- Guaranteed to exist (decorator would return 401 if not)

---

```python
# Line 175
data = request.get_json()
```
**Explanation:**
- Parses JSON request body
- Returns Python dict
- Returns None if invalid JSON

---

```python
# Line 185-186
agent_id = data.get('agent_id')
phone_number = data.get('phone_number')
```
**Explanation:**
- Extracts required fields from request
- `.get()` → Returns None if key doesn't exist
- Safer than `data['agent_id']` (won't raise KeyError)

---

```python
# Line 203
agent = Agent.query.filter_by(id=agent_id, user_id=user.id).first()
```
**Explanation:**
- **Authorization check**
- Verifies agent exists AND belongs to authenticated user
- Prevents user from calling agents they don't own
- Returns None if not found

---

```python
# Line 213-218
if user.minutes_balance <= 0:
    return jsonify({
        'success': False,
        'error': 'Insufficient minutes balance',
        'code': 'INSUFFICIENT_MINUTES'
    }), 402
```
**Explanation:**
- Checks if user has calling credit
- Returns **402 Payment Required** (appropriate HTTP code)
- Prevents calls when no minutes available

---

```python
# Line 221
formatted_number = format_phone_number(phone_number)
```
**Explanation:**
- Normalizes phone number format
- Removes spaces, dashes, parentheses
- Adds country code if missing
- Example: "+966 50 123 4567" → "966501234567"

---

```python
# Line 224
outbound_trunk_id = user.outbound_trunk_id or os.environ.get('SIP_OUTBOUND_TRUNK_ID')
```
**Explanation:**
- Gets SIP trunk ID for making calls
- **Fallback pattern**: User's trunk OR system default
- `or` → Uses first truthy value
- Required for LiveKit SIP calling

---

```python
# Line 239-240
timestamp = datetime.now(SAUDI_TZ).timestamp()
room_name = f"call-{agent_id}-api-{user.username}-{int(timestamp)}"
```
**Explanation:**
- Generates unique room name
- Format: `call-12-api-john-1707654321`
- Includes:
  - `agent_id` → Which agent
  - `api` → Called via API
  - `username` → Which user
  - `timestamp` → Uniqueness

---

```python
# Line 245-252
asyncio.run(make_livekit_call(
    phone_number=formatted_number,
    room_name=room_name,
    agent_name=agent.name,
    outbound_trunk_id=outbound_trunk_id,
    agent_id=agent_id,
    webhook_context=context if context else None
))
```
**Explanation:**
- Initiates LiveKit call asynchronously
- `asyncio.run()` → Run async function in sync context
- Creates LiveKit room and SIP participant
- Agent auto-joins room when created

---

```python
# Line 255-263
call_log = CallLog(
    user_id=user.id,
    agent_id=agent_id,
    from_number=user.outbound_phone_number or os.environ.get('SAUDI_PHONE_NUMBER', 'API'),
    to_number=formatted_number,
    room_name=room_name,
    status='initiated',
    call_type='outbound'
)
```
**Explanation:**
- Creates call log record
- Tracks all call metadata
- `status='initiated'` → Call started (not completed)
- `call_type='outbound'` → Outbound call (vs inbound)

---

```python
# Line 265-266
db.session.add(call_log)
db.session.commit()
```
**Explanation:**
- Saves call log to database
- Immediate commit (don't wait)
- Call is tracked even if agent fails later

---

```python
# Line 270-277
return jsonify({
    'success': True,
    'call_id': call_log.id,
    'room_name': room_name,
    'status': 'initiated',
    'agent_id': agent_id,
    'phone_number': formatted_number
}), 200
```
**Explanation:**
- Returns success response
- HTTP 200 OK
- Includes call details for client tracking
- Client can poll `/calls/{call_id}` for status updates

---

```python
# Line 280-287
except Exception as e:
    logger.error(f"Error initiating API call: {e}", exc_info=True)
    db.session.rollback()
    return jsonify({
        'success': False,
        'error': 'Failed to initiate call',
        'code': 'CALL_FAILED',
        'details': str(e)
    }), 500
```
**Explanation:**
- Catch-all error handler
- `exc_info=True` → Logs full stack trace
- `db.session.rollback()` → Undo partial changes
- Returns 500 Internal Server Error
- Includes error details for debugging

---

### UI Route - API Keys Page

```python
# Line 340-342
@api_v1_bp.route('/settings/api-keys', methods=['GET'])
@login_required
@approved_required
```
**Explanation:**
- Different authentication (session-based, not API key)
- `@login_required` → User must be logged in
- `@approved_required` → User must be approved
- Web UI route, not API endpoint

---

```python
# Line 347
user_id = session['user_id']
```
**Explanation:**
- Gets user ID from session cookie
- Flask session (encrypted)
- Set during login

---

```python
# Line 348
api_key_info = api_key_service.get_key_info(user_id)
```
**Explanation:**
- Fetches key information for display
- Returns dict with key details
- Returns None if no key exists

---

```python
# Line 351
new_key = session.pop('new_api_key', None)
```
**Explanation:**
- **One-time display pattern**
- `.pop()` → Gets value AND removes from session
- Only exists after key generation
- Shown in modal, then deleted

---

```python
# Line 353-355
return render_template('settings/api_keys.html',
                     api_key_info=api_key_info,
                     new_key=new_key)
```
**Explanation:**
- Renders HTML template
- Passes variables to template
- Template uses Jinja2 syntax: `{{ api_key_info.name }}`

---

### UI Route - Generate Key

```python
# Line 358-360
@api_v1_bp.route('/settings/api-keys/generate', methods=['POST'])
@login_required
@approved_required
```
**Explanation:**
- POST endpoint (form submission)
- Session authentication (not API key)
- Only approved users can generate keys

---

```python
# Line 367
raw_key = api_key_service.create_key_for_user(user_id)
```
**Explanation:**
- Generates new API key
- Returns raw key (full key, shown once)
- Service handles revocation of old key

---

```python
# Line 371
session['new_api_key'] = raw_key
```
**Explanation:**
- **Temporary storage** in session
- Displayed once in modal
- Removed after display (via `.pop()`)
- Never stored permanently

---

```python
# Line 372
flash('API key generated successfully!', 'success')
```
**Explanation:**
- Flask flash message
- Shows success notification in UI
- `'success'` → Message category (for styling)

---

```python
# Line 376
return redirect(url_for('api_v1.api_keys_page'))
```
**Explanation:**
- **Post-Redirect-Get pattern**
- Redirects back to settings page
- Prevents form resubmission on refresh
- `url_for()` → Generates URL from route name

---

## Summary

### Key Takeaways

1. **Security First**
   - Keys hashed with SHA-256 (never stored plain text)
   - Cryptographically secure key generation
   - One key per user (enforced by database)
   - Audit trail (keys never deleted, only revoked)
   - Redis-backed per-user rate limiting (200 calls/hour)

2. **Clean Architecture**
   - Service layer separates business logic
   - Decorator pattern for authentication + rate limiting
   - Repository pattern with SQLAlchemy
   - Middleware for response headers (`X-RateLimit-*`, `X-API-Version`)

3. **User Experience**
   - One-time key display with modal
   - Copy-to-clipboard functionality
   - Usage statistics and tracking
   - Live code examples in UI

4. **API Design**
   - RESTful endpoints
   - Consistent error codes
   - JSON request/response
   - Standard HTTP status codes

5. **Migration Support**
   - SQLite (development)
   - PostgreSQL (production)
   - Safe to run multiple times
   - Detailed output and verification

---

## Appendix: Error Codes Reference

| Code | HTTP | Meaning | Action |
|------|------|---------|--------|
| `MISSING_API_KEY` | 401 | No X-API-Key header | Add header to request |
| `INVALID_API_KEY` | 401 | Key not found/revoked | Check key, regenerate if needed |
| `ACCOUNT_NOT_APPROVED` | 403 | User not approved | Wait for admin approval |
| `MISSING_BODY` | 400 | No JSON body | Add JSON body to request |
| `MISSING_AGENT_ID` | 400 | agent_id not in body | Add agent_id field |
| `MISSING_PHONE_NUMBER` | 400 | phone_number not in body | Add phone_number field |
| `AGENT_NOT_FOUND` | 404 | Agent doesn't exist | Check agent ID, verify ownership |
| `INSUFFICIENT_MINUTES` | 402 | No calling credit | Add minutes to account |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests | Wait `retry_after_seconds` then retry |
| `NO_TRUNK_CONFIGURED` | 500 | No SIP trunk | Contact administrator |
| `CALL_FAILED` | 500 | LiveKit error | Check logs, retry |

---

## Appendix: Database Indexes

```sql
-- User lookup (most common query)
CREATE INDEX idx_api_key_user_id ON api_key(user_id);

-- Key validation (authentication)
CREATE INDEX idx_api_key_hash ON api_key(key_hash);

-- Active keys filter
CREATE INDEX idx_api_key_active ON api_key(is_active);
```

**Query Performance:**
- User lookup: O(log n) with B-tree index
- Key validation: O(log n) with B-tree index
- Combined query: Uses composite index scan

---

## Appendix: Testing Checklist

### Unit Tests
- [ ] Key generation produces 36-character keys
- [ ] Keys start with "nvx_" prefix
- [ ] SHA-256 hashing is consistent
- [ ] Invalid keys are rejected
- [ ] Revoked keys cannot be used
- [ ] Usage stats are updated

### Integration Tests
- [ ] Create key for new user
- [ ] Create key for existing user (revokes old)
- [ ] Authenticate with valid key
- [ ] Authenticate with invalid key
- [ ] Authenticate with revoked key
- [ ] Make API call with authentication
- [ ] Handle insufficient minutes

### UI Tests
- [ ] Display key information
- [ ] Show "no key" state
- [ ] Generate new key (modal appears)
- [ ] Copy key to clipboard
- [ ] Regenerate key (confirms first)
- [ ] Revoke key (confirms first)

---

**End of Documentation**

Generated: February 13, 2026
System: NevoxAI Voice Agent Platform
Version: 1.1
