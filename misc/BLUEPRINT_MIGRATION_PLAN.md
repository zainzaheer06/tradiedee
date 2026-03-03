# Blueprint Migration Plan

## Current Status
- **File Size:** 2,578 lines
- **Total Routes:** 60 routes
- **Models:** 9 database models
- **Status:** Ready for migration

---

## Migration Strategy

### Phase 1: Foundation (CURRENT)
✅ Backup created: `app_backup.py`
✅ Directory structure created:
```
routes/
├── __init__.py
├── agents.py
├── campaigns.py
├── inbound.py
└── core.py

utils/
├── __init__.py
├── decorators.py
├── email.py
└── helpers.py
```

### Phase 2: Extract Shared Code
- [ ] Extract 9 models to `models.py`
- [ ] Extract decorators to `utils/decorators.py`
- [ ] Extract email functions to `utils/email.py`
- [ ] Extract helper functions to `utils/helpers.py`

### Phase 3: Create Blueprints
- [ ] Create `routes/agents.py` (12 routes)
- [ ] Create `routes/campaigns.py` (11 routes)
- [ ] Create `routes/inbound.py` (7 routes)
- [ ] Create `routes/core.py` (30 routes: admin, auth, tools, main, API)

### Phase 4: Update Main App
- [ ] Simplify `app.py` to use blueprints
- [ ] Register all blueprints
- [ ] Update imports

### Phase 5: Testing
- [ ] Test each blueprint independently
- [ ] Test full application
- [ ] Verify all routes work

---

## Detailed Route Distribution

### routes/agents.py (12 routes)
| Line | Route | Function |
|------|-------|----------|
| 605 | GET `/agents` | List agents |
| 598 | GET/POST `/agent/create` | Create agent |
| 620 | GET/POST `/agent/new` | New agent form |
| 703 | GET `/agent/<id>` | View agent |
| 663 | GET/POST `/agent/<id>/edit` | Edit agent |
| 723 | POST `/agent/<id>/delete` | Delete agent |
| 774 | POST `/agent/<id>/make-call` | Make call |
| 1166 | GET `/agents/<id>/knowledge-base` | KB management |
| 1189 | POST `/agents/<id>/knowledge-base/upload` | Upload KB |
| 1263 | POST `/agents/<id>/knowledge-base/<doc_id>/delete` | Delete KB doc |
| 1303 | POST `/agents/<id>/knowledge-base/rebuild` | Rebuild KB |
| 1503 | GET/POST `/agents/<id>/tools` | Agent tools |

### routes/campaigns.py (11 routes)
| Line | Route | Function |
|------|-------|----------|
| 1630 | GET `/outbound/campaigns` | List campaigns |
| 1667 | GET/POST `/outbound/campaign/create` | Create campaign |
| 1742 | GET `/outbound/campaign/<id>` | View campaign |
| 1711 | GET/POST `/outbound/campaign/<id>/edit` | Edit campaign |
| 1991 | POST `/outbound/campaign/<id>/delete` | Delete campaign |
| 1813 | POST `/outbound/campaign/<id>/upload` | Upload contacts |
| 1878 | POST `/outbound/campaign/<id>/add-contacts-manual` | Add contacts |
| 1945 | POST `/outbound/campaign/<id>/start` | Start campaign |
| 1964 | POST `/outbound/campaign/<id>/pause` | Pause campaign |
| 1977 | POST `/outbound/campaign/<id>/stop` | Stop campaign |
| 2010 | GET `/outbound/campaign/<id>/export` | Export data |

**Plus:** `/call-logs` and `/call-log/<id>` (outbound call logs)

### routes/inbound.py (7 routes)
| Line | Route | Function |
|------|-------|----------|
| 1006 | GET `/inbound` | List inbound configs |
| 1017 | GET/POST `/inbound/create` | Create inbound |
| 1080 | GET/POST `/inbound/<id>/edit` | Edit inbound |
| 1142 | POST `/inbound/<id>/delete` | Delete inbound |
| 1599 | GET `/inbound/calls` | Inbound call logs |

### routes/core.py (30 routes)

**Authentication (6 routes):**
| Line | Route | Function |
|------|-------|----------|
| 327 | GET/POST `/signup` | User signup |
| 365 | GET/POST `/login` | User login |
| 432 | GET `/logout` | Logout |
| 385 | GET `/verify-email/<token>` | Email verification |
| 411 | POST `/resend-verification` | Resend verification |
| 438 | GET `/pending-approval` | Pending approval page |

