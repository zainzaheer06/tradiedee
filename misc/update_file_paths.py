#!/usr/bin/env python3
"""
Script to update file paths after reorganizing config and data files
"""

import os

# Define the mapping of old paths to new paths
PATH_MAPPINGS = {
    # Google credentials
    'aimeetingassistant-448613-1ff1fc705734.json': 'config/google/aimeetingassistant-448613-1ff1fc705734.json',
}

def update_paths_in_file(filepath):
    """Update file paths in a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content
        updates_made = 0

        # Replace each path
        for old_path, new_path in PATH_MAPPINGS.items():
            if old_path in content:
                count = content.count(old_path)
                content = content.replace(old_path, new_path)
                print(f"  [OK] Updated '{old_path}' -> '{new_path}' ({count} occurrence(s))")
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
    """Update paths in main application files"""
    files_to_update = [
        'agent.py',
        'agent-inbound.py',
    ]

    total_updates = 0

    for filename in files_to_update:
        if os.path.exists(filename):
            print(f"\nUpdating {filename}...")
            updates = update_paths_in_file(filename)
            total_updates += updates
            if updates == 0:
                print(f"  [INFO] No changes needed")
        else:
            print(f"\n[WARN] File not found: {filename}")

    print(f"\n[SUCCESS] Total updates: {total_updates}")

if __name__ == '__main__':
    main()
