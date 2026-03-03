# Security Changes Documentation

## Summary
Security hardening implemented on 2026-01-22 to address session hijacking, XSS, clickjacking, and SSRF vulnerabilities.

---

## 1. Session Security Configuration

**File:** `app.py`
**Lines:** 40-58

### Changes Made:
```python
# Line 45
app.config['SESSION_COOKIE_SECURE'] = True

# Line 49
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Line 53
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Line 58
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)
```

### Why Each Setting:

| Setting | Purpose | Attack Prevented |
|---------|---------|------------------|
| `SESSION_COOKIE_SECURE = True` | Cookies only sent over HTTPS | Man-in-the-middle session hijacking |
| `SESSION_COOKIE_HTTPONLY = True` | JavaScript cannot access cookies | XSS stealing session via `document.cookie` |
| `SESSION_COOKIE_SAMESITE = 'Lax'` | Cookies not sent with cross-origin requests | CSRF attacks |
| `PERMANENT_SESSION_LIFETIME = 4h` | Sessions expire after 4 hours | Limits exposure if session compromised |

---

## 2. Security Headers Middleware

**File:** `app.py`
**Lines:** 110-146

### Changes Made:
```python
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'        # Line 122
    response.headers['X-Frame-Options'] = 'DENY'                  # Line 128
    response.headers['X-XSS-Protection'] = '1; mode=block'        # Line 133
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'  # Line 138
    response.headers['Content-Security-Policy'] = "frame-ancestors 'none';"  # Line 144
    return response
```

### Why Each Header:

| Header | Purpose | Attack Prevented |
|--------|---------|------------------|
| `X-Content-Type-Options: nosniff` | Prevents MIME-type sniffing | Malicious file execution disguised as safe type |
| `X-Frame-Options: DENY` | Blocks page embedding in iframes | Clickjacking attacks |
| `X-XSS-Protection: 1; mode=block` | Enables browser XSS filter | Reflected XSS in older browsers |
| `Referrer-Policy` | Controls referrer header | Prevents URL leakage to external sites |
| `Content-Security-Policy` | Controls resource loading | XSS, data injection |

---

## 3. SSRF Protection - Webhook URL Validation

**File:** `routes/workflows.py`
**Lines:** 17-57

### Changes Made:
```python
# Lines 17-57: New validation function
from urllib.parse import urlparse

ALLOWED_WEBHOOK_DOMAINS = {
    'workflows.nevoxai.com',
    'nevoxai.com',
}

def is_safe_webhook_url(url: str) -> tuple[bool, str]:
    # Validates HTTPS and allowed domains only
```

**Used in:**
- `create_workflow()` - Line 99
- `update_workflow()` - Line 166

### Why This Protection:

| Check | Purpose | Attack Prevented |
|-------|---------|------------------|
| Must use HTTPS | Encrypts webhook data in transit | MITM attacks capturing API keys |
| Domain whitelist | Only your servers receive webhooks | SSRF to internal services (localhost, AWS metadata) |

### SSRF Attack Examples Blocked:
- `http://169.254.169.254/latest/meta-data/` - AWS credential theft
- `http://localhost:5432` - Internal database probing
- `http://127.0.0.1:6379` - Redis access
- `http://internal-service.local/admin` - Internal service access

---

## 4. Frontend URL Validation (workflows.html)

**File:** `templates/workflows/workflows.html`
**Lines:** 73-87 (input field), 379-403 (JS validation)

### Changes Made:

**HTML - Added security notice and pattern validation:**
```html
<input type="url" id="workflowUrl" required
       placeholder="https://workflows.nevoxai.com/webhook/your-workflow"
       pattern="https://(workflows\.)?nevoxai\.com/.*">

<div class="mt-2 p-2 bg-amber-50 border border-amber-200 rounded-lg">
    <p class="text-xs text-amber-700">
        <strong>Security:</strong> Only URLs from workflows.nevoxai.com
        or nevoxai.com are accepted.
    </p>
</div>
```

**JavaScript - Client-side validation before submit:**
```javascript
function isValidWebhookUrl(url) {
    const parsed = new URL(url);
    const hostname = parsed.hostname.toLowerCase();

    // Must be HTTPS
    if (parsed.protocol !== 'https:') return false;

    // Must be from allowed domains
    const allowedDomains = ['workflows.nevoxai.com', 'nevoxai.com'];
    return allowedDomains.some(domain =>
        hostname === domain || hostname.endsWith('.' + domain)
    );
}
```

### Why Frontend Validation:

| Layer | Purpose |
|-------|---------|
| HTML `pattern` attribute | Basic browser validation before submit |
| JavaScript validation | Better error messages, prevents unnecessary API calls |
| Backend validation | **Primary security** - never trust frontend |

---

## Files Modified

| File | Lines Changed | Change Type |
|------|---------------|-------------|
| `app.py` | 40-58 | Session security config |
| `app.py` | 130-166 | Security headers middleware |
| `routes/workflows.py` | 17-57 | SSRF protection function |
| `routes/workflows.py` | 90-92 | Use validation in create |
| `routes/workflows.py` | 160-162 | Use validation in update |
| `templates/workflows/workflows.html` | 73-87 | URL input with security notice |
| `templates/workflows/workflows.html` | 379-403 | JS validation function |

---

## Testing Checklist

- [ ] Verify session cookies have Secure, HttpOnly, SameSite flags (browser DevTools > Application > Cookies)
- [ ] Verify security headers present (browser DevTools > Network > Response Headers)
- [ ] Test webhook creation with `http://` URL - should fail
- [ ] Test webhook creation with `https://evil.com` - should fail
- [ ] Test webhook creation with `https://workflows.nevoxai.com/webhook/test` - should succeed
- [ ] Verify sessions expire after 4 hours of inactivity

---

## Future Recommendations

1. **Add CSRF tokens** to all forms using Flask-WTF
2. **Implement account lockout** after 5 failed login attempts
3. **Add password complexity** requirements (min 8 chars, mixed case, numbers)
4. **Enable audit logging** for sensitive operations
5. **Move secrets** to environment variables or secrets manager
