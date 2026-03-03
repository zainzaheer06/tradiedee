"""
View Nevox-specific metrics from Prometheus endpoint
Run this AFTER making some test calls
"""
import requests

try:
    response = requests.get('http://localhost:8000/metrics', timeout=5)
    if response.status_code == 200:
        lines = response.text.split('\n')

        # Filter for Nevox metrics
        nevox_metrics = [line for line in lines if 'nevox_' in line]

        if nevox_metrics:
            print("✅ Nevox Metrics Found!\n")
            print("=" * 80)

            # Group by metric type
            costs = [m for m in nevox_metrics if 'cost' in m or 'savings' in m]
            tokens = [m for m in nevox_metrics if 'token' in m or 'character' in m]
            calls = [m for m in nevox_metrics if 'call' in m and 'cost' not in m]

            if costs:
                print("\n💰 COST METRICS:")
                print("-" * 80)
                for line in costs:
                    if not line.startswith('#'):
                        print(line)

            if tokens:
                print("\n📊 TOKEN USAGE METRICS:")
                print("-" * 80)
                for line in tokens:
                    if not line.startswith('#'):
                        print(line)

            if calls:
                print("\n📞 CALL METRICS:")
                print("-" * 80)
                for line in calls:
                    if not line.startswith('#'):
                        print(line)

            print("\n" + "=" * 80)
            print(f"\n📈 Total Nevox metrics: {len([m for m in nevox_metrics if not m.startswith('#')])}")

        else:
            print("⚠️ No Nevox metrics found yet!")
            print("   Make a test call first, then run this script again.")
            print("\n💡 Tip: Run your agent with: python agent-after-promotheus.py console")
    else:
        print(f"❌ Got status code: {response.status_code}")

except requests.exceptions.ConnectionRefusedError:
    print("❌ Connection refused - metrics server not running!")
    print("   Make sure your agent is running with: python agent-after-promotheus.py console")
except Exception as e:
    print(f"❌ Error: {e}")
