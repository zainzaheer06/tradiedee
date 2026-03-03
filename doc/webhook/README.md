# 🎯 Webhook Context Documentation

Complete guide for implementing and understanding webhook context functionality in the NevoxAI agent system.

## 📚 Documentation Structure

### 1. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** ⚡ START HERE
   - Quick 5-step implementation checklist
   - Copy-paste code snippets
   - Common mistakes and debugging tips
   - **Best for**: Developers who want fast implementation
   - **Time**: ~15 minutes to implement

### 2. **[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)** 📖 COMPREHENSIVE
   - Detailed explanation of all changes
   - Full code walkthrough
   - Architecture flow diagrams
   - Testing instructions
   - **Best for**: Complete understanding of the feature
   - **Time**: ~30 minutes to read

### 3. **[CALL_FLOW_DIAGRAM.md](CALL_FLOW_DIAGRAM.md)** 📞 VISUAL
   - End-to-end call flow ASCII diagram
   - Phase-by-phase breakdown
   - Extraction points explained
   - Failure scenarios and logs
   - **Best for**: Understanding data flow
   - **Time**: ~10 minutes to review

---

## 🎯 Quick Start

### For New Developers
1. Read: [QUICK_REFERENCE.md](QUICK_REFERENCE.md) (5 min)
2. Copy: Code snippets from Section 1-5
3. Test: Run `test_webhook_context.py`
4. Verify: Check logs for "✅ Webhook context found:"

### For Integration
1. Review: [CALL_FLOW_DIAGRAM.md](CALL_FLOW_DIAGRAM.md) (10 min)
2. Understand: Data flow from API to Agent
3. Check: Extraction points in your code
4. Implement: Using [QUICK_REFERENCE.md](QUICK_REFERENCE.md)

### For Complete Understanding
1. Study: [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) (30 min)
2. Review: Architecture flow section
3. Understand: Each of the 5 changes in detail
4. Reference: Code summary table

---

## 🚀 What is Webhook Context?

**Webhook Context** allows you to pass customer data through the API to AI agents for personalized conversations.

### Simple Example

**API Request:**
```json
{
  "agent_id": 74,
  "phone_number": "+966501234567",
  "context": {
    "customer_name": "زين",
    "order_id": "ORD-2024-001"
  }
}
```

**Agent Response:**
```
أهلاً زين! 👋
شكراً لك على اتصالك
بخصوص طلبيتك ORD-2024-001...
```

---

## 📋 The 5 Changes Summary

| # | What | Where | Status |
|---|------|-------|--------|
| 1 | Add prompt builder function | `agent-server_api.py` line 642 | ✅ Done |
| 2 | Update `__init__` signature | `agent-server_api.py` line 681 | ✅ Done |
| 3 | Update prompt building logic | `agent-server_api.py` line 685-691 | ✅ Done |
| 4 | Initialize webhook_context | `agent-server_api.py` line 964 | ✅ Done |
| 5 | Extract & pass webhook_context | `agent-server_api.py` line 1407-1427 | ✅ Done |

---

## 🧪 Testing

### Run Tests
```bash
python scripts/test_webhook_context.py
```

### Expected Output
```
✅ API Health: PASS
✅ Call with Context: PASS
✅ Call without Context: PASS

Total: 3 tests
Passed: 3
Success Rate: 100.0%
```

### Verify Implementation
```bash
# Check all changes are in place
grep -n "def build_prompt_with_webhook_context" agent-server_api.py
grep -n "webhook_context: dict = None" agent-server_api.py
grep -n "EXTRACT WEBHOOK CONTEXT" agent-server_api.py
grep -n "webhook_context=webhook_context" agent-server_api.py
```

---

## 🔍 How It Works

```
CLIENT REQUEST
     ↓
  (API Request with context)
     ↓
API LAYER (routes/api_v1.py)
     ↓
  (Extract context, build metadata)
     ↓
LIVEKIT SERVER
     ↓
  (Store metadata in room)
     ↓
AGENT WORKER (agent-server_api.py)
     ↓
  (Extract metadata, build prompt with context)
     ↓
ASSISTANT INITIALIZATION
     ↓
  (Use context in responses)
     ↓
PERSONALIZED RESPONSE
```

For detailed flow, see [CALL_FLOW_DIAGRAM.md](CALL_FLOW_DIAGRAM.md)

