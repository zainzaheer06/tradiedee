# ⚡ Webhook Context - Quick Reference Checklist

## 5 Changes to Implement in `agent-server_api.py`

---

## ✅ CHANGE 1: Add Prompt Builder Function

**WHERE**: After `build_full_prompt()` function (Line 642)

**WHAT TO ADD**:
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

Use this context to personalize the conversation.
"""
        full_prompt = base_prompt + webhook_section
        logger.info(f"✅ Prompt built WITH webhook context: {list(webhook_context.keys())}")
        return full_prompt
    else:
        logger.info(f"ℹ️ Prompt built WITHOUT webhook context")
        return base_prompt
```

**KEY LINES**:
- Line 658: JSON encode context
- Line 670: Combine prompts
- Line 671: Log keys

---

## ✅ CHANGE 2: Update Assistant `__init__` Signature

**WHERE**: Line 681 (class Assistant function signature)

**CHANGE THIS**:
```python
def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None,
             chat_ctx=None, is_transferred: bool = False, background_audio=None) -> None:
```

**TO THIS**:
```python
def __init__(self, config: dict = None, agent_id: int = None, preloaded_tools: list = None,
             chat_ctx=None, is_transferred: bool = False, background_audio=None,
             webhook_context: dict = None) -> None:  # ⭐ ADD THIS
```

---

## ✅ CHANGE 3: Update Prompt Building Logic

**WHERE**: Line 648-649 in `__init__` body

**CHANGE THIS**:
```python
# Build full prompt: system instructions + user's custom prompt
full_prompt = build_full_prompt(config['prompt'])
```

**TO THIS**:
```python
# Build full prompt with optional webhook context
if webhook_context:
    full_prompt = build_prompt_with_webhook_context(config['prompt'], webhook_context)
    logger.info(f"✅ Assistant initialized WITH webhook context")
else:
    full_prompt = build_full_prompt(config['prompt'])
    logger.info(f"ℹ️ Assistant initialized WITHOUT webhook context")
```

**AND ADD** (after line 676):
```python
self.webhook_context = webhook_context
```

---

## ✅ CHANGE 4: Initialize webhook_context in entrypoint

**WHERE**: Line 964 (start of entrypoint function, after logging "Initial participants")

**ADD THIS LINE**:
```python
webhook_context = None
```

---

## ✅ CHANGE 5: Extract & Pass webhook_context

**PART A - EXTRACT**: After line 1405 (after participant joins)

**ADD THIS**:
```python
# ===== EXTRACT WEBHOOK CONTEXT from participant metadata =====
if participant.metadata:
    try:
        logger.info(f"🔍 Checking participant metadata for webhook_context...")
        metadata = json.loads(participant.metadata)
        if metadata.get('type') == 'outbound_api':
            webhook_context = metadata.get('webhook_context')
            if webhook_context:
                logger.info(f"✅ Webhook context found: {list(webhook_context.keys())}")
            else:
                logger.info(f"ℹ️ No webhook context in metadata")
    except Exception as e:
        logger.debug(f"Could not parse participant metadata: {e}")
```

**PART B - PASS**: Line 1426-1427 (in session.start call)

**CHANGE THIS**:
```python
agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools,
                background_audio=background_audio),
```

**TO THIS**:
```python
agent=Assistant(config=agent_config, agent_id=agent_id, preloaded_tools=dynamic_tools,
                background_audio=background_audio, webhook_context=webhook_context),  # ⭐ ADD THIS
```

---

## 🎯 Line-by-Line Reference

| Change | File | Before Line | New Lines | Action |
|--------|------|-------------|-----------|--------|
| **1** | agent-server_api.py | 639 | 642-676 | ADD function |
| **2** | agent-server_api.py | 681 | 681 | UPDATE signature |
| **3** | agent-server_api.py | 648-649 | 685-691 | REPLACE logic |
| **3b** | agent-server_api.py | 676 | 677 | ADD variable |
| **4** | agent-server_api.py | 961 | 964 | ADD initialization |
| **5a** | agent-server_api.py | 1405 | 1407-1420 | ADD extraction |
| **5b** | agent-server_api.py | 1426-1427 | 1427 | UPDATE call |

---

## 🧪 Verification Commands

After implementing, run these to verify:

```bash
# Check function exists
grep -n "def build_prompt_with_webhook_context" agent-server_api.py

# Check parameter added
grep -n "webhook_context: dict = None" agent-server_api.py

# Check initialization
grep -n "webhook_context = None" agent-server_api.py

# Check extraction
grep -n "EXTRACT WEBHOOK CONTEXT" agent-server_api.py

# Check passing
grep -n "webhook_context=webhook_context" agent-server_api.py
```

---

## 📊 Expected Log Output

When webhook context is working:

```
✅ Webhook context found: ['customer_name', 'order_id', 'service_type', ...]
✅ Prompt built WITH webhook context: ['customer_name', 'order_id', ...]
✅ Assistant initialized WITH webhook context
```

---

## ❌ Common Mistakes

| Mistake | Impact | Fix |
|---------|--------|-----|
| Forget `webhook_context: dict = None` parameter | TypeError on Assistant init | Add to line 681 |
| Don't extract from metadata | Context is always None | Add extraction code at 1407 |
| Forget to pass to Assistant | Context never reaches agent | Add to line 1427 |
| Check wrong metadata type | Context never extracted | Verify checking for 'outbound_api' |
| JSON dump fails silently | Context doesn't appear in prompt | Ensure `ensure_ascii=False` |

---

## 🔍 Debug Tips

**If context not showing in logs:**
1. Check API receives context: `print(f"Context: {data.get('context')}")`
2. Check metadata has context: `print(f"Metadata: {metadata}")`
3. Check extraction works: Look for "Checking participant metadata" log
4. Check type matches: Ensure `"type": "outbound_api"` in metadata

**If logs show no context:**
1. API might not be sending it - test with `test_webhook_context.py`
2. Metadata parsing might fail - add debug logging
3. Type mismatch - check if `type` field is `"outbound_api"`

---

## 📋 Copy-Paste Template

For new implementations, use this template:

```python
# 1. Add after line 639
def build_prompt_with_webhook_context(user_prompt: str, webhook_context: dict) -> str:
    # ... [see Change 1 above]

# 2. Update line 681 signature
def __init__(self, ..., webhook_context: dict = None) -> None:

# 3. Replace lines 648-649
if webhook_context:
    # ... [see Change 3 above]

# 4. Add line 964
webhook_context = None

# 5a. Add after line 1405
if participant.metadata:
    # ... [see Change 5a above]

# 5b. Update line 1427
agent=Assistant(..., webhook_context=webhook_context),
```

---

## ✨ Final Checklist

- [ ] Function `build_prompt_with_webhook_context()` added
- [ ] Parameter `webhook_context: dict = None` in `__init__`
- [ ] Conditional prompt building logic updated
- [ ] `self.webhook_context = webhook_context` added
- [ ] `webhook_context = None` initialized in entrypoint
- [ ] Metadata extraction code added
- [ ] Webhook_context passed to Assistant
- [ ] Test script runs without errors
- [ ] Logs show context extraction messages
- [ ] Agent includes context in responses

---

**Status**: Ready for Production ✅
**Files to Update**: 1 file (`agent-server_api.py`)
**Total Changes**: 5 logical changes (7 specific locations)
**Time to Implement**: ~15 minutes
**Testing Time**: ~5 minutes

