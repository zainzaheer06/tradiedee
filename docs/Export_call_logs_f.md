# Production Update Guide - February 9, 2026

## Summary of Changes
1. Identity section added to Prompt Builder
2. SIP details added to Subscription page
3. Excel export + date filters added to Call Logs

---

## 1. IDENTITY SECTION IN PROMPT BUILDER

### File: `templates/agents/new_agent_form.html`

**Change A: Add Identity checkbox (at top of section grid)**

FIND (around line 241):
```html
<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
    <!-- Role & Objective -->
```

ADD BEFORE `<!-- Role & Objective -->`:
```html
                                <!-- Identity -->
                                <label class="flex items-center gap-3 p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors">
                                    <input type="checkbox" id="section_identity" onchange="toggleSection('identity')" class="w-4 h-4 text-indigo-600 rounded">
                                    <span class="flex-1 font-medium text-gray-700">Identity</span>
                                    <i class="bi bi-info-circle text-gray-400 hover:text-indigo-600 cursor-help" title="Agent name, company, and how to introduce itself"></i>
                                </label>
```

**Change B: Add identity to sectionConfig JS object**

FIND:
```javascript
const sectionConfig = {
    role: {
```

ADD BEFORE `role: {`:
```javascript
    identity: {
        title: 'Identity',
        placeholder: `اسم الوكيل: [نورا]\nالشركة: [نيفوكس]\nالدور: [موظفة مبيعات]\n\nعند السؤال "من أنت؟":\nأنا [نورا]، مساعدة صوتية ذكية من [نيفوكس].\n\nعند السؤال عن التقنية:\nأنا مبنية بتقنية الذكاء الاصطناعي من نيفوكس.\n- لا تذكر OpenAI أو أي نظام تقني آخر.`
    },
```

**Change C: Add Identity to sectionMap in saveParsedSection function**

FIND:
```javascript
    const sectionMap = {
        'Role & Objective': 'role',
```

ADD BEFORE `'Role & Objective': 'role',`:
```javascript
        'Identity': 'identity',
```

### File: `templates/agents/new_agent_form_server.html`
Same 3 changes as above (A, B, C). Already applied if files were synced.

---

## 2. SIP DETAILS ON SUBSCRIPTION PAGE

### File: `templates/user/subscription.html`

**Change: Add SIP cards after the Account Info / Quick Stats grid**

FIND (end of file, before `{% endblock %}`):
```html
</div>
{% endblock %}
```

REPLACE WITH the full SIP block below, then `{% endblock %}`:
```html
</div>

<!-- SIP Details -->
<div class="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
    <!-- Outbound Configuration -->
    <div class="bg-white rounded-xl border border-gray-200 p-6">
        <h3 class="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
            <i class="bi bi-telephone-outbound text-indigo-600"></i>
            Outbound Configuration
        </h3>
        {% if user.sip_configured %}
        <div class="space-y-3 text-sm">
            <div class="flex justify-between py-2 border-b border-gray-100">
                <span class="text-gray-600">Status</span>
                <span class="inline-flex items-center gap-1 text-green-600 font-semibold">
                    <i class="bi bi-check-circle-fill"></i> Configured
                </span>
            </div>
            <div class="flex justify-between py-2 border-b border-gray-100">
                <span class="text-gray-600">Phone Number</span>
                <span class="font-semibold text-gray-900">{{ user.outbound_phone_number or '—' }}</span>
            </div>
            {% if user.sip_notes %}
            <div class="mt-3 p-3 bg-blue-50 rounded-lg text-xs text-blue-700">
                <i class="bi bi-info-circle"></i> {{ user.sip_notes }}
            </div>
            {% endif %}
        </div>
        {% else %}
        <div class="flex flex-col items-center justify-center py-6 text-gray-400">
            <i class="bi bi-telephone-x text-3xl mb-2"></i>
            <p class="text-sm">Outbound not configured</p>
            <p class="text-xs mt-1">Contact admin to set up outbound calling</p>
        </div>
        {% endif %}
    </div>

    <!-- Inbound Configuration -->
    <div class="bg-white rounded-xl border border-gray-200 p-6">
        <h3 class="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
            <i class="bi bi-telephone-inbound text-indigo-600"></i>
            Inbound Configuration
        </h3>
        {% if user.inbound_configurations %}
        <div class="space-y-3 text-sm">
            <div class="flex justify-between py-2 border-b border-gray-100">
                <span class="text-gray-600">Status</span>
                <span class="inline-flex items-center gap-1 text-green-600 font-semibold">
                    <i class="bi bi-check-circle-fill"></i> Configured ({{ user.inbound_configurations|length }} {{ 'number' if user.inbound_configurations|length == 1 else 'numbers' }})
                </span>
            </div>
            {% for config in user.inbound_configurations %}
            <div class="flex items-center justify-between py-2 {{ 'border-b border-gray-100' if not loop.last }}">
                <div>
                    <p class="font-semibold text-gray-900">{{ config.phone_number }}</p>
                    <p class="text-xs text-gray-500">{{ config.name }}</p>
                </div>
                <div class="text-right">
                    <span class="inline-flex items-center gap-1 px-2 py-1 bg-indigo-50 text-indigo-700 rounded text-xs font-medium">
                        <i class="bi bi-robot"></i> {{ config.agent.name if config.agent else 'Unlinked' }}
                    </span>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="flex flex-col items-center justify-center py-6 text-gray-400">
            <i class="bi bi-telephone-x text-3xl mb-2"></i>
            <p class="text-sm">Inbound not configured</p>
            <p class="text-xs mt-1">Contact admin to set up inbound numbers</p>
        </div>
        {% endif %}
    </div>
</div>
{% endblock %}
```

