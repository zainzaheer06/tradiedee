#!/usr/bin/env python3
"""
Script to update template paths in app.py after reorganizing templates into subdirectories
"""

import re

# Define the mapping of old paths to new paths
TEMPLATE_MAPPINGS = {
    # Auth templates
    "'signup.html'": "'auth/signup.html'",
    "'login.html'": "'auth/login.html'",
    "'pending_approval.html'": "'auth/pending_approval.html'",

    # Admin templates
    "'admin_dashboard.html'": "'admin/admin_dashboard.html'",
    "'admin_trunk_management.html'": "'admin/admin_trunk_management.html'",
    "'admin_configure_trunk.html'": "'admin/admin_configure_trunk.html'",
    "'admin_inbound_trunk_management.html'": "'admin/admin_inbound_trunk_management.html'",
    "'admin_configure_inbound_trunk.html'": "'admin/admin_configure_inbound_trunk.html'",

    # User templates
    "'user_dashboard.html'": "'user/user_dashboard.html'",
    "'subscription.html'": "'user/subscription.html'",

    # Agent templates
    "'agents_list.html'": "'agents/agents_list.html'",
    "'new_agent_form.html'": "'agents/new_agent_form.html'",
    "'view_agent.html'": "'agents/view_agent.html'",
    "'inbound_agents.html'": "'agents/inbound_agents.html'",
    "'create_inbound_agent.html'": "'agents/create_inbound_agent.html'",
    "'edit_inbound_agent.html'": "'agents/edit_inbound_agent.html'",
    "'agent_knowledge_base.html'": "'agents/agent_knowledge_base.html'",

    # Call templates
    "'web_call.html'": "'calls/web_call.html'",
    "'call_logs.html'": "'calls/call_logs.html'",
    "'view_call_log.html'": "'calls/view_call_log.html'",
    "'inbound_call_logs.html'": "'calls/inbound_call_logs.html'",

    # Campaign templates
    "'campaigns.html'": "'campaigns/campaigns.html'",
    "'create_campaign.html'": "'campaigns/create_campaign.html'",
    "'edit_campaign.html'": "'campaigns/edit_campaign.html'",
    "'view_campaign.html'": "'campaigns/view_campaign.html'",
}

def update_template_paths(filepath='app.py'):
    """Read app.py and update all template paths"""
    print(f"Reading {filepath}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    updates_made = 0

    # Replace each template path
    for old_path, new_path in TEMPLATE_MAPPINGS.items():
        if old_path in content:
            count = content.count(old_path)
            content = content.replace(old_path, new_path)
            print(f"[OK] Updated {old_path} -> {new_path} ({count} occurrence(s))")
            updates_made += count
        else:
            print(f"[WARN] Not found: {old_path}")

    # Write back if changes were made
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n[SUCCESS] Updated {updates_made} template paths in {filepath}")
    else:
        print("\n[WARN] No changes made")

    return updates_made

if __name__ == '__main__':
    update_template_paths()
