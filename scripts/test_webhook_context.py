"""
Test script for webhook context functionality
Tests the new webhook_context feature in agent-server_api.py

Usage:
    python scripts/test_webhook_context.py
"""

import requests
import json
import time
from datetime import datetime, timezone, timedelta

# Configuration
API_BASE_URL = "http://localhost:5004"
API_KEY = "nvx_4605812f0577221e98d6ada9befd5f18"
AGENT_ID = 74

# Saudi Arabia Timezone
SAUDI_TZ = timezone(timedelta(hours=3))

class WebhookContextTester:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key
        }
        self.test_results = []

    def log(self, message, level="INFO"):
        """Log test messages"""
        timestamp = datetime.now(SAUDI_TZ).strftime("%H:%M:%S")
        prefix = f"[{timestamp}] [{level}]"
        print(f"{prefix} {message}")

    def test_api_health(self):
        """Test if API is running"""
        self.log("Testing API health...", "TEST")
        try:
            response = requests.get(f"{self.base_url}/api/v1/health", timeout=5)
            if response.status_code == 200:
                self.log("✅ API is healthy", "PASS")
                self.test_results.append(("API Health", "PASS"))
                print(f"   Response: {response.json()}\n")
                return True
            else:
                self.log(f"❌ API returned status {response.status_code}", "FAIL")
                self.test_results.append(("API Health", "FAIL"))
                return False
        except Exception as e:
            self.log(f"❌ API unreachable: {e}", "FAIL")
            self.test_results.append(("API Health", "FAIL"))
            return False

    def test_with_context(self):
        """Test outbound call WITH webhook context"""
        self.log("TEST 1: Outbound call WITH webhook context", "TEST")

        payload = {
            "agent_id": AGENT_ID,
            "phone_number": "923354646825",
            "context": {
                "customer_name": "زين",
                "order_id": "ORD-2024-001",
                "service_type": "Internet Subscription",
                "status": "Active",
                "payment_status": "Pending"
            }
        }

        self.log(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}", "DEBUG")

        try:
            response = requests.post(
                f"{self.base_url}/api/v1/calls/outbound",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            print(f"\nStatus Code: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}\n")

            if response.status_code == 200:
                data = response.json()
                self.log(f"✅ Call initiated successfully", "PASS")
                self.log(f"   Call ID: {data.get('call_id')}", "INFO")
                self.log(f"   Room: {data.get('room_name')}", "INFO")
                self.log(f"   Status: {data.get('status')}", "INFO")
                self.test_results.append(("Call with Context", "PASS"))
                print(f"   Full Response: {json.dumps(data, indent=2)}\n")
                return True
            else:
                self.log(f"❌ Failed with status {response.status_code}", "FAIL")
                self.log(f"   Error: {response.text}", "INFO")
                self.test_results.append(("Call with Context", "FAIL"))
                return False
        except Exception as e:
            self.log(f"❌ Request failed: {e}", "FAIL")
            self.test_results.append(("Call with Context", "FAIL"))
            return False

    def test_without_context(self):
        """Test outbound call WITHOUT webhook context"""
        self.log("TEST 2: Outbound call WITHOUT webhook context", "TEST")

        payload = {
            "agent_id": AGENT_ID,
            "phone_number": "966509876543"
        }

        self.log(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}", "DEBUG")

        try:
            response = requests.post(
                f"{self.base_url}/api/v1/calls/outbound",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            print(f"\nStatus Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                self.log(f"✅ Call initiated successfully (no context)", "PASS")
                self.log(f"   Call ID: {data.get('call_id')}", "INFO")
                self.test_results.append(("Call without Context", "PASS"))
                print(f"   Full Response: {json.dumps(data, indent=2)}\n")
                return True
            else:
                self.log(f"❌ Failed with status {response.status_code}", "FAIL")
                self.test_results.append(("Call without Context", "FAIL"))
                return False
        except Exception as e:
            self.log(f"❌ Request failed: {e}", "FAIL")
            self.test_results.append(("Call without Context", "FAIL"))
            return False


    def test_list_agents(self):
        """Test listing agents"""
        self.log("TEST 6: List agents", "TEST")

        try:
            response = requests.get(
                f"{self.base_url}/api/v1/agents",
                headers=self.headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                agents = data.get('agents', [])
                self.log(f"✅ Retrieved {len(agents)} agents", "PASS")
                for agent in agents[:3]:  # Show first 3
                    self.log(f"   - ID: {agent.get('id')}, Name: {agent.get('name')}", "INFO")
                self.test_results.append(("List Agents", "PASS"))
                print()
                return True
            else:
                self.log(f"❌ Failed with status {response.status_code}", "FAIL")
                self.test_results.append(("List Agents", "FAIL"))
                return False
        except Exception as e:
            self.log(f"❌ Request failed: {e}", "FAIL")
            self.test_results.append(("List Agents", "FAIL"))
            return False

    def run_all_tests(self):
        """Run all tests"""
        print("=" * 80)
        print("🧪 WEBHOOK CONTEXT TEST SUITE")
        print("=" * 80)
        print()

        # Run tests in order
        if not self.test_api_health():
            self.log("⚠️  Skipping other tests - API not available", "WARNING")
            self.print_summary()
            return

        #time.sleep(1)
        #self.test_list_agents()

        time.sleep(1)
        self.test_with_context()

        #time.sleep(1)
        #self.test_without_context()

        #self.print_summary()

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("📊 TEST SUMMARY")
        print("=" * 80)
        print()

        passed = sum(1 for _, result in self.test_results if result == "PASS")
        failed = sum(1 for _, result in self.test_results if result == "FAIL")

        for test_name, result in self.test_results:
            status = "✅" if result == "PASS" else "❌"
            print(f"{status} {test_name}: {result}")

        print()
        print(f"Total: {len(self.test_results)} tests")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed / len(self.test_results) * 100):.1f}%")
        print()

        if failed == 0:
            print("🎉 All tests passed! Webhook context is working correctly!")
        else:
            print("⚠️  Some tests failed. Check the output above for details.")

        print("=" * 80)


def main():
    """Main entry point"""
    print("\n🚀 Starting Webhook Context Tests\n")
    print(f"API URL: {API_BASE_URL}")
    print(f"Agent ID: {AGENT_ID}")
    print()

    tester = WebhookContextTester(API_BASE_URL, API_KEY)
    tester.run_all_tests()


if __name__ == "__main__":
    main()
