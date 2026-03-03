#!/usr/bin/env python3
"""
Script to update import statements after reorganizing Python files
"""

import os
import re

# Define the mapping of old imports to new imports
IMPORT_MAPPINGS = {
    # Service imports
    'from knowledge_base_service import': 'from services.knowledge_base_service import',
    'from recording_service import': 'from services.recording_service import',
    'from tool_service import': 'from services.tool_service import',
    'import knowledge_base_service': 'from services import knowledge_base_service',
    'import recording_service': 'from services import recording_service',
    'import tool_service': 'from services import tool_service',
}

def update_imports_in_file(filepath):
    """Update imports in a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content
        updates_made = 0

        # Replace each import
        for old_import, new_import in IMPORT_MAPPINGS.items():
            if old_import in content:
                count = content.count(old_import)
                content = content.replace(old_import, new_import)
                print(f"  [OK] Updated '{old_import}' -> '{new_import}' ({count} occurrence(s))")
                updates_made += count

        # Write back if changes were made
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return updates_made

        return 0

    except Exception as e:
        print(f"  [ERROR] Failed to update {filepath}: {e}")
        return 0

def main():
    """Update imports in main application files"""
    files_to_update = [
        'app.py',
        'agent.py',
        'agent-inbound.py',
    ]

    total_updates = 0

    for filename in files_to_update:
        if os.path.exists(filename):
            print(f"\nUpdating {filename}...")
            updates = update_imports_in_file(filename)
            total_updates += updates
            if updates == 0:
                print(f"  [INFO] No changes needed")
        else:
            print(f"\n[WARN] File not found: {filename}")

    print(f"\n[SUCCESS] Total updates: {total_updates}")

if __name__ == '__main__':
    main()
