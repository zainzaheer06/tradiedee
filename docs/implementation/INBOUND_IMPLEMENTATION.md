# Inbound Call Management Implementation Guide

## ✅ Completed Steps:

1. **Database Migration** - Added new fields:
   - `agent.call_type` - 'inbound' or 'outbound'
   - `agent.dispatch_rule_id` - LiveKit dispatch rule ID
   - `agent.phone_number` - Inbound phone number
   - `call_log.call_type` - Track call direction

2. **Model Updates** - Updated Agent and CallLog models in app.py

---

## 📋 TODO: Routes to Add to app.py

Add these routes after your existing agent routes:

```python
# ==================== INBOUND AGENTS ====================

@app.route('/inbound')
@login_required
def inbound_agents():
    """List all inbound agents for current user"""
    agents = Agent.query.filter_by(
        user_id=session['user_id'],
        call_type='inbound'
    ).order_by(Agent.created_at.desc()).all()
    return render_template('inbound_agents.html', agents=agents)


@app.route('/inbound/create', methods=['GET', 'POST'])
@login_required
def create_inbound_agent():
    """Create new inbound agent and dispatch rule"""
    if request.method == 'POST':
        name = request.form.get('name')
        prompt = request.form.get('prompt')
        greeting = request.form.get('greeting')
        voice_id = request.form.get('voice_id')
        voice_name = request.form.get('voice_name')
        phone_number = request.form.get('phone_number')  # Optional: for display

        # Create agent in database
        agent = Agent(
            user_id=session['user_id'],
            name=name,
            prompt=prompt,
            greeting=greeting,
            voice_id=voice_id,
            voice_name=voice_name,
            call_type='inbound',
            phone_number=phone_number
        )
        db.session.add(agent)
        db.session.flush()  # Get agent.id

        # Create LiveKit dispatch rule
        try:
            livekit_api = api.LiveKitAPI(
                url=os.environ.get('LIVEKIT_URL'),
                api_key=os.environ.get('LIVEKIT_API_KEY'),
                api_secret=os.environ.get('LIVEKIT_API_SECRET')
            )

            # Create dispatch rule with agent_id in metadata
            dispatch_rule = asyncio.run(livekit_api.sip.create_sip_dispatch_rule(
                api.CreateSIPDispatchRuleRequest(
                    trunk_ids=[os.environ.get('SIP_INBOUND_TRUNK_ID')],
                    name=f"Inbound: {name}",
                    metadata=json.dumps({"auto_ai": True}),
                    attributes={
                        "agent_name": name,
                        "user_id": str(session['user_id'])
                    },
                    rule=api.SIPDispatchRule(
                        dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                            room_prefix="call-"
                        )
                    ),
                    room_config=api.RoomConfiguration(
                        agents=[api.RoomAgentDispatch(
                            agent_name="agent-inbound",
                            metadata=json.dumps({
                                "language": "ar",
                                "model": "gpt-4o-realtime",
                                "agent_id": agent.id  # Pass agent ID here!
                            })
                        )]
                    )
                )
            ))

            # Save dispatch rule ID
            agent.dispatch_rule_id = dispatch_rule.sip_dispatch_rule_id
            db.session.commit()

            flash(f'Inbound agent "{name}" created successfully!', 'success')
            return redirect(url_for('inbound_agents'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating dispatch rule: {str(e)}', 'error')
            logger.error(f"Dispatch rule creation error: {e}")
            return redirect(url_for('create_inbound_agent'))

    # GET request - show form
    voices = get_available_voices()
    return render_template('create_inbound_agent.html', voices=voices)


@app.route('/inbound/<int:agent_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_inbound_agent(agent_id):
    """Edit existing inbound agent"""
    agent = Agent.query.filter_by(
        id=agent_id,
        user_id=session['user_id'],
        call_type='inbound'
    ).first_or_404()

    if request.method == 'POST':
        agent.name = request.form.get('name')
        agent.prompt = request.form.get('prompt')
        agent.greeting = request.form.get('greeting')
        agent.voice_id = request.form.get('voice_id')
        agent.voice_name = request.form.get('voice_name')
        agent.phone_number = request.form.get('phone_number')

        # Update dispatch rule if needed
        if agent.dispatch_rule_id:
            try:
                livekit_api = api.LiveKitAPI(
                    url=os.environ.get('LIVEKIT_URL'),
                    api_key=os.environ.get('LIVEKIT_API_KEY'),
                    api_secret=os.environ.get('LIVEKIT_API_SECRET')
                )

                # Update dispatch rule metadata
                asyncio.run(livekit_api.sip.delete_sip_dispatch_rule(
                    api.DeleteSIPDispatchRuleRequest(
                        sip_dispatch_rule_id=agent.dispatch_rule_id
                    )
                ))

                # Recreate with new settings (same as create)
                # ... (copy dispatch rule creation code from above)

            except Exception as e:
                logger.error(f"Error updating dispatch rule: {e}")

        db.session.commit()
        flash('Inbound agent updated successfully!', 'success')
        return redirect(url_for('inbound_agents'))

    voices = get_available_voices()
    return render_template('edit_inbound_agent.html', agent=agent, voices=voices)


@app.route('/inbound/<int:agent_id>/delete', methods=['POST'])
@login_required
def delete_inbound_agent(agent_id):
    """Delete inbound agent and its dispatch rule"""
    agent = Agent.query.filter_by(
        id=agent_id,
        user_id=session['user_id'],
        call_type='inbound'
    ).first_or_404()

    # Delete LiveKit dispatch rule
    if agent.dispatch_rule_id:
        try:
            livekit_api = api.LiveKitAPI(
                url=os.environ.get('LIVEKIT_URL'),
                api_key=os.environ.get('LIVEKIT_API_KEY'),
                api_secret=os.environ.get('LIVEKIT_API_SECRET')
            )

            asyncio.run(livekit_api.sip.delete_sip_dispatch_rule(
                api.DeleteSIPDispatchRuleRequest(
                    sip_dispatch_rule_id=agent.dispatch_rule_id
                )
            ))

        except Exception as e:
            logger.error(f"Error deleting dispatch rule: {e}")

    db.session.delete(agent)
    db.session.commit()

    flash('Inbound agent deleted successfully!', 'success')
    return redirect(url_for('inbound_agents'))


@app.route('/inbound/calls')
@login_required
def inbound_call_logs():
    """View all inbound call logs"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Get inbound agents for this user
    agent_ids = [a.id for a in Agent.query.filter_by(
        user_id=session['user_id'],
        call_type='inbound'
    ).all()]

    # Get call logs
    pagination = CallLog.query.filter(
        CallLog.agent_id.in_(agent_ids),
        CallLog.call_type == 'inbound'
    ).order_by(CallLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('inbound_call_logs.html',
                          pagination=pagination,
                          calls=pagination.items)
```

