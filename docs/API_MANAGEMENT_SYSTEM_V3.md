
API Management System - Implementation Plan (V2)
NOTE

For High-Scale Production (1000s of calls/hour) See 
API_MANAGEMENT_SYSTEM_V3.md
 for production-grade architecture with Celery, PostgreSQL, and circuit breakers.

Goal
Enable external systems (n8n, custom applications) to trigger outbound calls programmatically through a secure REST API. Support both single calls and campaign calls with proper authentication, rate limiting, and context injection.

This plan (V2) is optimized for:

Quick implementation (1-2 weeks)
Up to 1,000 calls/hour
10-20 concurrent calls
MVP and initial production use
Current System Analysis
Existing Call Infrastructure
Single Calls (
agents.py:341-444
):

Route: /agents/<agent_id>/make-call (POST)
Uses 
make_livekit_call()
 function
Supports pre-call webhook for context fetching
Creates 
CallLog
 records
Requires user login (@login_required)
Campaign Calls (
campaign_worker.py:280-414
):

Background worker processes campaigns
Uses LiveKit SIP API directly
Supports pre-call webhooks
Tracks contacts in 
CampaignContact
 table
Passes context via room_metadata
Key Insight
Both call types use the same pattern:

Build room_metadata with context
Call LiveKit SIP API with metadata
Context is passed to AI agent via participant_metadata
We can reuse this pattern for API calls!

Proposed Architecture
API Call Flow
External System (n8n)
    │
    │ POST /api/v1/call/initiate
    │ Headers: X-API-Key: nvx_sk_...
    │ Body: { agent_id, phone, context }
    │
    ▼
┌─────────────────────────────┐
│  1. Validate API Key        │ → User.query.filter_by(api_key=...)
│  2. Check Rate Limit        │ → Redis: api_rate:{user_id}
│  3. Verify Agent Ownership  │ → Agent.query.filter_by(id, user_id)
│  4. Check Minutes Balance   │ → user.minutes_balance > 0
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│  5. Create CallLog          │
│  6. Build webhook_context   │ → { source: "api", context: {...} }
│  7. Call make_livekit_call()│ → REUSE EXISTING FUNCTION
└─────────────────────────────┘
    │
    ▼
Return: { success: true, call_id: 123 }
Campaign API Flow
External System
    │
    │ POST /api/v1/campaign/initiate
    │ Body: { campaign_id, contacts: [...] }
    │
    ▼
┌─────────────────────────────┐
│  1. Validate API Key        │
│  2. Verify Campaign Access  │
│  3. Add Contacts to DB      │
│  4. Start Campaign          │ → campaign.status = 'running'
└─────────────────────────────┘
    │
    ▼
Campaign Worker picks up and processes
Implementation Details
1. Database Changes
Add to User model (
models.py
):

# API Management
api_key = db.Column(db.String(64), unique=True, nullable=True, index=True)
api_key_created_at = db.Column(db.DateTime, nullable=True)
api_rate_limit = db.Column(db.Integer, default=100)  # calls per hour
Migration: migrations/add_api_key_to_user.py

2. Services Layer
Rate Limiter Service
File: services/api_rate_limiter.py

Redis-based (works with multiple workers)
Per-user rate limiting
Configurable limits per user
class APIRateLimiter:
    def is_allowed(user_id, limit=100) -> (bool, remaining)
    def get_usage(user_id) -> dict
    def reset(user_id) -> bool
3. API Routes
File: routes/external_api.py

Authentication Decorator
@require_api_key
def endpoint():
    # request.api_user = User object
    # request.rate_limit_remaining = int
Endpoints
Endpoint	Method	Purpose
/api/v1/call/initiate	POST	Trigger single call
/api/v1/call/<id>/status	GET	Get call status
/api/v1/call/<id>/transcript	GET	Get transcript
/api/v1/campaign/initiate	POST	Start campaign with contacts
/api/v1/campaign/<id>/status	GET	Get campaign progress
4. Single Call Implementation
Endpoint: POST /api/v1/call/initiate

Request:

{
  "agent_id": 5,
  "phone": "+966512345678",
  "call_type": "noshow_recovery",
  "context": {
    "patient_name": "Ahmed",
    "appointment_date": "2026-01-29",
    "doctor_name": "Dr. Fatima"
  }
}
Implementation Strategy:

✅ Reuse 
make_livekit_call()
 from 
agents.py:447
✅ Use ThreadPoolExecutor for non-blocking execution
✅ Pass context via webhook_context parameter (already supported!)
Response:

{
  "success": true,
  "call_id": 1234,
  "room_name": "api-call-5-1706621234",
  "status": "initiated",
  "rate_limit_remaining": 95
}
5. Campaign Call Implementation
Endpoint: POST /api/v1/campaign/initiate

Request:

{
  "campaign_id": 10,
  "contacts": [
    {
      "phone": "+966512345678",
      "name": "Ahmed",
      "custom_data": {
        "appointment_id": "12345",
        "clinic": "Main Branch"
      }
    }
  ]
}
Implementation:

Add contacts to 
CampaignContact
 table
Set campaign status to 
running
Campaign worker automatically picks up and processes
Alternative - Direct Campaign Trigger:

{
  "agent_id": 5,
  "campaign_name": "No-Show Recovery - Jan 2026",
  "contacts": [...],
  "call_window_start": "09:00",
  "call_window_end": "18:00",
  "concurrent_calls": 3
}
This creates a new campaign and starts it immediately.

6. API Key Management UI
Route: /settings/api

