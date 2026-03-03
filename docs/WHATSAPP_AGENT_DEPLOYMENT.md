# WhatsApp Agent Feature — Production Deployment Guide

**Date:** February 2026  
**Feature:** WhatsApp AI Agents with Provider Support + Socials Sidebar  

---

## Overview

This feature adds a full WhatsApp Agent system that auto-generates n8n workflows.  
Users create a WhatsApp agent in the dashboard → system generates and deploys an n8n workflow → workflow handles incoming WhatsApp messages via webhook.

Supports multiple providers: **Whapi**, **Meta (Official)**, **Unifonic**, and **Custom**.

---

## NEW FILES (copy to production)

| # | File | Lines | Description |
|---|------|-------|-------------|
| 1 | `services/n8n_service.py` | 954 lines | n8n API client + workflow JSON generator |
| 2 | `routes/whatsapp.py` | 423 lines | All WhatsApp agent CRUD + deploy routes |
| 3 | `templates/whatsapp/whatsapp_agents.html` | 161 lines | List page — all WhatsApp agents |
| 4 | `templates/whatsapp/new_whatsapp_agent.html` | 274 lines | Create form with provider dropdown |
| 5 | `templates/whatsapp/edit_whatsapp_agent.html` | 226 lines | Edit form with provider dropdown |
| 6 | `templates/whatsapp/view_whatsapp_agent.html` | 313 lines | View page with deploy/activate controls |
| 7 | `docs/scripts/migrate_whatsapp_agent.py` | 105 lines | DB migration script |

---

## MODIFIED FILES (changes in existing files)

### 1. `models.py` (330 lines total)

**What changed:** Added new `WhatsAppAgent` model class

| Change | Lines |
|--------|-------|
| New `WhatsAppAgent` class definition | L264–L330 (entire class is new, appended at end of file) |
| `whatsapp_provider` field | L276 |
| `send_text_endpoint` field | L284 |
| `send_voice_endpoint` field | L285 |

**Code to add at the end of `models.py` (after the last existing model):**
```python
class WhatsAppAgent(db.Model):
    """WhatsApp AI Agent - connects an existing Agent to WhatsApp via auto-generated n8n workflow"""
    __tablename__ = 'whatsapp_agent'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    whatsapp_provider = db.Column(db.String(50), default='whapi')
    whatsapp_api_url = db.Column(db.String(500), nullable=False)
    whatsapp_api_key = db.Column(db.String(255), nullable=False)
    whatsapp_phone_number = db.Column(db.String(20), nullable=True)
    send_text_endpoint = db.Column(db.String(500), nullable=True)
    send_voice_endpoint = db.Column(db.String(500), nullable=True)
    whatsapp_system_prompt = db.Column(db.Text, nullable=True)
    enable_voice_response = db.Column(db.Boolean, default=False)
    enable_image_analysis = db.Column(db.Boolean, default=True)
    enable_document_analysis = db.Column(db.Boolean, default=True)
    memory_window = db.Column(db.Integer, default=10)
    n8n_workflow_id = db.Column(db.String(100), nullable=True)
    n8n_workflow_active = db.Column(db.Boolean, default=False)
    webhook_path = db.Column(db.String(200), nullable=True, unique=True)
    is_active = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='draft')
    error_message = db.Column(db.Text, nullable=True)
    total_messages = db.Column(db.Integer, default=0)
    total_conversations = db.Column(db.Integer, default=0)
    last_message_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None),
                           onupdate=lambda: datetime.now(SAUDI_TZ).replace(tzinfo=None))

    user = db.relationship('User', backref='whatsapp_agents')
    agent = db.relationship('Agent', backref='whatsapp_agents')

    @property
    def effective_prompt(self):
        base = self.agent.prompt if self.agent else ''
        if self.whatsapp_system_prompt:
            return f"{base}\n\n--- WhatsApp-Specific Instructions ---\n{self.whatsapp_system_prompt}"
        return base
```

---

### 2. `routes/__init__.py` (28 lines total)

**What changed:** Registered WhatsApp blueprint

| Change | Line |
|--------|------|
| Import `whatsapp_bp` | L16 |
| `app.register_blueprint(whatsapp_bp, url_prefix='/whatsapp')` | L27 |

**Add this import (around L16):**
```python
from routes.whatsapp import whatsapp_bp
```

**Add this registration (around L27, after other register_blueprint calls):**
```python
app.register_blueprint(whatsapp_bp, url_prefix='/whatsapp')
```

---

### 3. `templates/base.html` (532 lines total)

**What changed:** Removed standalone WhatsApp nav link → Added "Socials" dropdown with WhatsApp inside + JS toggle + auto-expand

| Change | Lines | Description |
|--------|-------|-------------|
| Removed standalone WhatsApp link | was ~L250 | Deleted the `<a href="whatsapp">` nav item |
| Added Socials dropdown (HTML) | L291–L306 | New dropdown matching Inbound/Outbound style |
| Added `toggleSocialsMenu()` JS | L437–L443 | Toggle function for Socials submenu |
| Added Socials auto-expand | L484–L491 | Auto-opens Socials submenu on `/whatsapp` pages |

