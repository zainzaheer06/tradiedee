# 🚀 Webhook Context Implementation Guide

**Feature**: Inject customer/order context data into AI agent prompts for personalized conversations

**Implementation Date**: February 2026
**Status**: ✅ Complete & Tested

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Files Modified](#files-modified)
3. [Detailed Changes](#detailed-changes)
4. [Server-Side Manual Implementation](#server-side-manual-implementation)
5. [Testing](#testing)
6. [Architecture Flow](#architecture-flow)

---

## 🎯 Overview

### What is Webhook Context?

Webhook context allows you to pass customer data (name, order ID, loyalty status, etc.) through the API to the agent worker, where it gets injected into the agent's system prompt. This enables personalized, context-aware conversations.

### Example Flow

```
API Request with context:
{
  "agent_id": 74,
  "phone_number": "+966501234567",
  "context": {
    "customer_name": "زين",
    "order_id": "ORD-2024-001",
    "service_type": "Internet"
  }
}
     ↓
API builds LiveKit room metadata
     ↓
Agent worker extracts metadata
     ↓
Agent sees context in prompt:
"# 📊 بيانات العميل
{
  "customer_name": "زين",
  "order_id": "ORD-2024-001",
  "service_type": "Internet"
}"
     ↓
Agent uses context: "أهلاً زين، بخصوص طلبيتك ORD-2024-001"
```

---

## 📁 Files Modified

| File | Purpose | Changes |
|------|---------|---------|
| `routes/api_v1.py` | REST API endpoint | Already had webhook context support ✅ |
| `agent-server_api.py` | Agent worker | **5 major changes** ⭐ |
| `scripts/test_webhook_context.py` | Test suite | Created for validation |

---

## 🔧 Detailed Changes

### FILE 1: `routes/api_v1.py` (API Layer)

**Status**: ✅ Already supports webhook context

#### Function: `make_livekit_call()` - Lines 138-176

**What it does**: Creates LiveKit room with webhook context in metadata

```python
async def make_livekit_call(
    phone_number: str,
    room_name: str,
    agent_name: str,
    outbound_trunk_id: str,
    agent_id: int = None,
    webhook_context: dict = None  # ⭐ NEW PARAMETER
):
    """
    Create a LiveKit room and initiate an outbound call

    Args:
        webhook_context: Optional dict with customer data
    """
    lkapi = api.LiveKitAPI()

    # ⭐ Line 155-160: Create metadata with context
    room_metadata = {
        "type": "outbound_api",
        "agent_id": agent_id,
        "phone_number": phone_number,
        "webhook_context": webhook_context  # ⭐ PASS CONTEXT HERE
    }

    # Line 166-173: Create SIP participant with metadata
    sip_participant = await lkapi.sip.create_sip_participant(
        api.CreateSIPParticipantRequest(
            room_name=room_name,
            sip_trunk_id=outbound_trunk_id,
            sip_call_to=phone_number,
            participant_identity="phone_user",
            participant_metadata=json.dumps(room_metadata)  # ⭐ METADATA SENT HERE
        )
    )

    await lkapi.aclose()
```

#### Function: `create_outbound_call()` - Lines 181-325

**What it does**: REST API endpoint that accepts context in request body

```python
@api_v1_bp.route('/calls/outbound', methods=['POST'])
@require_api_key
def create_outbound_call():
    """
    POST /api/v1/calls/outbound

    Request Body:
    {
        "agent_id": 12,
        "phone_number": "+966501234567",
        "context": {                      # ⭐ NEW FIELD
            "customer_name": "Ahmed",
            "order_id": "ORD-456"
        }
    }
    """

    # Line 273: Extract context from request
    context = data.get('context', {})

    # Line 283-290: Pass context to LiveKit
    asyncio.run(make_livekit_call(
        phone_number=formatted_number,
        room_name=room_name,
        agent_name=agent.name,
        outbound_trunk_id=outbound_trunk_id,
        agent_id=agent_id,
        webhook_context=context if context else None  # ⭐ PASS HERE
    ))
```

---

### FILE 2: `agent-server_api.py` (Agent Worker) ⭐ MAIN CHANGES

#### CHANGE 1: New Function - Prompt Builder with Context

**Location**: After `build_full_prompt()` function (Line 642-676)

**Function Name**: `build_prompt_with_webhook_context()`

```python
def build_prompt_with_webhook_context(user_prompt: str, webhook_context: dict) -> str:
    """
    Inject webhook data into prompt for pre-call context

    Args:
        user_prompt: Agent's prompt from database
        webhook_context: Customer data dict (e.g., customer_name, order_id)

    Returns:
        Complete prompt with system instructions + user prompt + webhook data
    """
    # Line 654: Get base prompt with system instructions
    base_prompt = build_full_prompt(user_prompt)

    # Line 657-668: If context exists, inject it
    if webhook_context:
        webhook_text = json.dumps(webhook_context, ensure_ascii=False, indent=2)

        webhook_section = f"""

# 📊 بيانات العميل من النظام (Customer Data from System)
```json
{webhook_text}
```

Use this context to personalize the conversation. Address the customer by name if provided. Reference their order/case details naturally in conversation.
"""

        full_prompt = base_prompt + webhook_section  # ⭐ INJECT CONTEXT
        logger.info(f"✅ Prompt built WITH webhook context: {list(webhook_context.keys())}")
        return full_prompt
    else:
        # Line 675-676: No context, use default
        logger.info(f"ℹ️ Prompt built WITHOUT webhook context")
        return base_prompt
```

**Key Lines**:
- **Line 657**: Check if webhook_context exists
- **Line 658**: Convert context to JSON
- **Line 660-668**: Create webhook section with formatted context
- **Line 670**: Combine base prompt + context
- **Line 671**: Log context keys

---

#### CHANGE 2: Update Assistant Class `__init__` Method

**Location**: Line 681 (function signature)

**Original**:
```python
def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None,
             chat_ctx=None, is_transferred: bool = False, background_audio=None) -> None:
```

**Updated** (Line 681):
```python
def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None,
             chat_ctx=None, is_transferred: bool = False, background_audio=None,
             webhook_context: dict = None) -> None:  # ⭐ ADD THIS PARAMETER
```

**In `__init__` body** - Lines 685-691:

**Original**:
```python
# Build full prompt: system instructions + user's custom prompt
full_prompt = build_full_prompt(config['prompt'])
```

**Updated**:
```python
# Build full prompt with optional webhook context
if webhook_context:  # ⭐ CHECK IF CONTEXT EXISTS
    full_prompt = build_prompt_with_webhook_context(config['prompt'], webhook_context)
    logger.info(f"✅ Assistant initialized WITH webhook context")
else:
    full_prompt = build_full_prompt(config['prompt'])
    logger.info(f"ℹ️ Assistant initialized WITHOUT webhook context")
```

**In `__init__` body** - Line 677 (add after line 676):

**Add this line**:
```python
self.webhook_context = webhook_context  # ⭐ STORE FOR REFERENCE
```

---

#### CHANGE 3: Initialize webhook_context in entrypoint

**Location**: Line 964 (start of entrypoint function)

**After line 961** (📊 Initial participants log), add:

```python
    # ===== WEBHOOK CONTEXT: Initialize for outbound API calls =====
    webhook_context = None  # ⭐ INITIALIZE HERE
```

---

#### CHANGE 4: Extract webhook_context from Participant Metadata

**Location**: Lines 1407-1420 (after participant joins)

**After line 1405** (`logger.info(f"✅ Participant joined...")`), add:

```python
        # ===== EXTRACT WEBHOOK CONTEXT from participant metadata =====
        if participant.metadata:  # ⭐ CHECK IF METADATA EXISTS
            try:
                logger.info(f"🔍 Checking participant metadata for webhook_context...")
                metadata = json.loads(participant.metadata)  # ⭐ PARSE JSON

                if metadata.get('type') == 'outbound_api':  # ⭐ CHECK TYPE
                    webhook_context = metadata.get('webhook_context')  # ⭐ EXTRACT
                    if webhook_context:
                        logger.info(f"✅ Webhook context found: {list(webhook_context.keys())}")
                    else:
                        logger.info(f"ℹ️ No webhook context in metadata")
            except Exception as e:
                logger.debug(f"Could not parse participant metadata: {e}")
```

**Key Points**:
- Line 1408: Check if metadata exists
- Line 1410: Parse JSON metadata
- Line 1413: Filter for `outbound_api` type only
- Line 1414: Extract webhook_context
- Line 1416: Log found keys

---

#### CHANGE 5: Pass webhook_context to Assistant

**Location**: Line 1426-1427 (session.start call)

**Original**:
```python
            agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools,
                            background_audio=background_audio),
```

**Updated**:
```python
            agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools,
                            background_audio=background_audio, webhook_context=webhook_context),  # ⭐ ADD THIS
```

---

## 📖 Server-Side Manual Implementation Guide

### Step 1: Copy Function to Your Agent Worker

**Copy this function** from lines 642-676 of `agent-server_api.py`:

```python
def build_prompt_with_webhook_context(user_prompt: str, webhook_context: dict) -> str:
    """Inject webhook data into prompt for pre-call context"""
    base_prompt = build_full_prompt(user_prompt)
    if webhook_context:
        webhook_text = json.dumps(webhook_context, ensure_ascii=False, indent=2)
        webhook_section = f"""

# 📊 بيانات العميل من النظام (Customer Data from System)
```json
{webhook_text}
```

Use this context to personalize the conversation. Address the customer by name if provided. Reference their order/case details naturally in conversation.
"""
        full_prompt = base_prompt + webhook_section
        logger.info(f"✅ Prompt built WITH webhook context: {list(webhook_context.keys())}")
        return full_prompt
    else:
        logger.info(f"ℹ️ Prompt built WITHOUT webhook context")
        return base_prompt
```

### Step 2: Update Assistant Class Constructor

**Locate** your Assistant class `__init__` method

**Add parameter** to function signature:
```python
def __init__(self, config, ..., webhook_context: dict = None):
```

**Replace prompt building logic** with:
```python
if webhook_context:
    full_prompt = build_prompt_with_webhook_context(config['prompt'], webhook_context)
    logger.info(f"✅ Assistant initialized WITH webhook context")
else:
    full_prompt = build_full_prompt(config['prompt'])
    logger.info(f"ℹ️ Assistant initialized WITHOUT webhook context")
```

**Add instance variable**:
```python
self.webhook_context = webhook_context
```

### Step 3: Initialize webhook_context in entrypoint

**In your entrypoint function**, at the beginning add:
```python
webhook_context = None
```

### Step 4: Extract from Participant Metadata

**After participant joins**, add:
```python
if participant.metadata:
    try:
        metadata = json.loads(participant.metadata)
        if metadata.get('type') == 'outbound_api':
            webhook_context = metadata.get('webhook_context')
            if webhook_context:
                logger.info(f"✅ Webhook context found: {list(webhook_context.keys())}")
    except Exception as e:
        logger.debug(f"Could not parse participant metadata: {e}")
```

### Step 5: Pass to Assistant Constructor

**When creating Assistant**, pass the webhook_context:
```python
Assistant(
    config=agent_config,
    agent_id=agent_id,
    webhook_context=webhook_context  # ⭐ ADD THIS
)
```

---

## 🧪 Testing

### Test Script Location
`scripts/test_webhook_context.py`

### Running Tests
```bash
python scripts/test_webhook_context.py
```

### What Gets Tested
1. ✅ API Health Check
2. ✅ List Agents
3. ✅ Call WITH webhook context
4. ✅ Call WITHOUT webhook context

### Expected Output
```
📊 TEST SUMMARY
✅ API Health: PASS
✅ List Agents: PASS
✅ Call with Context: PASS
✅ Call without Context: PASS

Total: 4 tests
Passed: 4
Success Rate: 100.0%
```

---

## 🏗️ Architecture Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT APPLICATION                        │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP POST /api/v1/calls/outbound
                       │ + context: { customer_name, order_id }
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                    FLASK API (api_v1.py)                     │
│  create_outbound_call()                                      │
│  - Extract context from request body                         │
│  - Pass to make_livekit_call(webhook_context=context)       │
└──────────────────────┬──────────────────────────────────────┘
                       │ Create SIP Participant
                       │ with metadata containing webhook_context
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                    LIVEKIT SERVER                            │
│  - Creates room                                              │
│  - Notifies agent worker about new job                      │
└──────────────────────┬──────────────────────────────────────┘
                       │ Job assignment
                       ↓
┌─────────────────────────────────────────────────────────────┐
│             AGENT WORKER (agent-server_api.py)              │
│  entrypoint()                                                │
│  1. Initialize webhook_context = None                       │
│  2. Agent pre-loads config                                  │
│  3. Wait for participant to join                            │
│  4. Extract metadata: webhook_context = metadata.get(...)   │
│  5. Create Assistant(webhook_context=webhook_context)       │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│             ASSISTANT INITIALIZATION                         │
│  __init__()                                                  │
│  if webhook_context:                                        │
│    prompt = build_prompt_with_webhook_context(...)          │
│  else:                                                       │
│    prompt = build_full_prompt(...)                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│             FINAL AGENT PROMPT                              │
│  [System Instructions]                                       │
│  [User's Custom Prompt]                                     │
│  # 📊 بيانات العميل من النظام                            │
│  {                                                           │
│    "customer_name": "زين",                                 │
│    "order_id": "ORD-2024-001",                             │
│    ...                                                       │
│  }                                                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓ Agent can now use context in responses
            "أهلاً زين! بخصوص طلبيتك ORD-2024-001..."
```

---

## 📝 Code Summary Table

| Component | File | Lines | Function | Purpose |
|-----------|------|-------|----------|---------|
| **API Layer** | `routes/api_v1.py` | 273 | `create_outbound_call()` | Extract context from request |
| **API Layer** | `routes/api_v1.py` | 289 | `make_livekit_call()` | Pass context to LiveKit metadata |
| **Prompt Builder** | `agent-server_api.py` | 642-676 | `build_prompt_with_webhook_context()` | Inject context into prompt |
| **Agent Init** | `agent-server_api.py` | 681 | `Assistant.__init__()` | Accept & store webhook_context |
| **Agent Init** | `agent-server_api.py` | 685-691 | `Assistant.__init__()` | Conditionally build prompt |
| **Entrypoint** | `agent-server_api.py` | 964 | `entrypoint()` | Initialize webhook_context |
| **Extract** | `agent-server_api.py` | 1407-1420 | `entrypoint()` | Extract from participant metadata |
| **Pass** | `agent-server_api.py` | 1427 | `session.start()` | Pass to Assistant constructor |

---

## ✅ Verification Checklist

After implementing, verify:

- [ ] `build_prompt_with_webhook_context()` function exists
- [ ] Assistant `__init__` accepts `webhook_context` parameter
- [ ] Webhook context is initialized in entrypoint
- [ ] Metadata extraction code is in place
- [ ] Assistant receives webhook_context when created
- [ ] Logs show `✅ Webhook context found:` when context is present
- [ ] Agent prompt includes customer data section
- [ ] Test script runs successfully
- [ ] API accepts context in request body
- [ ] Agent uses context in responses

---

## 🚀 Quick Copy-Paste Implementation

If you want to implement this in a new agent worker file:

1. **Copy the function** (lines 642-676 from agent-server_api.py)
2. **Update Assistant.__init__** with the 5 changes shown above
3. **Run test script** to validate
4. **Check logs** for "✅ Webhook context found:" message

---

## 📞 Support References

- **API Endpoint**: `POST /api/v1/calls/outbound`
- **Request Field**: `context` (optional dict)
- **Metadata Type**: `outbound_api`
- **Logs Pattern**: `✅ Webhook context found:`
- **Test File**: `scripts/test_webhook_context.py`

---

**Version**: 1.0
**Last Updated**: February 2026
**Status**: Production Ready ✅