Template: templates/settings/api_keys.html

Features:

Generate new API key (shown once)
View masked key (nvx_sk_abc...xyz)
Regenerate key (revokes old)
View usage stats
Configure rate limit
File Structure
nevoxai-project/
├── models.py                          # ADD: api_key fields to User
├── services/
│   └── api_rate_limiter.py           # NEW: Redis rate limiting
├── routes/
│   ├── agents.py                      # NO CHANGES (reuse make_livekit_call)
│   ├── external_api.py               # NEW: API endpoints
│   └── api_settings.py               # NEW: API key management UI
├── templates/
│   └── settings/
│       └── api_keys.html             # NEW: API management page
└── migrations/
    └── add_api_key_to_user.py        # NEW: Database migration
Key Design Decisions
✅ Reuse vs Rebuild
Approach	Decision
Reuse 
make_livekit_call()
✅ YES - Already supports webhook_context
Reuse campaign worker	✅ YES - Just add contacts via API
Create new CallService	❌ NO - Unnecessary abstraction
✅ Threading Strategy
Use ThreadPoolExecutor for API calls:

Flask responds immediately (< 100ms)
Call executes in background
No blocking on LiveKit API
call_executor = ThreadPoolExecutor(max_workers=20)
# Submit to background
call_executor.submit(
    _execute_call,
    phone, room_name, agent_name, trunk_id, agent_id, context
)
# Return immediately
return jsonify({'success': True, 'call_id': call_log.id})
✅ Context Injection
Unified approach for all call sources:

webhook_context = {
    "source": "api",           # or "ui", "campaign"
    "call_type": call_type,    # "noshow_recovery", etc.
    "initiated_at": datetime.now().isoformat(),
    **context                  # User-provided context
}
# Pass to make_livekit_call()
await make_livekit_call(
    phone, room_name, agent_name, trunk_id, agent_id,
    webhook_context=webhook_context  # ✅ Already supported!
)
User Review Required
IMPORTANT

API Key Security

API keys will be stored in plaintext in database (for validation)
Keys are shown only once during generation
Users should store keys securely (environment variables, secrets manager)
Consider adding IP whitelisting for production
IMPORTANT

Rate Limiting

Default: 100 calls per hour per user
Configurable per user by admin
Uses Redis (requires Redis running)
Falls back to "allow all" if Redis unavailable
WARNING

Campaign API Behavior

Adding contacts to existing campaign: Contacts are processed based on campaign's call window
Creating new campaign via API: Starts immediately if within call window
Campaign worker must be running (python services/campaign_worker.py)
Proposed Changes
Database
[MODIFY] 
models.py
Add API key fields to 
User
 class (lines 14-37):

# API Management
api_key = db.Column(db.String(64), unique=True, nullable=True, index=True)
api_key_created_at = db.Column(db.DateTime, nullable=True)
api_rate_limit = db.Column(db.Integer, default=100)
Services
[NEW] 
api_rate_limiter.py
Redis-based rate limiter:

is_allowed(user_id, limit) - Check and increment
get_usage(user_id) - Get current usage
reset(user_id) - Admin reset function
Routes
[NEW] 
external_api.py
External API endpoints:

POST /api/v1/call/initiate - Single call
GET /api/v1/call/<id>/status - Call status
GET /api/v1/call/<id>/transcript - Transcript
POST /api/v1/campaign/initiate - Campaign with contacts
GET /api/v1/campaign/<id>/status - Campaign progress
Uses ThreadPoolExecutor for non-blocking call execution.

[NEW] 
api_settings.py
API key management UI:

GET /settings/api - View API settings
POST /settings/api/generate - Generate new key
POST /settings/api/regenerate - Regenerate key
POST /settings/api/revoke - Revoke key
Templates
[NEW] 
api_keys.html
User interface for:

Viewing masked API key
Generating/regenerating keys
Viewing usage statistics
API documentation links
Migrations
[NEW] 
add_api_key_to_user.py
Database migration to add:

api_key column (VARCHAR(64), UNIQUE)
api_key_created_at column (DATETIME)
api_rate_limit column (INTEGER, DEFAULT 100)
Index on api_key for fast lookups
Verification Plan
Automated Tests
Database Migration

python migrations/add_api_key_to_user.py
API Key Generation

Generate key via UI
Verify key format: nvx_sk_[32 hex chars]
Verify stored in database
Single Call API

curl -X POST http://localhost:5000/api/v1/call/initiate \
  -H "X-API-Key: nvx_sk_..." \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "phone": "+966512345678",
    "context": {"patient_name": "Test"}
  }'
Rate Limiting

Make 101 requests rapidly
Verify 101st returns 429 error
Campaign API

curl -X POST http://localhost:5000/api/v1/campaign/initiate \
  -H "X-API-Key: nvx_sk_..." \
  -d '{
    "campaign_id": 1,
    "contacts": [{"phone": "+966512345678", "name": "Test"}]
  }'
Manual Verification
n8n Integration

Create n8n workflow
Configure HTTP Request node with API key
Trigger call from n8n
Verify call is made and context is passed to agent
Context Verification

Make API call with custom context
Check agent receives context in room_metadata
Verify agent can access context during call
UI Testing

Navigate to /settings/api
Generate API key
Copy key (shown once)
Verify masked key displayed after refresh
Next Steps
Review this plan - Confirm approach aligns with your needs
Clarify requirements:
Do you need both single call AND campaign APIs?
Any specific context fields required?
Rate limit preferences?
Begin implementation - Start with database migration

Comment
Ctrl+Alt+M
