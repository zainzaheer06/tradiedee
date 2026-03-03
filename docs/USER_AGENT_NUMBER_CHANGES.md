# User-Based Agent Numbering - Implementation Changes

## Overview

This document describes the changes required to implement user-specific agent numbering where:
- User A has agents: 1, 2, 3, 4
- User B has agents: 1, 2, 3, 4 (separate sequence)

Instead of global database IDs (1, 2, 3... across all users), each user gets their own sequential numbering.

---

## Database Model (Already Exists)

**File:** `models.py`

The `user_agent_number` field already exists in the Agent model:

```python
# Line 41
user_agent_number = db.Column(db.Integer, nullable=True)  # User-specific sequential number
```

This field is already populated when creating new agents (see `routes/agents.py` lines 115-116).

---

## Changes Required

### 1. Routes File: `routes/agents.py`

#### A. Add Helper Function (after line 140)

```python
# ==================== HELPER FUNCTION ====================

def get_agent_by_user_number(agent_num):
    """
    Get agent by user_agent_number for the current user.
    Returns None if not found.
    """
    agent = Agent.query.filter_by(
        user_id=session['user_id'],
        user_agent_number=agent_num
    ).first()

    # Fallback for admin: allow access by global ID
    if not agent and session.get('is_admin'):
        agent = Agent.query.get(agent_num)

    return agent
```

#### B. Update Route Decorators and Functions

| Original (Line) | Change From | Change To |
|-----------------|-------------|-----------|
| Line 143 | `@agents_bp.route('/<int:agent_id>')` | `@agents_bp.route('/<int:agent_num>')` |
| Line 146 | `def view_agent(agent_id):` | `def view_agent(agent_num):` |
| Line 148 | `agent = Agent.query.get_or_404(agent_id)` | `agent = get_agent_by_user_number(agent_num)` |
| Line 165 | `@agents_bp.route('/<int:agent_id>/edit', ...)` | `@agents_bp.route('/<int:agent_num>/edit', ...)` |
| Line 168 | `def edit_agent_form(agent_id):` | `def edit_agent_form(agent_num):` |
| Line 277 | `@agents_bp.route('/<int:agent_id>/delete', ...)` | `@agents_bp.route('/<int:agent_num>/delete', ...)` |
| Line 280 | `def delete_agent(agent_id):` | `def delete_agent(agent_num):` |
| Line 332 | `@agents_bp.route('/<int:agent_id>/make-call', ...)` | `@agents_bp.route('/<int:agent_num>/make-call', ...)` |
| Line 335 | `def make_call_route(agent_id):` | `def make_call_route(agent_num):` |
| Line 478 | `@agents_bp.route('/<int:agent_id>/knowledge-base')` | `@agents_bp.route('/<int:agent_num>/knowledge-base')` |
| Line 501 | `@agents_bp.route('/<int:agent_id>/knowledge-base/upload', ...)` | `@agents_bp.route('/<int:agent_num>/knowledge-base/upload', ...)` |
| Line 571 | `@agents_bp.route('/<int:agent_id>/knowledge-base/<int:doc_id>/delete', ...)` | `@agents_bp.route('/<int:agent_num>/knowledge-base/<int:doc_id>/delete', ...)` |
| Line 609 | `@agents_bp.route('/<int:agent_id>/knowledge-base/rebuild', ...)` | `@agents_bp.route('/<int:agent_num>/knowledge-base/rebuild', ...)` |
| Line 638 | `@agents_bp.route('/<int:agent_id>/tools', ...)` | `@agents_bp.route('/<int:agent_num>/tools', ...)` |

#### C. Update Internal References

Inside each function, change:
- `agent_id` parameter to `agent_num`
- Lookup: `Agent.query.get_or_404(agent_id)` to `get_agent_by_user_number(agent_num)`
- Keep using `agent.id` for internal DB operations (CallLog, KnowledgeBase, etc.)
- Use `agent.user_agent_number` for URL generation

#### D. Update Redirects

| Line | Change From | Change To |
|------|-------------|-----------|
| Line 136 | `agent_id=new_agent.id` | `agent_num=new_agent.user_agent_number` |
| Line 247 | `agent_id=agent_id` | `agent_num=agent.user_agent_number` |
| Line 527, 533 | `agent_id=agent_id` | `agent_num=agent.user_agent_number` |
| Line 582 | `agent_id=agent_id` | `agent_num=agent.user_agent_number` |
| Line 620 | `agent_id=agent_id` | `agent_num=agent.user_agent_number` |
| Line 647 | `agent_id=agent_id` | `agent_num=agent.user_agent_number` |
| Line 688, 696 | `agent_id=agent_id` | `agent_num=agent.user_agent_number` |

---

### 2. Template: `templates/agents/agents_list.html`

#### A. Add Agent Number Badge (Line 47-55)

```html
<!-- Inside Card Header -->
<div class="flex items-center gap-2">
    <span class="inline-flex items-center justify-center w-7 h-7 bg-white/30 backdrop-blur-sm rounded-full text-xs font-bold text-white">
        {{ agent.user_agent_number or '?' }}
    </span>
    <h3 class="text-lg font-bold text-white truncate">{{ agent.name }}</h3>
</div>
```

