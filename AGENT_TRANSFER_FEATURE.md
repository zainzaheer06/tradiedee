# Agent-to-Agent Call Transfer — Full Implementation Documentation

**Feature:** Live call handoff from one AI agent to another during an active session
**Status:** Working ✅
**Date:** 2026-02-16
**Last Updated:** 2026-02-18 — Transfer chime sound added

---

## Overview

When an agent's prompt rules say to transfer (e.g. "if user speaks Arabic, transfer to agent_id=47"), the agent calls the `transfer_to_agent` tool. The current agent says a brief handoff message, then control passes to the new agent which:
- Swaps the TTS voice to its own
- Plays a transfer chime sound (up to 3 seconds) — falls back to silent pause if file missing
- Says its own greeting
- Continues the call with its own prompt, tools, and config

---

## Files Changed

### 1. `models.py`
**Purpose:** Add `transfer_targets` column to the Agent database model.
**Location:** `models.py` line **60**

**Added one line:**
```python
# line 60
transfer_targets = db.Column(db.JSON, nullable=True)  # e.g. [2, 3, 4]
```

**Database migration — run once on server:**
```bash
python scripts/migrations/add_transfer_targets_column.py
```
Or raw SQL:
```sql
ALTER TABLE agent ADD COLUMN transfer_targets JSON NULL;
```

---

### 2. `routes/agents.py`
**Purpose:** Save/load `transfer_targets` in the agent edit form.

---

#### Change A — Save transfer targets on POST
**Location:** `routes/agents.py` lines **237–242**

```python
# lines 237-242
# Update handoff transfer targets
if request.form.get('handoffs_enabled'):
    selected = request.form.getlist('transfer_agents')
    agent.transfer_targets = [int(i) for i in selected] if selected else None
else:
    agent.transfer_targets = None
```

This block sits just before `db.session.commit()` at line 244.

**Before this change:** `transfer_targets` was never read or saved from the form.

---

#### Change B — POST error path (validation failure) — re-render with `user_agents`
**Location:** `routes/agents.py` lines **210–213**

```python
# lines 210-213  (inside: if not prompt_value: block)
user_agents = Agent.query.filter(
    Agent.user_id == agent.user_id,
    Agent.id != agent_id
).order_by(Agent.name).all()
return render_template('agents/new_agent_form.html', agent=agent,
                       documents=documents, document_count=document_count,
                       user_agents=user_agents)
```

**Before:** `user_agents` was not passed here, so the Handoffs tab showed "No agents found" after a validation error.

---

#### Change C — GET handler — load `user_agents` for Handoffs tab
**Location:** `routes/agents.py` lines **279–296**

```python
# lines 279-284
# Get all user agents (for handoff target selection, exclude current agent)
# Use agent.user_id (not session user_id) so admin edits also show correct agents
user_agents = Agent.query.filter(
    Agent.user_id == agent.user_id,
    Agent.id != agent_id
).order_by(Agent.name).all()

# lines 289-296
return render_template('agents/new_agent_form.html',
                     agent=agent,
                     documents=documents,
                     document_count=document_count,
                     assigned_tools=assigned_tools,
                     workflows=workflows,
                     user_agents=user_agents,          # <-- ADDED
                     elevenlabs_to_generic=elevenlabs_to_generic_mapping)
```

**Before:** `user_agents` was not queried or passed to the template.

> **Why `agent.user_id` not `session['user_id']`:**
> Admin accounts editing another user's agent would only see their own agents.
> Using `agent.user_id` fetches the actual owner's agents instead.

---

### 3. `templates/agents/new_agent_form.html`
**Purpose:** Add a "Handoffs" tab to the agent edit form UI.

#### Change A — Add Tab 5 button

**Before:** 4 tabs (Basic, Voice, Tools, Config)

**After:** Added 5th tab button:
```html
<button class="nav-link" id="handoffs-tab" data-bs-toggle="tab"
        data-bs-target="#handoffs" type="button" role="tab">
    <i class="bi bi-arrow-left-right me-1"></i> Handoffs
</button>
```

#### Change B — Add Handoffs tab panel

