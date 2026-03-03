#!/usr/bin/env python3
"""
Simple startup script for LiveKit Voice Agent + Flask Dashboard
"""

import subprocess
import time
import sys
import os
from pathlib import Path

def main():
    print("🚀 LiveKit Voice Agent System")
    print("=" * 60)

    current_dir = Path(__file__).parent
    agent_file = current_dir / "agent.py"
    agent_inbound_file = current_dir / "agent-inbound.py"
    app_file = current_dir / "app.py"
    campaign_file = current_dir / "services" / "campaign_worker.py"

    # Check files exist
    if not agent_file.exists():
        print(f"❌ Error: agent.py not found!")
        return 1

    if not agent_inbound_file.exists():
        print(f"❌ Error: agent-inbound.py not found!")
        return 1

    if not app_file.exists():
        print(f"❌ Error: app.py not found!")
        return 1

    print("📁 Files found:")
    print(f"   Agent: {agent_file}")
    print(f"   Agent Inbound: {agent_inbound_file}")
    print(f"   Dashboard: {app_file}")
    print(f"   Campaign Worker: {campaign_file}")
    print()

    try:
        # Start agent
        print("🤖 Starting LiveKit Agent...")
        agent_process = subprocess.Popen(
            [sys.executable, str(agent_file), "dev"],
            cwd=str(current_dir)
        )
        print("✅ Agent started (PID: {})".format(agent_process.pid))

        # Wait for agent to initialize
        time.sleep(3)

        print("🤖 Starting LiveKit Inbound Agent...")
        agent_inbound_process = subprocess.Popen(
            [sys.executable, str(agent_inbound_file), "dev"],
            cwd=str(current_dir)
        )
        print("✅ Inbound Agent started (PID: {})".format(agent_inbound_process.pid))
        
        time.sleep(3)

        print("🤖 Starting Campaign Worker...")
        campaign_process = subprocess.Popen(
            [sys.executable, str(campaign_file)],
            cwd=str(current_dir)
        )
        print("✅ Campaign Worker started (PID: {})".format(campaign_process.pid))

        time.sleep(3)

        # Start Flask dashboard
        print("🌐 Starting Flask Dashboard...")
        web_process = subprocess.Popen(
            [sys.executable, str(app_file)],
            cwd=str(current_dir)
        )
        print("✅ Dashboard started (PID: {})".format(web_process.pid))

        print()
        print("=" * 60)
        print("🎯 SYSTEM READY!")
        print("=" * 60)
        print()
        print("📱 Dashboard: http://localhost:5000")
        print("🤖 Agent: Running and listening for calls")
        print()
        print("📝 How to use:")
        print("1. Open http://localhost:5000 in your browser")
        print("2. Login (admin/admin123)")
        print("3. Create or select an agent")
        print("4. Enter phone number with country code (e.g., +923001234567)")
        print("5. Click 'Make Call'")
        print("6. Agent will speak in Arabic when call connects")
        print()
        print("⏹️  Press Ctrl+C to stop both services")
        print("=" * 60)

        # Wait for processes
        try:
            agent_process.wait()
            web_process.wait()
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down...")
            print("   Stopping agent...")
            agent_process.terminate()
            print("   Stopping dashboard...")
            web_process.terminate()
            agent_process.wait()
            web_process.wait()
            print("✅ Shutdown complete")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