#### B. Update URL References (Lines 80-92)

| Line | Change From | Change To |
|------|-------------|-----------|
| 80 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |
| 84 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |
| 89 | `confirmDelete({{ agent.id }}, ...)` | `confirmDelete({{ agent.user_agent_number }}, ...)` |

#### C. Update JavaScript (Lines 165-168)

```javascript
// Change function parameter
function confirmDelete(agentNum, agentName) {
    document.getElementById('agentNameToDelete').textContent = agentName;
    document.getElementById('deleteForm').action = '/agent/' + agentNum + '/delete';
    document.getElementById('deleteModal').classList.remove('hidden');
}
```

---

### 3. Template: `templates/agents/view_agent.html`

#### A. Show Agent Number in Header (Lines 20-21)

```html
<div class="flex items-center justify-center w-12 h-12 bg-indigo-600 rounded-lg">
    <span class="text-white text-lg font-bold">{{ agent.user_agent_number or '?' }}</span>
</div>
```

#### B. Update Pagination URLs (Lines 131, 141)

| Line | Change From | Change To |
|------|-------------|-----------|
| 131 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |
| 141 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |

#### C. Update Make Call URL (Line 275)

```javascript
const response = await fetch('{{ url_for("agents.make_call_route", agent_num=agent.user_agent_number) }}', {
```

---

### 4. Template: `templates/agents/new_agent_form.html`

| Line | Change From | Change To |
|------|-------------|-----------|
| 21 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |
| 498 | `uploadKnowledgeBase({{ agent.id }})` | `uploadKnowledgeBase({{ agent.user_agent_number }})` |
| 531 | `deleteKnowledgeBaseDocument({{ agent.id }}, ...)` | `deleteKnowledgeBaseDocument({{ agent.user_agent_number }}, ...)` |
| 608 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |

#### Update JavaScript Functions (Lines 1250, 1270, 1296, 1301)

```javascript
function uploadKnowledgeBase(agentNum) {
    // ...
    fetch(`/agent/${agentNum}/knowledge-base/upload`, {
    // ...
}

function deleteKnowledgeBaseDocument(agentNum, docId, filename) {
    // ...
    fetch(`/agent/${agentNum}/knowledge-base/${docId}/delete`, {
    // ...
}
```

---

### 5. Template: `templates/agents/agent_knowledge_base.html`

| Line | Change From | Change To |
|------|-------------|-----------|
| 63 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |
| 93 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |
| 146 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |

---

### 6. Template: `templates/tools/agent_tools.html`

| Line | Change From | Change To |
|------|-------------|-----------|
| 12 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |
| 55 | `agent_id=agent.id` | `agent_num=agent.user_agent_number` |

---

## Backfill Script for Existing Agents

Add to `app.py` in `init_db()` function:

```python
def init_db():
    """Initialize database and create default admin user"""
    with app.app_context():
        db.create_all()
        logger.info("Database tables created")

        # Backfill user_agent_number for existing agents
        from models import Agent
        from sqlalchemy import func

        # Find agents without user_agent_number
        agents_without_number = Agent.query.filter(
            Agent.user_agent_number.is_(None)
        ).order_by(Agent.user_id, Agent.created_at).all()

        if agents_without_number:
            logger.info(f"Backfilling {len(agents_without_number)} agents with user_agent_number")

            # Group by user and assign sequential numbers
            user_counters = {}
            for agent in agents_without_number:
                if agent.user_id not in user_counters:
                    # Get max existing number for this user
                    max_num = db.session.query(func.max(Agent.user_agent_number)).filter(
                        Agent.user_id == agent.user_id,
                        Agent.user_agent_number.isnot(None)
                    ).scalar() or 0
                    user_counters[agent.user_id] = max_num

                user_counters[agent.user_id] += 1
                agent.user_agent_number = user_counters[agent.user_id]

            db.session.commit()
            logger.info("Backfill complete")

        # ... rest of init_db
```

---

## Important Notes

1. **Internal Operations**: Always use `agent.id` (global database ID) for:
   - Database relationships (CallLog, KnowledgeBase, Campaign, etc.)
   - Room names for calls (`call-{agent.id}-{timestamp}`)
   - Redis cache keys
   - File storage paths

2. **URL/Display Only**: Use `agent.user_agent_number` for:
   - URL parameters
   - Display in UI
   - User-facing references

3. **Admin Fallback**: The helper function allows admins to still access agents by global ID as a fallback.

---

## Files Summary

| File | Type | Changes |
|------|------|---------|
| `routes/agents.py` | Routes | Route decorators, function parameters, lookups, redirects |
| `templates/agents/agents_list.html` | Template | URLs, JavaScript, agent number badge |
| `templates/agents/view_agent.html` | Template | URLs, agent number display |
| `templates/agents/new_agent_form.html` | Template | Form action, JavaScript functions |
| `templates/agents/agent_knowledge_base.html` | Template | Form actions |
| `templates/tools/agent_tools.html` | Template | Back/cancel links |
| `app.py` | Startup | Backfill script in init_db() |

---

*Document created: January 2026*
*Status: NOT IMPLEMENTED (reverted to original)*