---

## 📍 Key Files

### Modified Files
- **`agent-server_api.py`** - Agent worker (5 changes applied)
- **`routes/api_v1.py`** - REST API (already supports webhook context)

### Test & Documentation Files
- **`scripts/test_webhook_context.py`** - Test script
- **`doc/webhook/`** - This documentation folder

---

## ✅ Implementation Checklist

Before considering implementation complete:

- [ ] Read QUICK_REFERENCE.md
- [ ] Add `build_prompt_with_webhook_context()` function
- [ ] Update `Assistant.__init__()` signature with `webhook_context` parameter
- [ ] Update prompt building logic with conditional check
- [ ] Initialize `webhook_context = None` in entrypoint
- [ ] Add metadata extraction code after participant joins
- [ ] Pass `webhook_context` to Assistant constructor
- [ ] Run test script successfully
- [ ] Verify logs show "✅ Webhook context found:"
- [ ] Test with API request containing context

---

## 🐛 Troubleshooting

### Context Not Appearing in Logs
1. **Check API sends context**: Verify API request includes `context` field
2. **Check metadata parsing**: Look for metadata in participant object
3. **Check extraction code**: Verify "Checking participant metadata" log appears
4. **Check type matches**: Ensure `metadata.get('type') == 'outbound_api'`

### Agent Not Using Context
1. **Check logs** for "✅ Webhook context found:" message
2. **Check prompt** in logs for context injection
3. **Check parameter**: Verify `webhook_context=webhook_context` passed to Assistant
4. **Check function**: Verify `build_prompt_with_webhook_context()` exists

### TypeError in Assistant Init
1. **Error**: `TypeError: __init__() got unexpected keyword argument 'webhook_context'`
2. **Fix**: Ensure line 681 has `webhook_context: dict = None` parameter added

---

## 📞 Support

### Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| Context is None | API not sending it | Check API request body has `context` field |
| Logs show no extraction | Metadata parsing fails | Add debug logging to metadata extraction |
| Agent not using context | Parameter not passed | Verify line 1427 includes `webhook_context=webhook_context` |
| TypeError on init | Missing parameter | Add `webhook_context: dict = None` to line 681 |

### Debug Tips

```python
# Check if context reached agent worker
if webhook_context:
    logger.debug(f"Context keys: {list(webhook_context.keys())}")
    logger.debug(f"Context data: {webhook_context}")

# Check if metadata exists
if participant.metadata:
    logger.debug(f"Metadata type: {metadata.get('type')}")
    logger.debug(f"Metadata keys: {metadata.keys()}")
```

---

## 📊 Architecture Overview

### API Layer
- **Endpoint**: `POST /api/v1/calls/outbound`
- **Accepts**: `context` field in request body
- **Passes**: `webhook_context` to LiveKit metadata

### Agent Worker
- **Receives**: Metadata from LiveKit job assignment
- **Extracts**: `webhook_context` from participant metadata
- **Uses**: Context to build personalized prompt
- **Result**: Agent can reference customer data in responses

### Agent (Claude)
- **Input**: Prompt with injected context data
- **Processing**: Understands context from prompt
- **Output**: Personalized, context-aware responses

---

## 🎓 Learning Path

1. **Beginner**: Start with [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
   - Learn the 5 changes needed
   - Understand what each part does

2. **Intermediate**: Read [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)
   - Understand the complete architecture
   - See how data flows through system

3. **Advanced**: Study [CALL_FLOW_DIAGRAM.md](CALL_FLOW_DIAGRAM.md)
   - Master the detailed flow
   - Understand error scenarios
   - Learn verification strategies

---

## 📝 Version Information

- **Implementation Date**: February 2026
- **Status**: Production Ready ✅
- **Files Modified**: 1 (`agent-server_api.py`)
- **Total Changes**: 5 logical changes (7 specific locations)
- **Implementation Time**: ~15 minutes
- **Testing Time**: ~5 minutes

---

## 🔗 Related Resources

- **Test Script**: `../../scripts/test_webhook_context.py`
- **API File**: `../../routes/api_v1.py`
- **Agent Worker**: `../../agent-server_api.py`
- **Project Root**: `../../`

---

**Last Updated**: February 2026
**Maintainer**: Development Team
**Status**: Complete & Tested ✅
