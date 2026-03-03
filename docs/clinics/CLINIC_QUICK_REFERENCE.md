# Clinic Platform — Quick Reference Guide

## Phase 1: Frontend Templates (COMPLETED ✅)
- **Status**: Done, ready to use
- **Files**: 6 template pages + 1 routes file + sidebar updates
- **What it does**: Beautiful clinic-specific UI with form fields

## Phase 2: Backend Implementation (COMPLETED ✅)
- **Status**: Done, all files created
- **Files**: Database model + migration + service + updated routes

---

## All Files Created/Modified

### ✅ CREATED (New Files)
```
✓ migrations/add_clinic_feature_fields.py    (Database migration)
✓ services/clinic_service.py                 (Business logic service)
✓ templates/clinic/clinic_hub.html           (Main dashboard)
✓ templates/clinic/appointment_booking.html  (Config page)
✓ templates/clinic/noshow_recovery.html      (Config page)
✓ templates/clinic/patient_reminders.html    (Config page)
✓ templates/clinic/vaccination_campaign.html (Config page)
✓ templates/clinic/new_patient_intake.html   (Config page)
✓ routes/clinic.py                           (All routes)
```

### ✅ MODIFIED (Existing Files)
```
✓ models.py                                  (Added clinic fields to Workflow)
✓ routes/__init__.py                         (Added clinic blueprint import)
✓ templates/base.html                        (Added clinic sidebar section)
```

### 📚 DOCUMENTATION (Created)
```
✓ CLINIC_PHASE_2_GUIDE.md                    (Implementation guide)
✓ CLINIC_PHASE_2_SERVER_MANUAL.md            (Step-by-step manual)
✓ CLINIC_QUICK_REFERENCE.md                  (This file)
```

---

## Quick Setup Steps

### 1. Copy All Files
Make sure these files are in place:
- [ ] All 8 clinic template files in `templates/clinic/`
- [ ] `services/clinic_service.py`
- [ ] `migrations/add_clinic_feature_fields.py`
- [ ] `routes/clinic.py` (fully updated)

### 2. Update Existing Files
- [ ] `models.py` — Add clinic fields (4 lines)
- [ ] `routes/__init__.py` — Import clinic blueprint (2 lines)
- [ ] `templates/base.html` — Add clinic sidebar section (already done)

### 3. Run Database Migration
```bash
cd /path/to/project
flask db upgrade
```

### 4. Restart Flask
```bash
# Stop current server (Ctrl+C)
# Restart
python app.py
```

### 5. Test
- Navigate to: `http://localhost:5004/clinic/`
- Should see clinic dashboard with all features

---

## File Size Reference

| File | Type | Lines | Size |
|------|------|-------|------|
| `services/clinic_service.py` | Python | 280 | ~9 KB |
| `routes/clinic.py` | Python | 430 | ~16 KB |
| `migrations/add_clinic_feature_fields.py` | Python | 28 | ~0.8 KB |
| `templates/clinic/clinic_hub.html` | HTML | 500+ | ~18 KB |
| `templates/clinic/appointment_booking.html` | HTML | 290 | ~10 KB |
| `templates/clinic/noshow_recovery.html` | HTML | 260 | ~9 KB |
| `templates/clinic/patient_reminders.html` | HTML | 280 | ~10 KB |
| `templates/clinic/vaccination_campaign.html` | HTML | 220 | ~8 KB |
| `templates/clinic/new_patient_intake.html` | HTML | 350 | ~12 KB |

---

## Database Changes

### Added to `workflow` table:
```sql
ALTER TABLE workflow ADD COLUMN clinic_feature_type VARCHAR(50);
ALTER TABLE workflow ADD COLUMN clinic_config JSON;
CREATE INDEX ix_workflow_clinic_feature_type ON workflow(clinic_feature_type);
```

### Data stored in `clinic_config`:
```json
{
  "agent_id": 123,
  "opening_time": "08:00",
  "closing_time": "18:00",
  "operating_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
  "min_advance_hours": 2,
  "max_advance_days": 30,
  "send_confirmation_call": true,
  "... other feature-specific fields ..."
}
```