No route changes needed - subscription route already passes `user` object with all SIP fields.

---

## 3. EXCEL EXPORT + DATE FILTERS FOR CALL LOGS

### Dependency: Install openpyxl on production
```bash
pip install openpyxl
```

### File: `routes/core.py`

**Change A: Add imports (line 17)**

BEFORE:
```python
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
```

AFTER:
```python
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
```

**Change B: Replace call_logs route with helper + refactored route + export route**

FIND the entire `call_logs()` function (starts with `@core_bp.route('/call-logs')`).

REPLACE WITH:

```python
def _build_call_logs_query(user_id):
    """Build filtered CallLog query from request args. Shared by call_logs page and export."""
    filters = {
        'status': request.args.get('status', ''),
        'call_type': request.args.get('call_type', ''),
        'interest': request.args.get('interest', ''),
        'agent': request.args.get('agent', '', type=str),
        'phone': request.args.get('phone', '').strip(),
        'date_from': request.args.get('date_from', ''),
        'date_to': request.args.get('date_to', ''),
    }

    query = CallLog.query.filter_by(user_id=user_id)

    if filters['status']:
        query = query.filter(CallLog.status == filters['status'])
    if filters['call_type']:
        query = query.filter(CallLog.call_type == filters['call_type'])
    if filters['agent']:
        query = query.filter(CallLog.agent_id == filters['agent'])
    if filters['phone']:
        query = query.filter(
            db.or_(
                CallLog.to_number.contains(filters['phone']),
                CallLog.from_number.contains(filters['phone'])
            )
        )
    if filters['date_from']:
        try:
            date_from = datetime.strptime(filters['date_from'], '%Y-%m-%d')
            query = query.filter(CallLog.created_at >= date_from)
        except ValueError:
            pass
    if filters['date_to']:
        try:
            date_to = datetime.strptime(filters['date_to'], '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(CallLog.created_at <= date_to)
        except ValueError:
            pass
    if filters['interest']:
        if filters['interest'] == 'interested':
            query = query.filter(CallLog.sentiment_summary.like('%"interest": "Interested"%'))
        elif filters['interest'] == 'not_interested':
            query = query.filter(CallLog.sentiment_summary.like('%"interest": "Not Interested"%'))
        elif filters['interest'] == 'na':
            query = query.filter(db.or_(
                CallLog.status == 'no_answer',
                CallLog.status == 'failed'
            ))

    return query, filters


@core_bp.route('/call-logs')
@login_required
@approved_required
def call_logs():
    """Outbound call logs with pagination and filters"""
    user = db.session.get(User, session['user_id'])

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    if per_page not in [10, 25, 50, 100]:
        per_page = 25

    query, filters = _build_call_logs_query(user.id)

    pagination = query.order_by(CallLog.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)

    agents = Agent.query.filter_by(user_id=user.id).order_by(Agent.name).all()

    return render_template('calls/call_logs.html',
                         call_logs=pagination.items,
                         pagination=pagination,
                         per_page=per_page,
                         user=user,
                         agents=agents,
                         filters=filters)


@core_bp.route('/call-logs/export')
@login_required
@approved_required
def export_call_logs():
    """Export filtered call logs as Excel file"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    user = db.session.get(User, session['user_id'])
    query, filters = _build_call_logs_query(user.id)
    calls = query.order_by(CallLog.created_at.desc()).limit(5000).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Call Logs"

    # Header styling
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        bottom=Side(style="thin", color="E5E7EB")
    )

    # Note: Transcription column intentionally excluded from export
    headers = ["Date", "Phone Number", "From Number", "Agent", "Call Type",
               "Duration (sec)", "Minutes Used", "Status"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    # Data rows
    for row_idx, call in enumerate(calls, 2):
        agent_name = ""
        if call.agent_id:
            agent = db.session.get(Agent, call.agent_id)
            agent_name = agent.name if agent else ""

        ws.cell(row=row_idx, column=1, value=call.created_at.strftime('%Y-%m-%d %H:%M') if call.created_at else "")
        ws.cell(row=row_idx, column=2, value=call.to_number or "")
        ws.cell(row=row_idx, column=3, value=call.from_number or "")
        ws.cell(row=row_idx, column=4, value=agent_name)
        ws.cell(row=row_idx, column=5, value=call.call_type or "outbound")
        ws.cell(row=row_idx, column=6, value=call.duration_seconds or 0)
        ws.cell(row=row_idx, column=7, value=call.minutes_used or 0)
        ws.cell(row=row_idx, column=8, value=call.status or "")

        for col in range(1, 9):
            ws.cell(row=row_idx, column=col).border = thin_border

    # Auto-width columns
    for col in range(1, 9):
        ws.column_dimensions[chr(64 + col)].width = 18

    # Generate file in memory
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"call_logs_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )
```

