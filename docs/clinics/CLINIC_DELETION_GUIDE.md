# Clinic Platform - Complete Deletion Guide

**Last Updated:** February 25, 2026
**Document Version:** 1.0
**Status:** Complete Removal Instructions

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Backup & Restore](#backup--restore)
4. [Deletion Steps](#deletion-steps)
5. [Verification Checklist](#verification-checklist)
6. [Troubleshooting](#troubleshooting)
7. [After Deletion](#after-deletion)
8. [FAQ](#faq)

---

## Overview

This guide provides complete instructions to **permanently remove** all clinic platform features from Nevox AI.

### What Gets Deleted

✓ All clinic routes and API endpoints
✓ All clinic HTML templates
✓ Clinic service layer
✓ Database clinic columns
✓ All clinic workflows and campaigns
✓ Clinic sidebar navigation
✓ Clinic documentation

### What Stays Intact

✓ All agents, campaigns, and workflows (non-clinic)
✓ User accounts and authentication
✓ Original Nevox platform features
✓ Database structure (except clinic columns)

### Time Required

- **Full deletion**: 10-15 minutes
- **Verification**: 5 minutes
- **Total**: ~20 minutes

---

## Prerequisites

Before deletion, ensure:

- [ ] You have a database backup
- [ ] Flask server is running or will be restarted
- [ ] You have terminal/bash access
- [ ] You're in the project root directory
- [ ] No active clinic feature configurations are critical

**Current Location:**
```
c:\Users\mzain\Python-projects\Commercial\nevoxai_server\nevoxai-project\
```

---

## Backup & Restore

### Create a Backup (RECOMMENDED)

**Before you delete anything, create a backup:**

```bash
# Backup database
cp c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/instance/nevox.db \
   c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/instance/nevox.db.backup.$(date +%Y%m%d-%H%M%S)

# Backup entire project
tar -czf ~/nevox-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
    c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/

echo "Backup complete!"
```

### Restore from Backup

**If you need to restore:**

```bash
# Restore database
cp c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/instance/nevox.db.backup \
   c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/instance/nevox.db

# Restore entire project
tar -xzf ~/nevox-backup-YYYYMMDD-HHMMSS.tar.gz -C /

echo "Restore complete! Restart Flask."
```

---

## Deletion Steps

### Step 1: Stop Flask Server

```bash
# Kill Flask process
pkill -f "python app.py" || echo "Flask not running"

# Wait for process to stop
sleep 2

echo "Flask server stopped"
```

### Step 2: Delete Clinic Routes File

```bash
# Delete clinic routes
rm -f c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/routes/clinic.py

# Verify deletion
if [ ! -f c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/routes/clinic.py ]; then
    echo "[OK] clinic.py deleted"
else
    echo "[ERROR] Failed to delete clinic.py"
fi
```

**Files Deleted:**
- `routes/clinic.py` (~430 lines)

---

### Step 3: Delete Clinic Templates

```bash
# Delete clinic templates directory
rm -rf c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/templates/clinic/

# Verify deletion
if [ ! -d c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/templates/clinic/ ]; then
    echo "[OK] clinic templates deleted"
else
    echo "[ERROR] Failed to delete clinic templates"
fi
```

**Files Deleted:**
- `templates/clinic/clinic_hub.html`
- `templates/clinic/appointment_booking.html`
- `templates/clinic/noshow_recovery.html`
- `templates/clinic/patient_reminders.html`
- `templates/clinic/vaccination_campaign.html`
- `templates/clinic/new_patient_intake.html`

---

### Step 4: Delete Clinic Service

```bash
# Delete clinic service
rm -f c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/services/clinic_service.py

# Verify deletion
if [ ! -f c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/services/clinic_service.py ]; then
    echo "[OK] clinic_service.py deleted"
else
    echo "[ERROR] Failed to delete clinic_service.py"
fi
```

**Files Deleted:**
- `services/clinic_service.py` (~300 lines)

---

### Step 5: Delete Clinic Migration

```bash
# Delete clinic migration
rm -f c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/migrations/add_clinic_feature_fields.py

# Verify deletion
if [ ! -f c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/migrations/add_clinic_feature_fields.py ]; then
    echo "[OK] clinic migration deleted"
else
    echo "[ERROR] Failed to delete clinic migration"
fi
```

**Files Deleted:**
- `migrations/add_clinic_feature_fields.py`

---

### Step 6: Delete Clinic Documentation

```bash
# Delete clinic docs
rm -rf c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/docs/clinics/

# Verify deletion
if [ ! -d c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/docs/clinics/ ]; then
    echo "[OK] clinic docs deleted"
else
    echo "[ERROR] Failed to delete clinic docs"
fi
```

**Files Deleted:**
- `docs/clinics/CLINIC_DOCUMENTATION_INDEX.md`
- `docs/clinics/CLINIC_PHASE_2_GUIDE.md`
- `docs/clinics/CLINIC_PHASE_2_SERVER_MANUAL.md`
- `docs/clinics/CLINIC_QUICK_REFERENCE.md`
- `docs/clinics/CLINIC_IMPLEMENTATION_CHECKLIST.md`
- `docs/clinics/CLINIC_DELETION_GUIDE.md` (this file)

---

### Step 7: Update `routes/__init__.py`

**Open file:**
```bash
nano c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/routes/__init__.py
```

**Find and DELETE these 2 lines:**

```python
from .clinic import clinic_bp
```

And:

```python
app.register_blueprint(clinic_bp)  # Clinic platform pages (/clinic/*)
```

**After deletion, the file should have:**

```python
"""
Routes package - Blueprint registration for all application routes
"""

def register_blueprints(app):
    """Register all application blueprints"""
    from .core import core_bp
    from .agents import agents_bp
    from .campaigns import campaigns_bp
    from .inbound import inbound_bp
    from .public_api import public_api_bp
    from .workflows import workflows_bp
    from .test_agent import test_agent_bp
    from .api_v1 import api_v1_bp
    from .whatsapp import whatsapp_bp

    # Register blueprints in order
    app.register_blueprint(core_bp)
    app.register_blueprint(agents_bp, url_prefix='/agent')
    app.register_blueprint(campaigns_bp, url_prefix='/outbound')
    app.register_blueprint(inbound_bp, url_prefix='/inbound')
    app.register_blueprint(workflows_bp)
    app.register_blueprint(public_api_bp)
    app.register_blueprint(test_agent_bp, url_prefix='/test-agent')
    app.register_blueprint(api_v1_bp)
    app.register_blueprint(whatsapp_bp, url_prefix='/whatsapp')
```

**Save:** Ctrl+O → Enter → Ctrl+X

---

### Step 8: Update `models.py`

**Open file:**
```bash
nano c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/models.py
```

**Find the Workflow class (~line 200):**

Look for:
```python
clinic_feature_type = db.Column(db.String(50), nullable=True)
clinic_config = db.Column(db.JSON, nullable=True)
```

**DELETE these 2 lines completely.**

**After deletion, the Workflow class should not have any clinic-related columns.**

**Save:** Ctrl+O → Enter → Ctrl+X

---

### Step 9: Update `templates/base.html`

**Open file:**
```bash
nano c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/templates/base.html
```

**Search for:** `CLINIC START` (Ctrl+W in nano)

**Delete the entire block between these comments:**

```html
<!-- CLINIC START -->
... (everything until CLINIC END)
<!-- CLINIC END -->
```

**Including:**
- Clinic Hub link
- Appointments submenu
- Outreach submenu
- All nested links

**Search for:** `sbMenu('clinic')` and `sbMenu('clinicout')`

**Delete or update this line (around line 751):**

From:
```javascript
['inbound','outbound','socials','clinic','clinicout'].forEach(id => {
```

To:
```javascript
['inbound','outbound','socials'].forEach(id => {
```

**Delete these lines (around line 768):**

```javascript
if (p.includes('/clinic/appointment') || p.includes('/clinic/noshow') || p.includes('/clinic/reminder')) sbMenu('clinic');
if (p.includes('/clinic/vaccination') || p.includes('/clinic/intake')) sbMenu('clinicout');
```

**Save:** Ctrl+O → Enter → Ctrl+X

---

### Step 10: Clean Database - Delete Clinic Workflows

```bash
cd c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project

python << 'EOF'
from app import app
from models import db, Workflow

with app.app_context():
    # Find all clinic workflows
    clinic_workflows = Workflow.query.filter(
        Workflow.clinic_feature_type.isnot(None)
    ).all()

    print(f"Found {len(clinic_workflows)} clinic workflows")

    # Delete each one
    for workflow in clinic_workflows:
        print(f"  Deleting: {workflow.clinic_feature_type} (ID: {workflow.id})")
        db.session.delete(workflow)

    # Commit changes
    db.session.commit()

    print(f"[OK] Deleted {len(clinic_workflows)} clinic workflows from database")

EOF
```

**Expected output:**
```
Found X clinic workflows
  Deleting: appointment_booking (ID: XX)
  Deleting: patient_reminders (ID: XX)
  ...
[OK] Deleted X clinic workflows from database
```

---

### Step 11: Clean Database - Drop Clinic Columns

```bash
cd c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project

python << 'EOF'
from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    # Drop clinic_feature_type column
    try:
        print("Dropping clinic_feature_type column...")
        db.session.execute(text('ALTER TABLE workflow DROP COLUMN clinic_feature_type'))
        db.session.commit()
        print("[OK] Dropped clinic_feature_type")
    except Exception as e:
        print(f"[INFO] Column already dropped or error: {e}")
        db.session.rollback()

    # Drop clinic_config column
    try:
        print("Dropping clinic_config column...")
        db.session.execute(text('ALTER TABLE workflow DROP COLUMN clinic_config'))
        db.session.commit()
        print("[OK] Dropped clinic_config")
    except Exception as e:
        print(f"[INFO] Column already dropped or error: {e}")
        db.session.rollback()

EOF
```

**Expected output:**
```
Dropping clinic_feature_type column...
[OK] Dropped clinic_feature_type
Dropping clinic_config column...
[OK] Dropped clinic_config
```

---

### Step 12: Restart Flask Server

```bash
cd c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project

# Start Flask
python app.py

# You should see:
# [INFO] All blueprints registered successfully
# (no clinic blueprint error)
```

---

## Verification Checklist

After completing all deletion steps, verify everything is clean:

### 1. Check File Deletions

```bash
echo "=== FILE VERIFICATION ==="

# Check clinic.py deleted
if [ -f c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/routes/clinic.py ]; then
    echo "[ERROR] clinic.py still exists"
else
    echo "[OK] clinic.py deleted"
fi

# Check templates/clinic deleted
if [ -d c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/templates/clinic/ ]; then
    echo "[ERROR] templates/clinic still exists"
else
    echo "[OK] templates/clinic deleted"
fi

# Check clinic_service.py deleted
if [ -f c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/services/clinic_service.py ]; then
    echo "[ERROR] clinic_service.py still exists"
else
    echo "[OK] clinic_service.py deleted"
fi

# Check docs/clinics deleted
if [ -d c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/docs/clinics/ ]; then
    echo "[ERROR] docs/clinics still exists"
else
    echo "[OK] docs/clinics deleted"
fi
```

### 2. Check Code Deletions

```bash
echo "=== CODE VERIFICATION ==="

# Check clinic imports in routes/__init__.py
if grep -q "from .clinic import" c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/routes/__init__.py; then
    echo "[ERROR] clinic import still in routes/__init__.py"
else
    echo "[OK] clinic import removed from routes/__init__.py"
fi

# Check clinic registration in routes/__init__.py
if grep -q "register_blueprint(clinic_bp)" c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/routes/__init__.py; then
    echo "[ERROR] clinic blueprint registration still in routes/__init__.py"
else
    echo "[OK] clinic blueprint registration removed from routes/__init__.py"
fi

# Check clinic columns in models.py
if grep -q "clinic_feature_type" c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/models.py; then
    echo "[ERROR] clinic_feature_type still in models.py"
else
    echo "[OK] clinic_feature_type removed from models.py"
fi

if grep -q "clinic_config" c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/models.py; then
    echo "[ERROR] clinic_config still in models.py"
else
    echo "[OK] clinic_config removed from models.py"
fi

# Check clinic sidebar in base.html
if grep -q "CLINIC START" c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/templates/base.html; then
    echo "[ERROR] clinic sidebar still in base.html"
else
    echo "[OK] clinic sidebar removed from base.html"
fi
```

### 3. Check Database

```bash
cd c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project

python << 'EOF'
from app import app
from models import db, Workflow
from sqlalchemy import inspect

with app.app_context():
    # Check clinic workflows
    clinic_count = Workflow.query.filter(
        Workflow.clinic_feature_type.isnot(None)
    ).count()

    if clinic_count == 0:
        print("[OK] No clinic workflows in database")
    else:
        print(f"[ERROR] Found {clinic_count} clinic workflows still in database")

    # Check if columns exist
    inspector = inspect(db.engine)
    columns = [c['name'] for c in inspector.get_columns('workflow')]

    if 'clinic_feature_type' in columns:
        print("[ERROR] clinic_feature_type column still in database")
    else:
        print("[OK] clinic_feature_type column removed from database")

    if 'clinic_config' in columns:
        print("[ERROR] clinic_config column still in database")
    else:
        print("[OK] clinic_config column removed from database")

EOF
```

### 4. Test Flask Startup

```bash
# Test Flask can start without clinic errors
cd c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project

timeout 10 python app.py 2>&1 | grep -i "clinic\|error" || echo "[OK] No clinic errors on startup"
```

---

## Troubleshooting

### Issue: "clinic.py still exists after deletion"

**Solution:**
```bash
# Force delete
rm -f c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/routes/clinic.py
sudo rm -f c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/routes/clinic.py
```

### Issue: "Flask won't start - clinic import error"

**Solution:**
```bash
# Make sure routes/__init__.py is properly updated
grep -n "clinic" c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/routes/__init__.py

# If clinic references exist, remove them manually
nano c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/routes/__init__.py
```

### Issue: "Database drop column failed"

**Solution:**
```bash
# Try alternative approach
cd c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project

python << 'EOF'
from app import app
from models import db
from sqlalchemy import text, inspect

with app.app_context():
    # Check if column exists before dropping
    inspector = inspect(db.engine)
    columns = [c['name'] for c in inspector.get_columns('workflow')]

    for col in ['clinic_feature_type', 'clinic_config']:
        if col in columns:
            try:
                db.session.execute(text(f'ALTER TABLE workflow DROP COLUMN {col}'))
                db.session.commit()
                print(f"[OK] Dropped {col}")
            except Exception as e:
                print(f"[ERROR] Failed to drop {col}: {e}")
                db.session.rollback()
        else:
            print(f"[INFO] {col} doesn't exist")

EOF
```

### Issue: "Sidebar still shows clinic links"

**Solution:**
1. Clear browser cache (Ctrl+Shift+Delete)
2. Hard refresh (Ctrl+Shift+R)
3. Verify base.html was properly saved
4. Restart Flask server

### Issue: "/clinic/ endpoint still accessible"

**Solution:**
1. Verify clinic.py was deleted
2. Verify routes/__init__.py was updated
3. Restart Flask
4. Check Flask logs: `grep "clinic" /tmp/flask.log`

---

## After Deletion

### What's Clean

✅ No clinic routes
✅ No clinic templates
✅ No clinic service
✅ No clinic workflows in database
✅ No clinic columns in database
✅ No clinic sidebar navigation
✅ No clinic documentation

### What Still Works

✅ All agents preserved
✅ All non-clinic workflows preserved
✅ All campaigns preserved
✅ Authentication and users intact
✅ Original Nevox features fully functional

### Platform Status

The Nevox platform should now show:

**Sidebar Menu:**
- Workflows
- Agents
- Outbound Campaigns
- Inbound
- WhatsApp Bots

**No Clinic Hub or clinic submenus**

---

## FAQ

### Q: Can I restore clinic features after deletion?

**A:** Yes! If you created a backup before deletion:
```bash
cp c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/instance/nevox.db.backup \
   c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/instance/nevox.db
```

Then restore the files from git or your backup.

### Q: Will my agents/campaigns be deleted?

**A:** No! Only clinic-specific data is deleted. All agents, campaigns, and workflows (non-clinic) are preserved.

### Q: What if I delete the wrong files?

**A:** Use your backup to restore. Always create a backup before any major changes.

### Q: Can I delete only specific clinic features?

**A:** The deletion process removes ALL clinic features together. Individual feature removal would require code changes.

### Q: How do I know if deletion was successful?

**A:** Use the **Verification Checklist** section above to confirm all deletions.

### Q: Should I delete the database backup?

**A:** Keep it for 30-60 days. After that, safe to delete if everything works properly.

### Q: Can I re-add clinic features later?

**A:** Yes! You can re-implement by following the Phase 1, Phase 2 guides again.

### Q: What about clinic migrations?

**A:** The migration file is deleted. If you re-add clinic features, you'll create a new migration file.

### Q: Will users notice the clinic platform is gone?

**A:** Yes - they'll see the clinic sidebar removed on next login/refresh. No functionality loss otherwise.

---

## Support & Rollback

### If Something Goes Wrong

1. **Stop Flask:** `pkill -f "python app.py"`
2. **Restore backup:** `cp nevox.db.backup nevox.db`
3. **Restart Flask:** `python app.py`
4. **Clinic features restored**

### Document Feedback

Found issues with this guide? Update this file:
```
c:/Users/mzain/Python-projects/Commercial/nevoxai_server/nevoxai-project/docs/clinics/CLINIC_DELETION_GUIDE.md
```

---

## Checklist Summary

- [ ] Created database backup
- [ ] Stopped Flask server
- [ ] Deleted clinic.py
- [ ] Deleted templates/clinic/
- [ ] Deleted services/clinic_service.py
- [ ] Deleted migrations/add_clinic_feature_fields.py
- [ ] Deleted docs/clinics/
- [ ] Updated routes/__init__.py
- [ ] Updated models.py
- [ ] Updated templates/base.html
- [ ] Deleted clinic workflows from database
- [ ] Dropped clinic columns from database
- [ ] Restarted Flask
- [ ] Verified all deletions
- [ ] Tested Flask startup

---

**Deletion Complete!** ✅

Your Nevox platform is now back to the original state without clinic features.