Full panel added with:
- **Enable toggle** — pill switch Off/On (`handoffs_enabled` checkbox)
- **Two-column layout:**
  - Left: scrollable searchable list of all other agents (checkboxes with name + ID badge)
  - Right: selected agents panel showing chosen agents as removable tags
- **Blue info box** with example prompt rules showing users how to write transfer instructions
- **JavaScript functions:**
  - `syncHandoffSelected()` — syncs left checkboxes → right panel
  - `filterHandoffAgents()` — search/filter the agent list
  - `uncheckHandoff(id)` — removes agent from right panel
  - `toggleHandoffsConfig()` — shows/hides the config section

**Example prompt rule shown to user:**
```
If the user speaks in English, transfer to agent_id=47
If the user asks about billing, transfer to agent_id=52
```

---

### 4. `agent-server_api.py`
**Purpose:** Core agent server — transfer logic, voice swap, greeting on handoff.

---

#### Change A — `get_agent_config()` — include `transfer_targets` in cached config
**Location:** `agent-server_api.py` line **147**

```python
# line 147  (inside the config dict in get_agent_config())
'transfer_targets': agent.transfer_targets or None,
```

**Before:** This key was missing — the agent config dict had no `transfer_targets`.

---

#### Change B — `Assistant.__init__` — new parameters
**Location:** `agent-server_api.py` line **638**

**Original:**
```python
def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None) -> None:
```

**After transfer feature:**
```python
def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None,
             chat_ctx=None, is_transferred: bool = False) -> None:
```

**Current (with chime):**
```python
def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None,
             chat_ctx=None, is_transferred: bool = False, background_audio=None) -> None:
```

All params:
- `chat_ctx` — passes conversation history to new agent (old system prompt stripped)
- `is_transferred` — flag so `on_enter` knows to swap voice, play chime, and say greeting
- `background_audio` — `BackgroundAudioPlayer` instance created in `entrypoint`, carried through every transfer

Stored instance attributes:
```python
self.config = config
self.is_transferred = is_transferred
self.background_audio = background_audio   # NEW (chime update)
self._session = None
```

---

#### Change C — `on_enter()` — swap TTS voice, play chime, say greeting on transfer
**Location:** `agent-server_api.py` lines **673–710**

**Before (original — silent pause only):**
```python
        # Brief pause so the handoff feels natural (not instant)
        await asyncio.sleep(1.2)
```

**After step 1 (log lines added):**
```python
        # Brief pause so the handoff feels natural (not instant)
        logger.info("⏸️ Handoff pause (1.2s)...")
        await asyncio.sleep(1.2)
        logger.info("▶️ Resuming — new agent greeting starting")
```

**After step 2 — current code (chime player):**
```python
        # Play transfer chime / pause before new agent greets
        chime_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds', 'transfer.mp3')
        if self.background_audio and os.path.exists(chime_path):
            try:
                logger.info(f"🎵 Playing transfer chime (max 3s): {chime_path}")
                handle = self.background_audio.play(chime_path)
                await asyncio.sleep(3.0)
                handle.stop()
                logger.info("🎵 Transfer chime done — new agent greeting starting")
            except Exception as e:
                logger.error(f"❌ Failed to play chime: {e}")
                logger.info("⏸️ Fallback pause (2s)...")
                await asyncio.sleep(2)
                logger.info("▶️ Resuming — new agent greeting starting")
        else:
            if not os.path.exists(chime_path):
                logger.warning(f"⚠️ Chime file not found: {chime_path} — using silent pause")
            logger.info("⏸️ Handoff pause (2s)...")
            await asyncio.sleep(2)
            logger.info("▶️ Resuming — new agent greeting starting")
```

> **Key note:** `AgentSession.tts` is read-only — direct assignment raises `can't set attribute`. The private `self.session._tts` works.

> **How the 3s cap works:** `background_audio.play()` without `await` starts playback and returns a `PlayHandle` immediately. After `asyncio.sleep(3.0)`, `handle.stop()` cuts it. If the file is shorter than 3s it finishes naturally — no issue.

> **Tuning the chime duration:** Change `asyncio.sleep(3.0)` value. Applied identically in both `agent-server_api.py` and `server-code/agent-inbound.py`.