**Socials dropdown HTML (add after Outbound dropdown, around L291):**
```html
<!-- Socials Channel Dropdown -->
<div>
    <button onclick="toggleSocialsMenu()" class="nav-item w-full flex items-center justify-between px-4 py-3 text-gray-700 rounded-lg font-medium">
        <div class="flex items-center gap-3">
            <i class="bi bi-share text-lg"></i>
            <span>Socials</span>
        </div>
        <i id="socials-chevron" class="bi bi-chevron-down text-sm transition-transform"></i>
    </button>
    <div id="socials-submenu" class="submenu hidden mt-1 ml-4 space-y-1">
        <a href="{{ url_for('whatsapp.whatsapp_agents_list') }}" class="nav-item {% if request.endpoint and 'whatsapp' in request.endpoint %}active{% endif %} flex items-center gap-3 px-4 py-2 text-gray-700 rounded-lg text-sm">
            <i class="bi bi-whatsapp text-base" style="color: #25D366;"></i>
            <span>WhatsApp</span>
        </a>
    </div>
</div>
```

**JavaScript toggle function (add after `toggleOutboundMenu`):**
```javascript
function toggleSocialsMenu() {
    const submenu = document.getElementById('socials-submenu');
    const chevron = document.getElementById('socials-chevron');
    submenu.classList.toggle('show');
    submenu.classList.toggle('hidden');
    chevron.classList.toggle('chevron-rotate');
}
```

**Auto-expand (add inside `DOMContentLoaded` after outbound auto-expand):**
```javascript
// Socials menu
if (currentPath.includes('/whatsapp')) {
    const submenu = document.getElementById('socials-submenu');
    const chevron = document.getElementById('socials-chevron');
    if (submenu && chevron) {
        submenu.classList.add('show');
        submenu.classList.remove('hidden');
        chevron.classList.add('chevron-rotate');
    }
}
```

---

## HIDDEN FEATURES (display:none — not removed, can be re-enabled later)

These are hidden in the UI but the code/model still supports them:

| Feature | Files affected |
|---------|---------------|
| Image Analysis toggle | `new_whatsapp_agent.html` L167, `edit_whatsapp_agent.html` L149, `view_whatsapp_agent.html` L203 |
| Document/PDF Analysis toggle | `new_whatsapp_agent.html` L175, `edit_whatsapp_agent.html` L157, `view_whatsapp_agent.html` L209 |
| Image/PDF badges on list page | `whatsapp_agents.html` L73, L77 |

To re-enable: remove `style="display:none"` from those elements.

---

## DATABASE MIGRATION

### Option A: Run the migration script
```bash
cd /path/to/nevoxai-project
python docs/scripts/migrate_whatsapp_agent.py
```

### Option B: Manual SQL
```sql
CREATE TABLE IF NOT EXISTS whatsapp_agent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    whatsapp_provider VARCHAR(50) DEFAULT 'whapi',
    whatsapp_api_url VARCHAR(500) NOT NULL,
    whatsapp_api_key VARCHAR(255) NOT NULL,
    whatsapp_phone_number VARCHAR(20),
    send_text_endpoint VARCHAR(500),
    send_voice_endpoint VARCHAR(500),
    whatsapp_system_prompt TEXT,
    enable_voice_response BOOLEAN DEFAULT 0,
    enable_image_analysis BOOLEAN DEFAULT 1,
    enable_document_analysis BOOLEAN DEFAULT 1,
    memory_window INTEGER DEFAULT 10,
    n8n_workflow_id VARCHAR(100),
    n8n_workflow_active BOOLEAN DEFAULT 0,
    webhook_path VARCHAR(200) UNIQUE,
    is_active BOOLEAN DEFAULT 0,
    status VARCHAR(20) DEFAULT 'draft',
    error_message TEXT,
    total_messages INTEGER DEFAULT 0,
    total_conversations INTEGER DEFAULT 0,
    last_message_at DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES user(id),
    FOREIGN KEY (agent_id) REFERENCES agent(id)
);
```

If the table already exists but is missing the provider columns:
```sql
ALTER TABLE whatsapp_agent ADD COLUMN whatsapp_provider VARCHAR(50) DEFAULT 'whapi';
ALTER TABLE whatsapp_agent ADD COLUMN send_text_endpoint VARCHAR(500);
ALTER TABLE whatsapp_agent ADD COLUMN send_voice_endpoint VARCHAR(500);
```

---

## ENVIRONMENT VARIABLES (optional — has defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `N8N_API_URL` | `https://automation.nevoxai.com/api/v1` | n8n REST API base URL |
| `N8N_API_KEY` | (empty) | n8n API key |
| `N8N_OPENAI_CREDENTIAL_ID` | `KQ0gg0kyk4bsjjJL` | OpenAI credential ID in n8n |
| `N8N_OPENAI_CREDENTIAL_NAME` | `OpenAi account` | OpenAI credential name in n8n |

---

## DEPLOYMENT CHECKLIST

1. [ ] Copy **7 new files** listed above to production
2. [ ] Apply changes to `models.py` (add WhatsAppAgent class at end)
3. [ ] Apply changes to `routes/__init__.py` (import + register blueprint)
4. [ ] Apply changes to `templates/base.html` (Socials dropdown + JS)
5. [ ] Run migration: `python docs/scripts/migrate_whatsapp_agent.py`
6. [ ] Set `N8N_API_KEY` environment variable if not already set
7. [ ] Restart the application server
8. [ ] Test: Create WhatsApp agent → Deploy → Verify workflow appears in n8n
