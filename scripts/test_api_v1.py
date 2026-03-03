"""
Test Script for API v1 - Outbound Calls

This script tests the /api/v1/calls/outbound endpoint.

Usage:
    1. First, generate an API key from the UI (Settings > API Keys)
    2. Update API_KEY below with your key
    3. Run: python scripts/test_api_v1.py

Tests:
    1. Health check (no auth)
    2. List agents (with auth)
    3. Make outbound call (with auth)
"""
import requests
import json
import sys

# ==================== CONFIGURATION ====================

# Your API key (get from Settings > API Keys)
API_KEY = "nvx_758a88ec8597e968746d8d3677aa33d2"  # User's actual key

# Base URL of your server
BASE_URL = "http://localhost:5004"

# Test phone number
TEST_PHONE = "923354646825"

# Agent ID to use (update with your agent ID)
TEST_AGENT_ID = 51  # <-- UPDATE THIS!

# Optional context to pass to agent
TEST_CONTEXT = {
    "customer_name": "Test User",
    "order_id": "TEST-001",
    "notes": "API test call"
}

# ==================== TEST FUNCTIONS ====================

def print_header(title):
    print("\n"  "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(success, message):
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")


def test_health_check():
    """Test health check endpoint (no auth required)"""
    print_header("Test 1: Health Check")

    try:
        response = requests.get(f"{BASE_URL}/api/v1/health")
        data = response.json()

        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {json.dumps(data, indent=2)}")

        if response.status_code == 200 and data.get('status') == 'healthy':
            print_result(True, "Health check passed")
            return True
        else:
            print_result(False, "Health check failed")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


def test_list_agents():
    """Test list agents endpoint (requires auth)"""
    print_header("Test 2: List Agents")

    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/agents",
            headers={"X-API-Key": API_KEY}
        )
        data = response.json()

        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {json.dumps(data, indent=2)}")

        if response.status_code == 200 and data.get('success'):
            agents = data.get('agents', [])
            print_result(True, f"Found {len(agents)} agent(s)")

            if agents:
                print("\n   Available Agents:")
                for agent in agents:
                    print(f"   - ID: {agent['id']}, Name: {agent['name']}, Voice: {agent['voice_name']}")

            return True
        elif response.status_code == 401:
            print_result(False, "Invalid API key!")
            return False
        else:
            print_result(False, f"Failed: {data.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


def test_outbound_call():
    """Test outbound call endpoint (requires auth)"""
    print_header("Test 3: Outbound Call")

    print(f"   Phone: {TEST_PHONE}")
    print(f"   Agent ID: {TEST_AGENT_ID}")
    print(f"   Context: {json.dumps(TEST_CONTEXT)}")
    print()

    # Confirm before making call
    confirm = input("   Make this call? (yes/no): ")
    if confirm.lower() != 'yes':
        print("   Call cancelled.")
        return False

    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/calls/outbound",
            headers={
                "X-API-Key": API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "agent_id": TEST_AGENT_ID,
                "phone_number": TEST_PHONE,
                "context": TEST_CONTEXT
            }
        )
        data = response.json()

        print(f"\n   Status Code: {response.status_code}")
        print(f"   Response: {json.dumps(data, indent=2)}")

        if response.status_code == 200 and data.get('success'):
            print_result(True, f"Call initiated! ID: {data.get('call_id')}")
            print(f"\n   Call Details:")
            print(f"   - Call ID: {data.get('call_id')}")
            print(f"   - Room: {data.get('room_name')}")
            print(f"   - Status: {data.get('status')}")
            return True
        else:
            error = data.get('error', 'Unknown error')
            code = data.get('code', 'UNKNOWN')
            print_result(False, f"Failed: {error} ({code})")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


def test_invalid_api_key():
    """Test with invalid API key"""
    print_header("Test 4: Invalid API Key (should fail)")

    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/agents",
            headers={"X-API-Key": "nvx_invalid_key_12345"}
        )
        data = response.json()

        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {json.dumps(data, indent=2)}")

        if response.status_code == 401:
            print_result(True, "Correctly rejected invalid key")
            return True
        else:
            print_result(False, "Should have returned 401!")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


def test_missing_api_key():
    """Test without API key"""
    print_header("Test 5: Missing API Key (should fail)")

    try:
        response = requests.get(f"{BASE_URL}/api/v1/agents")
        data = response.json()

        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {json.dumps(data, indent=2)}")

        if response.status_code == 401:
            print_result(True, "Correctly rejected missing key")
            return True
        else:
            print_result(False, "Should have returned 401!")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


# ==================== MAIN ====================

def main():
    print("\n" + "=" * 60)
    print("   NevoxAI API v1 Test Suite")
    print("=" * 60)
    print(f"\n   Base URL: {BASE_URL}")
    print(f"   API Key: {API_KEY[:15]}..." if len(API_KEY) > 15 else f"   API Key: {API_KEY}")
    print(f"   Test Phone: {TEST_PHONE}")
    print(f"   Test Agent: {TEST_AGENT_ID}")

    results = []

    # Run tests
    #results.append(("Health Check", test_health_check()))
    #results.append(("Invalid API Key", test_invalid_api_key()))
    #results.append(("Missing API Key", test_missing_api_key()))
    #results.append(("List Agents", test_list_agents()))

    # Ask before making actual call
    print_header("Ready to test outbound call?")
    print("   This will make an ACTUAL phone call!")
    proceed = input("   Run outbound call test? (yes/no): ")

    if proceed.lower() == 'yes':
        results.append(("Outbound Call", test_outbound_call()))
    else:
        print("   Skipped outbound call test.")

    # Summary
    print_header("Test Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        icon = "✅" if result else "❌"
        print(f"   {icon} {name}")

    print(f"\n   Passed: {passed}/{total}")

    if passed == total:
        print("\n   🎉 All tests passed!")
    else:
        print("\n   ⚠️  Some tests failed. Check output above.")


if __name__ == '__main__':
    main()
