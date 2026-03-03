# Token Usage Analysis and Cost Optimization

## Current Token Usage Pattern from Logs:

### Conversation Flow:
1. **First Response**: 143 input → 24 output (Initial greeting)
2. **Second Response**: 192 input (49 new) → 23 output  
3. **Third Response**: 248 input (56 new) → 70 output (Longer response)
4. **Fourth Response**: 365 input (117 new) → 17 output
5. **Fifth Response**: 446 input (126 new) → 34 output
6. **Sixth Response**: 502 input (54 new) → 19 output

## Cost Calculation (GPT-4o Realtime Pricing):

### Input Tokens:
- **Text Input**: $0.005 per 1K tokens
- **Audio Input**: $0.10 per 1K tokens
- **Cached Input**: $0.0025 per 1K tokens (50% discount)

### Output Tokens:
- **Text Output**: $0.02 per 1K tokens  
- **Audio Output**: $0.20 per 1K tokens

### Your Session Cost Estimate:
```
Total Input Tokens: 502
- Fresh tokens: 54 (502-448) = $0.00027
- Cached tokens: 448 = $0.00112
Total Output Tokens: 187 (24+23+70+17+34+19) = $0.00374

Estimated cost per conversation: ~$0.005 (Half a cent)
```

## For 100+ Users Daily:

### Conservative Estimate:
- 100 users × 2 calls/day × $0.005 = **$1/day** = **$365/year**
- 500 users × 2 calls/day × $0.005 = **$5/day** = **$1,825/year**

### Peak Usage:
- 1000 users × 5 calls/day × $0.01 = **$50/day** = **$18,250/year**

## Cost Optimization Strategies:

### 1. Context Management
```python
# Limit conversation history to reduce input tokens
max_context_messages = 10  # Keep only last 10 exchanges
max_context_tokens = 1000  # Or limit by token count
```

### 2. Caching Strategy
```python
# Your system already benefits from cached tokens!
# 448/502 = 89% cache hit rate - Excellent!
```

### 3. Response Length Control
```python
instructions = """
أجب بإجابات قصيرة ومباشرة (10-30 كلمة فقط).
تجنب الإجابات الطويلة إلا إذا طلب المستخدم ذلك.
"""
```

### 4. Token Monitoring
```python
class TokenMonitor:
    def __init__(self):
        self.daily_tokens = {"input": 0, "output": 0}
        self.user_limits = {"free": 10000, "paid": 100000}
    
    def track_usage(self, user_id, input_tokens, output_tokens):
        # Track per-user token usage
        # Implement limits and alerts
        pass
```

## Production Token Management:

### Database Schema Addition:
```sql
ALTER TABLE call_logs ADD COLUMN input_tokens INTEGER DEFAULT 0;
ALTER TABLE call_logs ADD COLUMN output_tokens INTEGER DEFAULT 0;
ALTER TABLE call_logs ADD COLUMN cached_tokens INTEGER DEFAULT 0;
ALTER TABLE call_logs ADD COLUMN token_cost DECIMAL(10,6) DEFAULT 0.0;

ALTER TABLE users ADD COLUMN monthly_token_limit INTEGER DEFAULT 50000;
ALTER TABLE users ADD COLUMN current_month_tokens INTEGER DEFAULT 0;
```

### Real-time Monitoring:
```python
@session.on("metrics_collected")
def track_token_usage(ev: MetricsCollectedEvent):
    if hasattr(ev.metrics, 'input_tokens'):
        # Update user's token count
        # Check if approaching limits
        # Send alerts if needed
        pass
```