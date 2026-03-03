# FastAPI Migration Analysis

## Executive Summary

**Current Setup:** Flask-based application with 7 blueprints, 42+ routes, session-based authentication, and Jinja2 templates.

**Migration Complexity:** 🟡 **MEDIUM-HIGH** (3-4 weeks of work)

**Recommendation:** ⚠️ **DO NOT migrate the entire app to FastAPI**

Instead: **Hybrid Approach** - Keep Flask for UI, add FastAPI for API endpoints only.

---

## Current Architecture Analysis

### Application Structure

```
nevoxai-project/
├── app.py                    # Flask app initialization
├── models.py                 # SQLAlchemy models
├── routes/                   # 7 Flask blueprints
│   ├── core.py              # 42 routes (auth, admin, tools, webhooks)
│   ├── agents.py            # Agent management + make_call
│   ├── campaigns.py         # Campaign management
│   ├── inbound.py           # Inbound call handling
│   ├── workflows.py         # Workflow management
│   ├── public_api.py        # Public API endpoints
│   └── test_agent.py        # Browser-based testing
├── services/                 # 13 service files
│   ├── campaign_worker.py   # Background campaign processor
│   ├── redis_service.py     # Redis operations
│   ├── webhook_service.py   # Webhook handling
│   ├── tool_service.py      # Tool execution
│   └── ...
└── templates/                # 50+ Jinja2 HTML templates
    ├── base.html
    ├── auth/
    ├── agents/
    ├── campaigns/
    └── ...
```

### Key Dependencies on Flask

| Component | Flask Feature | Usage Count | Migration Difficulty |
|-----------|---------------|-------------|---------------------|
| **Authentication** | `session['user_id']` | 40+ routes | 🔴 **HIGH** |
| **Templates** | `render_template()` | 35+ routes | 🔴 **HIGH** |
| **Decorators** | `@login_required` | 30+ routes | 🟡 **MEDIUM** |
| **Forms** | `request.form` | 25+ routes | 🟢 **LOW** |
| **File Uploads** | `request.files` | 5+ routes | 🟢 **LOW** |
| **Blueprints** | Flask Blueprints | 7 blueprints | 🟡 **MEDIUM** |
| **Error Handlers** | `@app.errorhandler` | 3 handlers | 🟢 **LOW** |
| **Security Headers** | `@app.after_request` | 1 middleware | 🟢 **LOW** |

---

## What Would Need to Change

### 1. Authentication System (🔴 **MAJOR CHANGE**)

#### Current (Flask)
```python
# routes/core.py
from flask import session

@core_bp.route('/login', methods=['POST'])
def login():
    # Validate credentials
    session['user_id'] = user.id
    session.permanent = True
    return redirect('/dashboard')

@core_bp.route('/dashboard')
@login_required
def dashboard():
    user_id = session.get('user_id')
    # ...
```

#### FastAPI Equivalent
```python
# Would need JWT tokens or OAuth2
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.post('/login')
async def login(credentials: LoginRequest):
    # Validate
    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer"}

@app.get('/dashboard')
async def dashboard(token: str = Depends(oauth2_scheme)):
    user_id = decode_token(token)
    # ...
```

**Problems:**
- ❌ No built-in session management
- ❌ Need to implement JWT/OAuth2 from scratch
- ❌ Frontend needs to handle tokens (localStorage/cookies)
- ❌ All 40+ routes need token validation

---

### 2. Template Rendering (🔴 **MAJOR CHANGE**)

#### Current (Flask)
```python
@core_bp.route('/dashboard')
@login_required
def dashboard():
    agents = Agent.query.filter_by(user_id=current_user.id).all()
    return render_template('index.html', 
                         agents=agents,
                         current_year=datetime.now().year)
```

#### FastAPI Equivalent
```python
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

templates = Jinja2Templates(directory="templates")

@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(get_current_user)):
    agents = await Agent.filter(user_id=user.id).all()
    return templates.TemplateResponse('index.html', {
        'request': request,  # REQUIRED!
        'agents': agents,
        'current_year': datetime.now().year
    })
```