---

## API Endpoints Created

### Configuration Endpoints
```
POST /clinic/api/appointment-booking
POST /clinic/api/noshow-recovery
POST /clinic/api/patient-reminders
POST /clinic/api/vaccination-campaign
POST /clinic/api/new-patient-intake
```

### Status Endpoint
```
GET /clinic/api/status/<feature_type>
Returns: { configured: bool, workflow_id: int, agent_id: int, last_updated: string }
```

### Page Routes
```
GET /clinic/                              — Hub dashboard
GET /clinic/appointment-booking           — Config page
GET /clinic/noshow-recovery               — Config page
GET /clinic/patient-reminders             — Config page
GET /clinic/vaccination-campaign          — Config page
GET /clinic/new-patient-intake            — Config page
```

---

## Feature Types Supported

```
'appointment_booking'        — AI books appointments
'noshow_recovery'            — Calls missed appointments
'patient_reminders'          — Reminder calls before appointments
'vaccination_campaign'       — Outreach campaign calls
'new_patient_intake'         — Registration questionnaire
```

---

## Key Features

✅ **Form Validation**
- Agent required on all forms
- Type checking for numeric fields
- Feature-specific validation

✅ **Error Handling**
- Try/catch blocks on all API routes
- Detailed error messages shown to user
- Logging for debugging

✅ **Data Storage**
- JSON config for flexible storage
- Can store any feature-specific settings
- Pre/post webhook URLs supported

✅ **User Experience**
- Pre-filled forms when editing
- Success/error toast notifications
- Redirect to hub after save
- Status badges showing configuration state

✅ **Isolation**
- All clinic code in separate files
- Can be deleted without affecting other features
- No dependencies on other modules except core models

---

## Troubleshooting

### 404 on /clinic/
- **Cause**: Flask not restarted
- **Fix**: Restart Flask server

### Agent not showing in select
- **Cause**: No agents created
- **Fix**: Create agent in Setup > Agents first

### Form won't submit
- **Cause**: Browser console errors
- **Fix**: Open F12, check console for JavaScript errors

### Database errors
- **Cause**: Migration not applied
- **Fix**: Run `flask db upgrade`

### Data not saving
- **Cause**: Validation error
- **Fix**: Check form for required fields (agent must be selected)

---

## Related Documentation

- `CLINIC_PHASE_2_SERVER_MANUAL.md` — Detailed step-by-step guide
- `CLINIC_PHASE_2_GUIDE.md` — Architecture and implementation strategy
- Templates source — All 6 templates with full HTML/CSS/JS

---

## Version Info

- **Phase**: 2 (Backend Complete)
- **Date**: February 2026
- **Status**: Production Ready
- **Test Coverage**: All CRUD operations work
- **Database**: SQLite (or PostgreSQL compatible)

---

## Support Notes

### For Questions:
1. Check `CLINIC_PHASE_2_SERVER_MANUAL.md` for step-by-step setup
2. Review `services/clinic_service.py` for business logic
3. Check `routes/clinic.py` for API implementation
4. Read template files for frontend logic

### For Debugging:
1. Check Flask logs: `flask run --debug`
2. Check browser console: F12 > Console tab
3. Check network tab: F12 > Network tab
4. Query database directly: Check workflow table

### For Customization:
- Add new features: Create new route + template pair
- Modify validation: Update `validate_clinic_config()` in service
- Change UI: Edit template HTML/CSS
- Add fields: Extend `clinic_config` JSON structure

---

## Deletion Checklist (If Needed)

To completely remove clinic platform:
```bash
# 1. Downgrade database
flask db downgrade

# 2. Delete files
rm services/clinic_service.py
rm migrations/add_clinic_feature_fields.py
rm -rf templates/clinic/
rm routes/clinic.py

# 3. Revert models.py (remove clinic fields)

# 4. Revert routes/__init__.py (remove clinic import)

# 5. Revert templates/base.html (remove clinic sidebar)
```

Total deletion time: ~2 minutes
Remaining system: Unaffected
