"""
Test script to verify tool system is working correctly
"""

import sqlite3
import os

def test_tool_system():
    """Test the tool system database"""

    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(__file__), 'voice_agent.db')

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 60)
    print("TOOL SYSTEM TEST")
    print("=" * 60)

    # Test 1: Check if tables exist
    print("\n1. Checking if tool tables exist...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('tool', 'agent_tool')")
    tables = cursor.fetchall()

    if len(tables) == 2:
        print("   ✓ Both tables exist: tool, agent_tool")
    else:
        print(f"   ✗ Missing tables! Found: {[t[0] for t in tables]}")
        print("   → Run: python migrate_tools.py")
        return False

    # Test 2: List all tools
    print("\n2. Checking tools...")
    cursor.execute("SELECT id, user_id, name, tool_type, is_active FROM tool")
    tools = cursor.fetchall()

    if tools:
        print(f"   Found {len(tools)} tool(s):")
        for tool in tools:
            status = "Active" if tool['is_active'] else "Inactive"
            print(f"   - ID {tool['id']}: {tool['name']} ({tool['tool_type']}) - {status} [User: {tool['user_id']}]")
    else:
        print("   ⚠ No tools found")
        print("   → Create a tool in the dashboard first")

    # Test 3: Check agent-tool associations
    print("\n3. Checking agent-tool assignments...")
    cursor.execute("""
        SELECT
            at.id,
            at.agent_id,
            at.tool_id,
            a.name as agent_name,
            t.name as tool_name
        FROM agent_tool at
        LEFT JOIN agent a ON at.agent_id = a.id
        LEFT JOIN tool t ON at.tool_id = t.id
    """)
    assignments = cursor.fetchall()

    if assignments:
        print(f"   Found {len(assignments)} assignment(s):")
        for assn in assignments:
            print(f"   - Agent '{assn['agent_name']}' (ID {assn['agent_id']}) → Tool '{assn['tool_name']}' (ID {assn['tool_id']})")
    else:
        print("   ⚠ No assignments found")
        print("   → Go to agent edit page → Manage Tools → Select a tool")

    # Test 4: Check for orphaned assignments
    print("\n4. Checking data integrity...")
    cursor.execute("""
        SELECT at.id, at.agent_id, at.tool_id
        FROM agent_tool at
        LEFT JOIN agent a ON at.agent_id = a.id
        LEFT JOIN tool t ON at.tool_id = t.id
        WHERE a.id IS NULL OR t.id IS NULL
    """)
    orphans = cursor.fetchall()

    if orphans:
        print(f"   ⚠ Found {len(orphans)} orphaned assignment(s) (should clean these up)")
        for orphan in orphans:
            print(f"   - Assignment ID {orphan['id']}: Agent {orphan['agent_id']} → Tool {orphan['tool_id']}")
    else:
        print("   ✓ No orphaned assignments")

    # Test 5: Show available agents
    print("\n5. Available agents...")
    cursor.execute("SELECT id, user_id, name FROM agent LIMIT 5")
    agents = cursor.fetchall()

    if agents:
        print(f"   Found {len(agents)} agent(s) (showing first 5):")
        for agent in agents:
            print(f"   - ID {agent['id']}: {agent['name']} [User: {agent['user_id']}]")
    else:
        print("   ⚠ No agents found")

    conn.close()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

    return True

if __name__ == "__main__":
    test_tool_system()
