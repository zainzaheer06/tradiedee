# 📞 Webhook Context - Call Flow Diagram

## Complete End-to-End Flow

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                          WEBHOOK CONTEXT FLOW                                ║
║                     From API Request to Agent Response                        ║
╚══════════════════════════════════════════════════════════════════════════════╝


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PHASE 1: CLIENT REQUEST                                                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

                      CLIENT APPLICATION
                            │
                            │ POST /api/v1/calls/outbound
                            │
                            ├─ agent_id: 74
                            ├─ phone_number: "923354646825"
                            └─ context: {
                                  "customer_name": "زين",
                                  "order_id": "ORD-2024-001",
                                  "service_type": "Internet",
                                  "status": "Active",
                                  "payment_status": "Pending"
                               }
                            │
                            ▼


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PHASE 2: API LAYER (routes/api_v1.py)                                       ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

        ┌─────────────────────────────────────┐
        │  create_outbound_call()             │
        │  ✓ Validates API Key                │
        │  ✓ Formats phone number             │
        │  ✓ Creates room name                │
        └─────────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
    Line 273:                      Line 289:
    Extract context            Pass context
                                    │
        ├─ context = data.get(     │
        │    'context', {})         │
        │                           │
        └─ webhook_context =────────┤
           context if context else   │
           None                      │
                                    │
                                    ▼
        ┌─────────────────────────────────────┐
        │  make_livekit_call()                │
        │  ✓ Creates LiveKit API instance    │
        │  ✓ Builds room_metadata dict       │
        │  ✓ Prepares SIP participant        │
        └─────────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
    Line 155-160:                   Line 166:
    room_metadata = {           JSON serialize
        "type": "outbound_api", metadata
        "agent_id": 74,
        "phone_number": "...",
        "webhook_context": {
            "customer_name": "زين",
            ...
        }
    }
                                    │
                                    ▼
        ┌─────────────────────────────────────┐
        │ create_sip_participant_request()    │
        │ ✓ Set room_name                    │
        │ ✓ Set sip_trunk_id                 │
        │ ✓ Set sip_call_to (phone)         │
        │ ✓ Set participant_metadata         │
        │   (JSON with webhook context)      │
        └─────────────────────────────────────┘
                        │
                        ▼


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PHASE 3: LIVEKIT SERVER (Infrastructure)                                    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

        ┌─────────────────────────────────────┐
        │  LiveKit Server                     │
        │  ✓ Creates room                    │
        │  ✓ Stores metadata                 │
        │  ✓ Creates SIP participant         │
        │  ✓ Initiates phone call            │
        │  ✓ Notifies agent worker           │
        │    about new job                   │
        └─────────────────────────────────────┘
                        │
                        │ Job Assignment
                        │ (Room + Metadata)
                        ▼


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PHASE 4: AGENT WORKER INITIALIZATION (agent-server_api.py)                 ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

        ┌─────────────────────────────────────┐
        │  entrypoint()                       │
        │  ✓ Accepts job request              │
        │  ✓ Initializes variables            │
        │  ✓ Loads agent config               │
        │  ✓ Waits for participants           │
        └─────────────────────────────────────┘
                        │
        Line 964:       │
        webhook_context = None  ◄──── INITIALIZE
                        │
        ┌───────────────┴───────────────┐
        │                               │
    Line 961:                    Line 1400s:
    Log initial                Wait for
    participants              participant join
        │                           │
        │                           ▼
        │              ┌──────────────────────┐
        │              │ Participant Joins    │
        │              │ (Phone caller + SIP) │
        │              │ ✓ participant.name   │
        │              │ ✓ participant.kind   │
        │              │ ✓ participant.metadata ◄── THIS IS KEY
        │              └──────────────────────┘
        │                           │
        │                           ▼
        │              ┌──────────────────────────────────────┐
        │              │ Line 1407-1420:                      │
        │              │ EXTRACT WEBHOOK CONTEXT              │
        │              │                                      │
        │              │ Step 1: Check if metadata exists    │
        │              │ if participant.metadata:            │
        │              │                                      │
        │              │ Step 2: Parse JSON metadata         │
        │              │ metadata = json.loads(              │
        │              │    participant.metadata)            │
        │              │                                      │
        │              │ Step 3: Check type is outbound_api  │
        │              │ if metadata.get('type') ==          │
        │              │    'outbound_api':                  │
        │              │                                      │
        │              │ Step 4: Extract webhook_context     │
        │              │ webhook_context =                   │
        │              │    metadata.get(                    │
        │              │    'webhook_context')               │
        │              │                                      │
        │              │ Step 5: Log success                 │
        │              │ logger.info(                        │
        │              │ f"✅ Webhook context found:         │
        │              │ {list(webhook_context.keys())}")    │
        │              └──────────────────────────────────────┘
        │                           │
        │                           │ webhook_context now contains:
        │                           │ {
        │                           │   "customer_name": "زين",
        │                           │   "order_id": "ORD-2024-001",
        │                           │   "service_type": "Internet",
        │                           │   "status": "Active",
        │                           │   "payment_status": "Pending"
        │                           │ }
        │                           │
        └───────────────┬───────────┘
                        │
                        ▼
        ┌──────────────────────────────────────┐
        │ Load Agent Configuration              │
        │ ✓ agent_config = await               │
        │   get_agent_config(agent_id)         │
        └──────────────────────────────────────┘
                        │
                        ▼


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PHASE 5: ASSISTANT INITIALIZATION (agent-server_api.py)                    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

        Line 1427:
        ┌──────────────────────────────────────┐
        │ session.start(                       │
        │   agent=Assistant(                   │
        │     config=agent_config,             │
        │     agent_id=agent_id,               │
        │     preloaded_tools=dynamic_tools,   │
        │     background_audio=...,            │
        │     webhook_context=webhook_context  ◄── PASS HERE
        │   )                                  │
        │ )                                    │
        └──────────────────────────────────────┘
                        │
                        ▼
        ┌──────────────────────────────────────┐
        │ Assistant.__init__()                 │
        │ (Line 681 signature)                 │
        │                                      │
        │ Accepts all parameters:              │
        │ - config                             │
        │ - agent_id                           │
        │ - preloaded_tools                    │
        │ - chat_ctx                           │
        │ - is_transferred                     │
        │ - background_audio                   │
        │ - webhook_context ◄── NEW PARAMETER │
        └──────────────────────────────────────┘
                        │
                        ▼
        ┌──────────────────────────────────────┐
        │ Line 685-691:                        │
        │ CONDITIONAL PROMPT BUILDING          │
        │                                      │
        │ if webhook_context:                 │
        │    full_prompt =                     │
        │    build_prompt_with_webhook_context(
        │      config['prompt'],               │
        │      webhook_context                 │
        │    )                                 │
        │    logger.info(                      │
        │    "✅ Assistant initialized         │
        │     WITH webhook context")           │
        │ else:                                │
        │    full_prompt =                     │
        │    build_full_prompt(                │
        │      config['prompt']                │
        │    )                                 │
        │    logger.info(                      │
        │    "ℹ️ Assistant initialized         │
        │     WITHOUT webhook context")        │
        └──────────────────────────────────────┘
                        │
                        ▼


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PHASE 6: PROMPT INJECTION (agent-server_api.py)                            ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

        Line 642-676:
        ┌──────────────────────────────────────────┐
        │ build_prompt_with_webhook_context()      │
        │                                          │
        │ Step 1: Get base prompt                 │
        │ base_prompt = build_full_prompt(        │
        │   user_prompt)                          │
        │                                          │
        │ Step 2: Convert context to JSON         │
        │ webhook_text = json.dumps(              │
        │   webhook_context,                      │
        │   ensure_ascii=False,  ◄── ARABIC!      │
        │   indent=2)                             │
        │                                          │
        │ Step 3: Create context section          │
        │ webhook_section = """                   │
        │                                          │
        │ # 📊 بيانات العميل من النظام           │
        │ # (Customer Data from System)           │
        │ ```json                                 │
        │ {webhook_text}                          │
        │ ```                                     │
        │                                          │
        │ Use this context to personalize         │
        │ the conversation. Address the           │
        │ customer by name...                     │
        │ """                                     │
        │                                          │
        │ Step 4: Combine prompts                 │
        │ full_prompt = base_prompt +             │
        │   webhook_section                      │
        │                                          │
        │ Step 5: Log injection                   │
        │ logger.info(                            │
        │ f"✅ Prompt built WITH                   │
        │ webhook context:                        │
        │ {list(webhook_context.keys())}")        │
        │                                          │
        │ return full_prompt                      │
        └──────────────────────────────────────────┘
                        │
                        ▼
        ┌──────────────────────────────────────────┐
        │ FINAL AGENT PROMPT STRUCTURE             │
        │                                          │
        │ [SYSTEM INSTRUCTIONS]                   │
        │ You are a helpful AI assistant...       │
        │ You speak Arabic...                     │
        │ Your role is to help customers...      │
        │                                          │
        │ [USER'S CUSTOM PROMPT]                  │
        │ You are a customer service agent...    │
        │ Help with order inquiries...            │
        │                                          │
        │ [WEBHOOK CONTEXT SECTION] ◄── NEW      │
        │ # 📊 بيانات العميل من النظام           │
        │ ```json                                 │
        │ {                                       │
        │   "customer_name": "زين",              │
        │   "order_id": "ORD-2024-001",          │
        │   "service_type": "Internet",          │
        │   "status": "Active",                  │
        │   "payment_status": "Pending"          │
        │ }                                       │
        │ ```                                     │
        │                                          │
        │ Use this context to personalize         │
        │ the conversation...                     │
        └──────────────────────────────────────────┘
                        │
                        ▼


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PHASE 7: AGENT RESPONSE                                                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

        ┌──────────────────────────────────────┐
        │ Agent Receives Call                   │
        │                                      │
        │ Phone rings...                       │
        │ Agent hears: "السلام عليكم"          │
        │ (As-salamu alaikum)                  │
        └──────────────────────────────────────┘
                        │
                        ▼
        ┌──────────────────────────────────────┐
        │ Agent Uses Context                   │
        │                                      │
        │ "أهلاً زين! 👋                       │
        │  شكراً لك على اتصالك                │
        │  أنا هنا لمساعدتك بخصوص              │
        │  طلبيتك ORD-2024-001                │
        │  الخدمة: Internet                    │
        │  الحالة: نشطة ✓                      │
        │  هل هناك مشكلة في الدفع؟"           │
        │                                      │
        │ (Personalized, context-aware         │
        │  response in Arabic!)                │
        └──────────────────────────────────────┘
                        │
                        ▼
        ┌──────────────────────────────────────┐
        │ Conversation Continues                │
        │ with Context References               │
        │                                      │
        │ Customer benefits from:               │
        │ - Instant recognition (name)         │
        │ - No repeated questions              │
        │ - Faster resolution                  │
        │ - Better experience ✨               │
        └──────────────────────────────────────┘


╔══════════════════════════════════════════════════════════════════════════════╗
║                          KEY EXTRACTION POINTS                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────────────┐
│ EXTRACTION POINT 1: API REQUEST BODY                                        │
│ ───────────────────────────────────────────────────────────────────────────  │
│ Where: routes/api_v1.py, Line 273                                           │
│ What: Extract context from POST body                                        │
│ How:  context = data.get('context', {})                                    │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ EXTRACTION POINT 2: LIVEKIT METADATA                                        │
│ ───────────────────────────────────────────────────────────────────────────  │
│ Where: agent-server_api.py, Line 1410                                       │
│ What: Parse JSON metadata from participant                                  │
│ How:  metadata = json.loads(participant.metadata)                          │
│ Data: room_metadata from LiveKit containing webhook_context                │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ EXTRACTION POINT 3: WEBHOOK CONTEXT OBJECT                                  │
│ ───────────────────────────────────────────────────────────────────────────  │
│ Where: agent-server_api.py, Line 1413-1414                                  │
│ What: Extract webhook_context from metadata                                 │
│ How:  webhook_context = metadata.get('webhook_context')                    │
│ Type: dict with customer data                                               │
└──────────────────────────────────────────────────────────────────────────────┘


╔══════════════════════════════════════════════════════════════════════════════╗
║                          FAILURE SCENARIOS                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

❌ Scenario 1: No context in API request
   ├─ API extracts empty context: {}
   ├─ Lives off to make_livekit_call(webhook_context=None)
   ├─ Agent Worker receives None
   ├─ Assistant uses build_full_prompt() (no context)
   └─ Agent responds normally without personalization

❌ Scenario 2: Metadata parsing fails
   ├─ participant.metadata exists but invalid JSON
   ├─ try-except catches error
   ├─ logger.debug logs the error
   ├─ webhook_context remains None
   └─ Agent continues without context (graceful fallback)

❌ Scenario 3: Wrong metadata type
   ├─ metadata.get('type') != 'outbound_api'
   ├─ Type check fails
   ├─ webhook_context not extracted
   └─ Agent responds normally

❌ Scenario 4: Assistant parameter missing
   ├─ Line 1427 doesn't pass webhook_context parameter
   ├─ TypeError: Assistant() got unexpected keyword argument
   ├─ Job fails
   └─ ERROR: Must add webhook_context parameter to __init__


╔══════════════════════════════════════════════════════════════════════════════╗
║                          VERIFICATION LOGS                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

When working correctly, you should see these logs:

✅ SUCCESS LOGS:
   [HH:MM:SS] [INFO] 🔍 Checking participant metadata for webhook_context...
   [HH:MM:SS] [INFO] ✅ Webhook context found: ['customer_name', 'order_id', 'service_type', 'status', 'payment_status']
   [HH:MM:SS] [INFO] ✅ Prompt built WITH webhook context: ['customer_name', 'order_id', ...]
   [HH:MM:SS] [INFO] ✅ Assistant initialized WITH webhook context

⚠️  NO CONTEXT LOGS (Still OK):
   [HH:MM:SS] [INFO] 🔍 Checking participant metadata for webhook_context...
   [HH:MM:SS] [INFO] ℹ️ No webhook context in metadata
   [HH:MM:SS] [INFO] ℹ️ Prompt built WITHOUT webhook context
   [HH:MM:SS] [INFO] ℹ️ Assistant initialized WITHOUT webhook context

❌ ERROR LOGS (Fix These):
   [HH:MM:SS] [ERROR] Could not parse participant metadata: ...
   [HH:MM:SS] [ERROR] TypeError: Assistant() got unexpected keyword argument 'webhook_context'
   [HH:MM:SS] [ERROR] AttributeError: 'NoneType' object is not subscriptable (context issue)
```

---

## Quick Navigation

- **📖 Full Implementation Guide**: [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)
- **⚡ Quick Reference**: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
- **🧪 Test Script**: `../../scripts/test_webhook_context.py`
- **🔧 API File**: `../../routes/api_v1.py`
- **🤖 Agent Worker File**: `../../agent-server_api.py`
