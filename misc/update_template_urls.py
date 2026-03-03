"""
Update all url_for() calls in templates to use blueprint syntax
"""
import os
import re
from pathlib import Path

# Mapping of old endpoint names to new blueprint.endpoint format
URL_MAPPINGS = {
    # Core routes (authentication, main pages, admin)
    "'index'": "'core.index'",
    "'homepage'": "'core.homepage'",
    "'signup'": "'core.signup'",
    "'login'": "'core.login'",
    "'logout'": "'core.logout'",
    "'verify_email'": "'core.verify_email'",
    "'resend_verification'": "'core.resend_verification'",
    "'pending_approval'": "'core.pending_approval'",
    "'dashboard'": "'core.dashboard'",
    "'subscription'": "'core.subscription'",
    "'web_call'": "'core.web_call'",
    "'custom_tools'": "'core.custom_tools'",
    "'call_logs'": "'core.call_logs'",
    "'call_log'": "'core.call_log'",
    
    # Admin routes
    "'admin_dashboard'": "'core.admin_dashboard'",
    "'approve_user'": "'core.approve_user'",
    "'add_minutes'": "'core.add_minutes'",
    "'trunk_management'": "'core.trunk_management'",
    "'configure_trunk'": "'core.configure_trunk'",
    "'remove_trunk'": "'core.remove_trunk'",
    "'inbound_trunk_management'": "'core.inbound_trunk_management'",
    "'configure_inbound_trunk'": "'core.configure_inbound_trunk'",
    "'remove_inbound_trunk'": "'core.remove_inbound_trunk'",
    
    # Tools routes
    "'tools_list'": "'core.tools_list'",
    "'create_tool'": "'core.create_tool'",
    "'edit_tool'": "'core.edit_tool'",
    "'delete_tool'": "'core.delete_tool'",
    "'toggle_tool'": "'core.toggle_tool'",
    
    # API/Webhook routes
    "'demo_token'": "'core.demo_token'",
    "'start_demo_agent'": "'core.start_demo_agent'",
    "'call_ended_webhook'": "'core.call_ended_webhook'",
    
    # Agent routes
    "'agents_list'": "'agents.agents_list'",
    "'create_agent_redirect'": "'agents.create_agent_redirect'",
    "'create_agent_form'": "'agents.create_agent_form'",
    "'view_agent'": "'agents.view_agent'",
    "'edit_agent_form'": "'agents.edit_agent_form'",
    "'delete_agent'": "'agents.delete_agent'",
    "'make_call'": "'agents.make_call'",
    "'knowledge_base_management'": "'agents.knowledge_base_management'",
    "'upload_knowledge_base'": "'agents.upload_knowledge_base'",
    "'delete_knowledge_base'": "'agents.delete_knowledge_base'",
    "'rebuild_knowledge_base'": "'agents.rebuild_knowledge_base'",
    "'agent_tools'": "'agents.agent_tools'",
    
    # Campaign routes
    "'campaigns'": "'campaigns.campaigns'",
    "'create_campaign'": "'campaigns.create_campaign'",
    "'edit_campaign'": "'campaigns.edit_campaign'",
    "'view_campaign'": "'campaigns.view_campaign'",
    "'delete_campaign'": "'campaigns.delete_campaign'",
    "'upload_campaign_contacts'": "'campaigns.upload_campaign_contacts'",
    "'add_contacts_manual'": "'campaigns.add_contacts_manual'",
    "'start_campaign'": "'campaigns.start_campaign'",
    "'pause_campaign'": "'campaigns.pause_campaign'",
    "'stop_campaign'": "'campaigns.stop_campaign'",
    "'export_campaign'": "'campaigns.export_campaign'",
    
    # Inbound routes
    "'inbound_agents'": "'inbound.inbound_agents'",
    "'create_inbound_agent'": "'inbound.create_inbound_agent'",
    "'edit_inbound_agent'": "'inbound.edit_inbound_agent'",
    "'delete_inbound_agent'": "'inbound.delete_inbound_agent'",
    "'inbound_call_logs'": "'inbound.inbound_call_logs'",
    
    # Also handle double-quoted versions
    '"index"': '"core.index"',
    '"homepage"': '"core.homepage"',
    '"signup"': '"core.signup"',
    '"login"': '"core.login"',
    '"logout"': '"core.logout"',
    '"dashboard"': '"core.dashboard"',
    '"agents_list"': '"agents.agents_list"',
    '"campaigns"': '"campaigns.campaigns"',
    '"inbound_agents"': '"inbound.inbound_agents"',
}

def update_template_file(filepath):
    """Update url_for calls in a single template file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    changes_made = 0
    
    # Update each mapping
    for old_endpoint, new_endpoint in URL_MAPPINGS.items():
        # Match url_for(old_endpoint with optional parameters
        pattern = rf"url_for\({old_endpoint}([,\)])"
        replacement = rf"url_for({new_endpoint}\1"
        
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            changes_made += re.subn(pattern, replacement, content)[1]
            content = new_content
    
    # Write back if changes were made
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return changes_made
    return 0

def main():
    templates_dir = Path('templates')
    total_files = 0
    total_changes = 0
    
    print("Updating url_for() calls in templates...")
    print("=" * 60)
    
    for html_file in templates_dir.rglob('*.html'):
        changes = update_template_file(html_file)
        if changes > 0:
            total_files += 1
            total_changes += changes
            rel_path = html_file.relative_to(templates_dir)
            print(f"  {rel_path}: {changes} changes")
    
    print("=" * 60)
    print(f"Updated {total_files} files with {total_changes} total changes")

if __name__ == '__main__':
    main()