**Problems:**
- ❌ Must pass `request` to every template (Flask doesn't require this)
- ❌ All 35+ `render_template()` calls need updating
- ❌ Template context needs restructuring

---

### 3. Database Operations (🟡 **MEDIUM CHANGE**)

#### Current (Flask + SQLAlchemy)
```python
# Synchronous
user = User.query.filter_by(id=user_id).first()
db.session.add(call_log)
db.session.commit()
```

#### FastAPI Options

**Option A: Keep Sync (easier)**
```python
# Still works, but not ideal
from sqlalchemy.orm import Session

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get('/users/{user_id}')
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    return user
```

**Option B: Async (better performance)**
```python
# Requires async SQLAlchemy
from sqlalchemy.ext.asyncio import AsyncSession

@app.get('/users/{user_id}')
async def get_user(user_id: int, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    return user
```

**Impact:**
- 🟡 100+ database queries across all routes
- 🟡 If going async: Need to rewrite every query
- 🟡 If staying sync: Less benefit from FastAPI

---

### 4. Services Layer (🟢 **MINIMAL CHANGE**)

**Good News:** Your services are mostly independent!

```python
# services/campaign_worker.py - NO CHANGES NEEDED
# services/redis_service.py - NO CHANGES NEEDED
# services/webhook_service.py - NO CHANGES NEEDED
# services/tool_service.py - NO CHANGES NEEDED
```

These can work with both Flask and FastAPI! ✅

---

### 5. Routes Breakdown

#### Routes That MUST Stay in Flask (UI Routes)

| Blueprint | Routes | Reason |
|-----------|--------|--------|
| `core.py` | 30+ routes | Session auth, templates, forms |
| `agents.py` | 15+ routes | Agent CRUD UI, templates |
| `campaigns.py` | 10+ routes | Campaign UI, file uploads |
| `inbound.py` | 5+ routes | Inbound config UI |
| `workflows.py` | 8+ routes | Workflow UI |

**Total:** ~70 routes that render HTML templates

#### Routes That COULD Move to FastAPI (API Routes)

| Route | Current | FastAPI Benefit |
|-------|---------|-----------------|
| `/api/workflows/*` | Flask JSON | ✅ Better validation |
| `/api/public/*` | Flask JSON | ✅ Auto docs |
| Webhooks | Flask JSON | ✅ Async handling |
| **NEW: `/api/v1/call/initiate`** | N/A | ✅ Native async |

**Total:** ~10 API routes

---

## Migration Strategies

### ❌ Strategy 1: Full Migration (NOT RECOMMENDED)

**Effort:** 3-4 weeks

**Changes Required:**
1. Rewrite authentication (JWT/OAuth2) - 1 week
2. Update all 70 routes - 1 week
3. Fix all templates - 3 days
4. Rewrite database layer (if going async) - 1 week
5. Testing and debugging - 3 days

**Risks:**
- 🔴 High chance of breaking existing functionality
- 🔴 Users need to re-login (session → token)
- 🔴 Frontend JavaScript changes needed
- 🔴 No clear benefit for UI routes

---

### ✅ Strategy 2: Hybrid Approach (RECOMMENDED)

**Keep Flask for UI, Add FastAPI for APIs**

```python
# main.py
from flask import Flask
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware

# Existing Flask app (unchanged!)
flask_app = Flask(__name__)
# ... all your existing routes ...

# New FastAPI app (for APIs only)
fastapi_app = FastAPI(title="NevoxAI API")

# API routes only
@fastapi_app.post('/api/v1/call/initiate')
async def initiate_call(request: CallRequest, user: User = Depends(get_api_user)):
    # New API endpoint with native async
    pass

# Mount Flask inside FastAPI
fastapi_app.mount("/", WSGIMiddleware(flask_app))

# Run: uvicorn main:fastapi_app --reload
```

**Effort:** 2-3 days

**Changes Required:**
1. Create `main.py` with hybrid setup - 1 hour
2. Add FastAPI dependencies - 30 mins
3. Create new API routes in FastAPI - 1-2 days
4. Keep all existing Flask routes - 0 changes!

**Benefits:**
- ✅ Zero changes to existing code
- ✅ FastAPI for new API endpoints
- ✅ Gradual migration path
- ✅ Best of both worlds

---

### ✅ Strategy 3: Side-by-Side (ALTERNATIVE)

Run Flask and FastAPI as separate services:

```
┌─────────────────────────────────────┐
│   NGINX (Reverse Proxy)             │
└─────────────────────────────────────┘
         │
         ├─► /api/v1/*  → FastAPI (port 8000)
         │
         └─► /*         → Flask (port 5000)
```

**Effort:** 1 day setup + API development

**Benefits:**
- ✅ Complete separation
- ✅ Independent scaling
- ✅ No code changes to Flask

**Drawbacks:**
- ⚠️ Need to run 2 servers
- ⚠️ Shared database coordination

---

## Detailed Migration Checklist (If Full Migration)

### Phase 1: Authentication (Week 1)

- [ ] Install `python-jose`, `passlib`, `python-multipart`
- [ ] Create JWT token generation
- [ ] Create token validation dependency
- [ ] Update login endpoint to return tokens
- [ ] Create `get_current_user` dependency
- [ ] Replace all `@login_required` with `Depends(get_current_user)`
- [ ] Update frontend to store/send tokens
- [ ] Test authentication flow

### Phase 2: Core Routes (Week 2)

- [ ] Convert `core.py` routes (42 routes)
  - [ ] Update all `render_template()` calls
  - [ ] Add `request` to template context
  - [ ] Convert form handling to Pydantic models
  - [ ] Update session references
- [ ] Convert `agents.py` routes (15 routes)
- [ ] Convert `campaigns.py` routes (10 routes)
- [ ] Convert remaining blueprints

### Phase 3: Database Layer (Week 3)

**If staying synchronous:**
- [ ] Create `get_db()` dependency
- [ ] Update all routes to use `db: Session = Depends(get_db)`

**If going async:**
- [ ] Install `asyncpg`, `sqlalchemy[asyncio]`
- [ ] Create async engine and session
- [ ] Rewrite all queries to use `await`
- [ ] Update models for async compatibility

### Phase 4: Templates & Static Files (Week 3)

- [ ] Update all template calls to include `request`
- [ ] Test all 50+ templates
- [ ] Fix any Jinja2 compatibility issues
- [ ] Update static file serving

### Phase 5: Testing & Deployment (Week 4)

- [ ] Test all authentication flows
- [ ] Test all CRUD operations
- [ ] Test file uploads
- [ ] Test webhooks
- [ ] Load testing
- [ ] Deploy and monitor

---

## Recommendation: Hybrid Approach

### Implementation Plan

**Week 1: Setup Hybrid Architecture**

1. **Day 1-2:** Create hybrid setup
   ```bash
   pip install fastapi uvicorn
   ```
   
   Create `main.py`:
   ```python
   from flask_app import app as flask_app
   from fastapi import FastAPI
   from fastapi.middleware.wsgi import WSGIMiddleware
   
   fastapi_app = FastAPI()
   
   # New API routes here
   from routes.api_v1 import router
   fastapi_app.include_router(router, prefix="/api/v1")
   
   # Mount Flask
   fastapi_app.mount("/", WSGIMiddleware(flask_app))
   ```

2. **Day 3-5:** Implement API endpoints
   - Create `routes/api_v1/calls.py` (FastAPI router)
   - Implement `/api/v1/call/initiate`
   - Implement `/api/v1/call/{id}/status`
   - Add API key authentication

**Week 2: Testing & Documentation**

3. **Day 1-3:** Testing
   - Test API endpoints
   - Test Flask routes still work
   - Integration testing

4. **Day 4-5:** Documentation
   - Auto-generated docs at `/docs`
   - Update README

### Code Example: Hybrid Setup

```python
# main.py
from app import app as flask_app  # Your existing Flask app
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

# Create FastAPI app
fastapi_app = FastAPI(
    title="NevoxAI API",
    description="External API for triggering calls",
    version="1.0.0"
)

# Pydantic models
class CallRequest(BaseModel):
    agent_id: int
    phone: str
    call_type: Optional[str] = "api_outbound"
    context: Optional[dict] = {}

class CallResponse(BaseModel):
    success: bool
    call_id: int
    room_name: str
    status: str

# API Key authentication
async def get_api_user(api_key: str = Header(..., alias="X-API-Key")):
    from models import User
    user = User.query.filter_by(api_key=api_key).first()
    if not user or not user.is_approved:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user

# FastAPI routes
@fastapi_app.post('/api/v1/call/initiate', response_model=CallResponse)
async def initiate_call(
    request: CallRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_api_user)
):
    from routes.agents import make_livekit_call
    from models import db, CallLog, Agent
    
    # Validate agent
    agent = Agent.query.filter_by(id=request.agent_id, user_id=user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Create CallLog
    room_name = f"api-{request.agent_id}-{int(time.time())}"
    call_log = CallLog(
        user_id=user.id,
        agent_id=request.agent_id,
        to_number=request.phone,
        room_name=room_name,
        status='initiated'
    )
    db.session.add(call_log)
    db.session.commit()
    
    # Background task
    background_tasks.add_task(
        execute_call,
        phone=request.phone,
        room_name=room_name,
        agent_name=agent.name,
        trunk_id=user.outbound_trunk_id,
        agent_id=agent.id,
        context=request.context,
        call_id=call_log.id
    )
    
    return CallResponse(
        success=True,
        call_id=call_log.id,
        room_name=room_name,
        status='initiated'
    )

async def execute_call(phone, room_name, agent_name, trunk_id, agent_id, context, call_id):
    """Execute call in background"""
    import asyncio
    from routes.agents import make_livekit_call
    
    try:
        await make_livekit_call(
            phone_number=phone,
            room_name=room_name,
            agent_name=agent_name,
            outbound_trunk_id=trunk_id,
            agent_id=agent_id,
            webhook_context=context
        )
    except Exception as e:
        logger.error(f"Call failed: {e}")

# Mount Flask app (all existing routes work unchanged!)
fastapi_app.mount("/", WSGIMiddleware(flask_app))

# Run with: uvicorn main:fastapi_app --reload --port 5004
```

---

## Summary Table

| Approach | Effort | Risk | Benefits | Recommendation |
|----------|--------|------|----------|----------------|
| **Full Migration** | 3-4 weeks | 🔴 HIGH | Better async, modern | ❌ Not worth it |
| **Hybrid (Mount)** | 2-3 days | 🟢 LOW | Best of both | ✅ **RECOMMENDED** |
| **Side-by-Side** | 1 day | 🟡 MEDIUM | Clean separation | ✅ Alternative |
| **Keep Flask Only** | 0 days | 🟢 NONE | No changes | ⚠️ Miss FastAPI benefits |

---

## Final Recommendation

### ✅ Use Hybrid Approach for API V2

**What to do:**
1. Keep your entire Flask app as-is (70+ routes, templates, auth)
2. Add FastAPI mounted inside Flask
3. Create new API endpoints in FastAPI only
4. Get benefits of FastAPI (async, validation, docs) without rewriting everything

**Timeline:**
- Setup: 1 day
- API implementation: 2-3 days
- Testing: 1 day
- **Total: 4-5 days**

**vs Full Migration:**
- Full migration: 3-4 weeks
- High risk of breaking things
- No clear benefit for UI routes

### 🎯 Action Plan

1. **This week:** Implement hybrid setup
2. **Next week:** Add API endpoints in FastAPI
3. **Future:** Gradually move more API routes to FastAPI if needed
4. **Never:** Don't migrate UI routes (not worth it)

**You get:**
- ✅ FastAPI's async for API calls
- ✅ Auto-generated API docs
- ✅ Pydantic validation
- ✅ BackgroundTasks (no ThreadPool needed!)
- ✅ Zero changes to existing code

**Bottom line:** Don't migrate to FastAPI. Use both! 🚀