---

#### Change D — `transfer_to_agent` `@function_tool`
**Location:** `agent-server_api.py` lines **806 (decorator) – 851**

```python
# line 806  @function_tool decorator
# line 807  async def transfer_to_agent(self, ctx: RunContext, agent_id: int):

# line 813  Security check
allowed = self.config.get('transfer_targets') or []
if agent_id not in allowed:
    return "Transfer not allowed to that agent"

# line 824  Handoff announcement (old agent last words)
await ctx.session.generate_reply(instructions="...")
await ctx.wait_for_playout()

# line 831  Strip old system prompt, keep conversation
raw_messages = list(self.chat_ctx)
clean_messages = [m for m in raw_messages if m.role != "system"]
clean_ctx = llm.ChatContext(messages=clean_messages) if clean_messages else None

# Return new agent — LiveKit swaps automatically
return Assistant(
    config=target_config,
    agent_id=agent_id,
    preloaded_tools=target_tools,
    chat_ctx=clean_ctx,
    is_transferred=True,
    background_audio=self.background_audio,   # NEW — carry player to new agent
)
```

> **Critical:** `@function_tool` auto-registers the method. Do NOT manually add it to `tools=[]` — causes `ValueError: duplicate function name`.

> **Why pass `background_audio`:** The `BackgroundAudioPlayer` is created once in `entrypoint`. Each transferred `Assistant` must receive it so it can play the chime. If not passed, `self.background_audio` is `None` and the chime silently falls back to the sleep pause.

---

#### Change E — `build_tts_engine()` — module-level function
**Location:** `agent-server_api.py` lines **896–912** (just before `entrypoint`)

```python
# lines 896-912
def build_tts_engine(config):
    """Build a TTS engine from agent config. Module-level so it can be called from anywhere."""
    return elevenlabs.TTS(
        voice_id=config['voice_id'],
        model="eleven_turbo_v2_5",
        ...
    )
```

Inside `entrypoint`, `create_tts_engine` is now an alias at line **959–960**:
```python
# lines 959-960
def create_tts_engine(config):
    return build_tts_engine(config)
```

**Before:** TTS creation was only inside `entrypoint()` — inaccessible to `Assistant.on_enter()`.

---

#### Change F — Imports — add `BackgroundAudioPlayer`
**Location:** `agent-server_api.py` lines **32–47**

**Before:**
```python
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    ...
)
```

**After:**
```python
from livekit.agents import (
    Agent,
    AgentSession,
    AudioConfig,           # NEW
    BackgroundAudioPlayer, # NEW
    JobContext,
    ...
)
```

---

#### Change G — `entrypoint()` — create and start `BackgroundAudioPlayer`
**Location:** `agent-server_api.py` — two `session.start()` call sites:
- Non-campaign rooms: ~line **1382**
- Campaign rooms: ~line **1573**

**Before (both sites):**
```python
await session.start(
    room=ctx.room,
    agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools),
    room_input_options=RoomInputOptions(...),
)
```

**After (both sites):**
```python
background_audio = BackgroundAudioPlayer()
await session.start(
    room=ctx.room,
    agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools,
                    background_audio=background_audio),
    room_input_options=RoomInputOptions(...),
)
await background_audio.start(room=ctx.room, agent_session=session)
logger.info("🎵 BackgroundAudioPlayer started (ready for transfer chimes)")
```

> **Why `start()` must come AFTER `session.start()`:** `background_audio.start()` requires `agent_session=session` to be already running. The initial agent's `on_enter()` has `is_transferred=False` so it never tries to play — the player just needs to be ready before the first transfer happens.

---

### 5. `server-code/agent-inbound.py`
**Purpose:** Inbound SIP call agent server — same transfer + chime feature applied here.

All changes are **identical** to `agent-server_api.py` (Sections 4B–4G above), applied to the same class and same locations in this file.

**Key differences from `agent-server_api.py`:**
- Only **one** `session.start()` call in `entrypoint` (no campaign path)
- Sound file path resolves to: `server-code/sounds/transfer.mp3`