---

## 📋 TODO: Update Sidebar (base.html or layout.html)

Add this menu item in your sidebar navigation:

```html
<!-- Inbound Calls Section -->
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('inbound_agents') }}">
        <i class="bi bi-telephone-inbound"></i>
        Inbound Calls
    </a>
</li>
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('inbound_call_logs') }}">
        <i class="bi bi-list-ul"></i>
        Inbound Call Logs
    </a>
</li>
```

---

## 📋 TODO: Create Templates

### 1. `templates/inbound_agents.html`
List of all inbound agents with create/edit/delete buttons

### 2. `templates/create_inbound_agent.html`
Form to create new inbound agent (similar to create_agent.html but with inbound-specific fields)

### 3. `templates/edit_inbound_agent.html`
Form to edit existing inbound agent

### 4. `templates/inbound_call_logs.html`
List of all inbound calls with transcriptions and interest analysis

---

## 🔧 How It Works:

1. **User creates inbound agent** via UI
2. **System automatically**:
   - Creates agent in database with `call_type='inbound'`
   - Creates LiveKit SIP dispatch rule
   - Passes `agent_id` in dispatch rule metadata
3. **When call comes in**:
   - LiveKit triggers dispatch rule
   - Sends to `agent-inbound` worker
   - Worker reads `agent_id` from metadata
   - Loads correct agent config from database
4. **Call is logged** with `call_type='inbound'`
5. **User views** inbound call logs separately from outbound

---

## Next Steps:

1. Copy the routes from this document into `app.py`
2. Create the 4 template files listed above
3. Update your sidebar navigation
4. Test by creating an inbound agent
5. Make a test call to verify it works

The agent will now automatically use the correct configuration!