**Main Pages (5 routes):**
| Line | Route | Function |
|------|-------|----------|
| 317 | GET `/` | Landing page |
| 323 | GET `/homepage` | Homepage |
| 443 | GET `/dashboard` | User dashboard |
| 868 | GET `/subscription` | Subscription page |
| 860 | GET `/web-call` | Web call interface |
| 875 | GET `/custom-tools` | Custom tools |

**Admin (9 routes):**
| Line | Route | Function |
|------|-------|----------|
| 458 | GET `/admin` | Admin dashboard |
| 473 | POST `/admin/approve-user/<id>` | Approve user |
| 490 | POST `/admin/add-minutes/<id>` | Add minutes |
| 501 | GET `/admin/trunk-management` | Trunk management |
| 509 | GET/POST `/admin/configure-trunk/<id>` | Configure trunk |
| 537 | POST `/admin/remove-trunk/<id>` | Remove trunk |
| 553 | GET `/admin/inbound-trunk-management` | Inbound trunk mgmt |
| 562 | GET/POST `/admin/configure-inbound-trunk/<id>` | Config inbound trunk |
| 585 | POST `/admin/remove-inbound-trunk/<id>` | Remove inbound trunk |

**Tools (6 routes):**
| Line | Route | Function |
|------|-------|----------|
| 1333 | GET `/tools` | List tools |
| 1342 | GET/POST `/tools/create` | Create tool |
| 1420 | GET/POST `/tools/<id>/edit` | Edit tool |
| 1471 | POST `/tools/<id>/delete` | Delete tool |
| 1488 | POST `/tools/<id>/toggle` | Toggle tool |

**API/Webhooks (3 routes):**
| Line | Route | Function |
|------|-------|----------|
| 919 | POST `/api/demo-token` | Demo token |
| 963 | POST `/api/start-demo-agent` | Start demo agent |
| 2209 | POST `/webhook/call-ended` | Webhook: call ended |

**Call Logs (1 route):**
| Line | Route | Function |
|------|-------|----------|
| 882 | GET `/call-logs` | Outbound call logs |
| 907 | GET `/call-log/<id>` | View call log |

---

## Database Models to Extract

### models.py
```python
class User(db.Model):          # Line 77
class Agent(db.Model):         # Line 101
class InboundConfiguration(db.Model):  # Line 121
class CallLog(db.Model):       # Line 143
class Campaign(db.Model):      # Line 161
class CampaignContact(db.Model):  # Line 180
class KnowledgeBase(db.Model):  # Line 195
class Tool(db.Model):          # Line 206
class AgentTool(db.Model):     # Line 221
```

---

## Utilities to Extract

### utils/decorators.py
- `login_required()`
- `admin_required()`
- `approved_required()`

### utils/email.py
- `generate_verification_token()`
- `verify_token()`
- `send_verification_email()`
- `send_approval_notification()`

### utils/helpers.py
- `clean_text()`
- `from_json_filter()` (Jinja2 filter)

---

## Implementation Options

### Option A: Automated Migration (Recommended)
- Use Python script to extract and reorganize automatically
- Faster but requires careful testing
- **Estimated time:** 30 minutes

### Option B: Manual Migration
- Copy/paste each section manually
- Slower but more control
- **Estimated time:** 2-3 hours

### Option C: Hybrid Approach
- Extract shared code (models, utils) automatically
- Migrate routes manually one blueprint at a time
- Good balance of speed and control
- **Estimated time:** 1 hour

---

## Next Steps

1. **Review this plan** - Confirm approach
2. **Choose migration option** - A, B, or C?
3. **Execute migration** - Systematically implement
4. **Test thoroughly** - Verify all routes work
5. **Clean up** - Remove old code, update docs

---

## Rollback Plan

If migration fails:
1. Delete new files (`routes/`, `utils/`, `models.py`)
2. Restore `app_backup.py` to `app.py`
3. Application returns to original state

**Backup location:** `app_backup.py`

---

**Status:** Ready to begin migration
**Date:** November 23, 2025
**Estimated completion:** Option A: 30 min, Option B: 2-3 hrs, Option C: 1 hr
