"""
Quick test to verify Prometheus metrics endpoint is working
Run this AFTER starting your agent
"""
import requests

try:
    response = requests.get('http://localhost:8000/metrics', timeout=5)
    if response.status_code == 200:
        print("✅ Metrics endpoint is working!")
        print(f"\n📊 Metrics preview (first 1000 chars):\n")
        print(response.text[:1000])
        print("\n...")
        print(f"\n📈 Total response size: {len(response.text)} bytes")
    else:
        print(f"❌ Got status code: {response.status_code}")
except requests.exceptions.ConnectionRefusedError:
    print("❌ Connection refused - metrics server not running!")
    print("   Make sure your agent is running with: python agent-after-promotheus.py console")
except Exception as e:
    print(f"❌ Error: {e}")