**`entrypoint` change location:** ~line **1088**

```python
background_audio = BackgroundAudioPlayer()
await session.start(
    room=ctx.room,
    agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools,
                    background_audio=background_audio),
    room_input_options=RoomInputOptions(
        noise_cancellation=noise_cancellation.BVCTelephony(),
    ),
)
await background_audio.start(room=ctx.room, agent_session=session)
logger.info("🎵 BackgroundAudioPlayer started (ready for transfer chimes)")
```

---

### Transfer Sound File Setup

Place your audio file at these paths (relative to each script):

| Script | Sound file path |
|--------|----------------|
| `agent-server_api.py` | `sounds/transfer.mp3` |
| `server-code/agent-inbound.py` | `server-code/sounds/transfer.mp3` |

**Supported formats:** MP3, WAV, OGG, AAC, FLAC (LiveKit uses FFmpeg/PyAV; WAV has fastest load)

**Ideal length:** 1–3 seconds. The 3s cap cuts anything longer automatically.

**If file is missing:** Falls back to `asyncio.sleep(2)` silent pause — nothing breaks. Log will show:
```
⚠️ Chime file not found: .../sounds/transfer.mp3 — using silent pause
```

**Tuning the cap:** Change `asyncio.sleep(3.0)` in `on_enter()` of both files.

---

## Call Flow (Transfer Sequence)

```
User speaks → triggers transfer rule in prompt
      ↓
LLM calls transfer_to_agent(agent_id=47)
      ↓
Security check: is 47 in transfer_targets? ✅
      ↓
Load target agent config from Redis/DB
      ↓
Old agent says: "سأحولك الآن إلى وكيل آخر" (1 sentence)
      ↓
Strip system prompt, keep conversation messages
      ↓
Return Assistant(config=target, is_transferred=True, background_audio=...)
      ↓
LiveKit swaps agent in session automatically
      ↓
on_enter() fires:
  → self.session._tts = new TTS engine (new voice)
  → BackgroundAudioPlayer.play("sounds/transfer.mp3") — max 3s, then handle.stop()
     (fallback: asyncio.sleep(2) if file not found)
  → await self.session.say(greeting)  (new agent greets with its own voice)
      ↓
Call continues with new agent's voice, prompt, tools
```

---

## Bugs Fixed During Implementation

| Bug | Cause | Fix |
|-----|-------|-----|
| `ValueError: duplicate function name` | `@function_tool` auto-registers AND manual append to `tools=[]` | Removed manual append |
| Handoffs tab shows "No other agents found" | Route used `session['user_id']` (admin), not `agent.user_id` (owner) | Changed to `agent.user_id` |
| LLM calls wrong `agent_id` | Redis cache had stale prompt with old agent_id | Clear cache: `redis_service.invalidate_agent_config(agent_id)` |
| `AttributeError: '_ReadOnlyChatContext' has no attribute 'messages'` | LiveKit Realtime model wraps `chat_ctx` as read-only | Use `list(self.chat_ctx)` instead of `.messages` |
| `can't set attribute 'tts'` | `AgentSession.tts` is a read-only property | Use `self.session._tts = new_tts` (private attribute) |

---

## How to Configure an Agent for Transfers (User Instructions)

1. Go to **Agent Edit Form → Handoffs tab**
2. Toggle **Enable Handoffs** to ON
3. Select the target agents from the list
4. In the agent's **Prompt**, add transfer rules like:

```
# TRANSFER RULES
- If the user speaks in English, call transfer_to_agent with agent_id=47
- If the user asks about billing, call transfer_to_agent with agent_id=52
- If the user wants to speak to sales, call transfer_to_agent with agent_id=61
```

The agent IDs are shown as badges next to each agent name in the Handoffs tab.

---

## Backup Files (pre-change state)

| Backup File | Original File |
|-------------|--------------|
| `models_bk_transfer.py` | `models.py` |
| `routes/agents_bk_transfer.py` | `routes/agents.py` |
| `templates/agents/new_agent_form_bk_transfer.html` | `templates/agents/new_agent_form.html` |
| `agent-server_api_bk_transfer.py` | `agent-server_api.py` |
