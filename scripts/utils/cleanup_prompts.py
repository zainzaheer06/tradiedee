"""
Clean up extra spaces in agent prompts
"""
import sqlite3
import os
import re

def clean_text(text):
    """Remove extra spaces and normalize whitespace"""
    if not text:
        return text

    # Replace multiple spaces with single space
    text = re.sub(r' +', ' ', text)

    # Replace multiple newlines with max 2 newlines
    text = re.sub(r'\n\n\n+', '\n\n', text)

    # Remove trailing spaces on each line
    text = '\n'.join(line.rstrip() for line in text.split('\n'))

    # Strip leading/trailing whitespace from entire text
    text = text.strip()

    return text

def cleanup_database():
    """Clean up prompts and greetings in database"""
    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'voice_agent.db')

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all agents
    cursor.execute("SELECT id, name, prompt, greeting FROM agent")
    agents = cursor.fetchall()

    print("=" * 60)
    print("Cleaning Agent Prompts")
    print("=" * 60)
    print(f"\nFound {len(agents)} agents\n")

    updated_count = 0

    for agent_id, name, prompt, greeting in agents:
        updated = False

        # Clean prompt
        if prompt:
            cleaned_prompt = clean_text(prompt)
            if cleaned_prompt != prompt:
                cursor.execute("UPDATE agent SET prompt = ? WHERE id = ?", (cleaned_prompt, agent_id))
                print(f"  [{agent_id}] {name}")
                print(f"      Prompt: Removed {len(prompt) - len(cleaned_prompt)} characters")
                updated = True

        # Clean greeting
        if greeting:
            cleaned_greeting = clean_text(greeting)
            if cleaned_greeting != greeting:
                cursor.execute("UPDATE agent SET greeting = ? WHERE id = ?", (cleaned_greeting, agent_id))
                if not updated:
                    print(f"  [{agent_id}] {name}")
                print(f"      Greeting: Removed {len(greeting) - len(cleaned_greeting)} characters")
                updated = True

        if updated:
            updated_count += 1

    conn.commit()
    conn.close()

    print(f"\n[SUCCESS] Cleaned {updated_count} agent(s)")
    print("=" * 60)

if __name__ == "__main__":
    cleanup_database()