### File: `templates/calls/call_logs.html`

**Change A: Add date pickers after the existing 5-column filter grid**

FIND (after the Phone Search `</div>` closing the grid):
```html
            </div>

            <!-- Filter Actions -->
```

ADD BETWEEN them:
```html
            <!-- Date Range Row -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mt-3">
                <div>
                    <label class="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">From Date</label>
                    <input type="date" name="date_from" value="{{ filters.date_from }}"
                           class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">To Date</label>
                    <input type="date" name="date_to" value="{{ filters.date_to }}"
                           class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none">
                </div>
            </div>

```

**Change B: Add Export Excel button in filter actions**

FIND:
```html
                <a href="{{ url_for('core.call_logs', per_page=per_page) }}" class="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 font-medium transition-colors text-sm">
                    <i class="bi bi-x-circle"></i>
                    Clear Filters
                </a>
                {% if filters.status or filters.call_type or filters.interest or filters.agent or filters.phone %}
```

REPLACE WITH:
```html
                <a href="{{ url_for('core.call_logs', per_page=per_page) }}" class="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 font-medium transition-colors text-sm">
                    <i class="bi bi-x-circle"></i>
                    Clear Filters
                </a>
                <button type="button" onclick="exportExcel()" class="inline-flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium transition-colors text-sm">
                    <i class="bi bi-file-earmark-excel"></i>
                    Export Excel
                </button>
                {% if filters.status or filters.call_type or filters.interest or filters.agent or filters.phone or filters.date_from or filters.date_to %}
```

**Change C: Add exportExcel JS function and update auto-open logic**

FIND (in `<script>` block):
```javascript
// Auto-open filters if any filter is active
document.addEventListener('DOMContentLoaded', function() {
    const urlParams = new URLSearchParams(window.location.search);
    const hasFilters = urlParams.has('status') || urlParams.has('call_type') ||
                       urlParams.has('interest') || urlParams.has('agent') || urlParams.has('phone');
    if (hasFilters) {
        toggleFilters();
    }
});
```

REPLACE WITH:
```javascript
function exportExcel() {
    const form = document.getElementById('filterForm');
    const formData = new FormData(form);
    const params = new URLSearchParams(formData);
    params.delete('per_page');
    window.location.href = "{{ url_for('core.export_call_logs') }}?" + params.toString();
}

// Auto-open filters if any filter is active
document.addEventListener('DOMContentLoaded', function() {
    const urlParams = new URLSearchParams(window.location.search);
    const hasFilters = urlParams.has('status') || urlParams.has('call_type') ||
                       urlParams.has('interest') || urlParams.has('agent') ||
                       urlParams.has('phone') || urlParams.has('date_from') || urlParams.has('date_to');
    if (hasFilters) {
        toggleFilters();
    }
});
```

**Change D: Update ALL pagination links to include date filters**

FIND ALL occurrences of:
```
phone=filters.phone)
```

REPLACE ALL with:
```
phone=filters.phone, date_from=filters.date_from, date_to=filters.date_to)
```

There are 5 occurrences in pagination (first page, prev, page numbers, next, last).

---

## Quick Checklist for Production

- [ ] `pip install openpyxl` on production server
- [ ] Update `templates/agents/new_agent_form.html` (3 changes)
- [ ] Update `templates/agents/new_agent_form_server.html` (3 changes - same as above)
- [ ] Update `templates/user/subscription.html` (add SIP block at bottom)
- [ ] Update `routes/core.py` (imports + replace call_logs route + add export route)
- [ ] Update `templates/calls/call_logs.html` (4 changes)
- [ ] Restart Flask app
