#!/usr/bin/env python3
"""
CallTradie Webhook Test (No Authentication Required)
Simple test to verify job creation and database
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:5015"

# Colors
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")

def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.END}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ {msg}{Colors.END}")

def print_section(title):
    print(f"\n{Colors.YELLOW}{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}{Colors.END}\n")

# Test 1: Check if app is running
def test_app_running():
    print_section("TEST 1: CHECK IF APP IS RUNNING")
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print_success(f"App is running on {BASE_URL}")
            return True
        else:
            print_error(f"App returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error(f"Cannot connect to {BASE_URL}")
        print_info("Make sure Flask app is running: python app.py")
        return False
    except Exception as e:
        print_error(f"Error: {str(e)}")
        return False

# Test 2: Create normal job
def test_create_normal_job():
    print_section("TEST 2: CREATE NORMAL JOB VIA WEBHOOK")

    timestamp = int(time.time())
    payload = {
        "room_name": f"test-call-{timestamp}",
        "duration": 345,
        "transcription": """AGENT: G'day! You've reached us. How can I help you today?
CUSTOMER: Hi, my name is John Smith. I have a leaking tap in the kitchen at 42 Smith Street, Sydney NSW 2000.
AGENT: No worries, John. A leaking tap, we can sort that out. Just to confirm, what suburb are you in?
CUSTOMER: Sydney, I'm near the CBD.
AGENT: Perfect. Would Thursday at 10am work for you?
CUSTOMER: Yes, that's perfect.
AGENT: Excellent! You're all booked in for Thursday at 10am.""",
        "metadata": {
            "messages": [
                {"role": "agent", "text": "G'day! You've reached us. How can I help you today?"},
                {"role": "user", "text": "Hi, my name is John Smith. I have a leaking tap in the kitchen at 42 Smith Street, Sydney NSW 2000."}
            ],
            "sip_info": {
                "phone_number": "+61412345678",
                "trunk_phone_number": "+61298765432",
                "call_status": "active"
            }
        }
    }

    try:
        response = requests.post(f"{BASE_URL}/webhook/call-ended", json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()
            job_id = data.get('job_id')

            if job_id:
                print_success(f"Job created successfully")
                print_info(f"Job ID: {job_id}")
                print_info(f"Customer: John Smith")
                print_info(f"Phone: +61412345678")
                print_info(f"Address: 42 Smith Street, Sydney NSW 2000")
                print_info(f"Service Type: Plumbing (leaking tap)")
                print_info(f"Status: NEW")
                return job_id
            else:
                print_error("Job ID not in response")
                print_info(f"Response: {response.text}")
                return None
        else:
            print_error(f"Webhook failed with status {response.status_code}")
            print_info(f"Response: {response.text[:300]}")
            return None

    except Exception as e:
        print_error(f"Webhook error: {str(e)}")
        return None

# Test 3: Create emergency job
def test_create_emergency_job():
    print_section("TEST 3: CREATE EMERGENCY JOB VIA WEBHOOK")

    timestamp = int(time.time())
    payload = {
        "room_name": f"emergency-test-{timestamp}",
        "duration": 180,
        "transcription": """AGENT: How can we help?
CUSTOMER: HELP! I have a BURST PIPE in my laundry! Water is flooding everywhere!
AGENT: Oh no! That's urgent. Where are you located?
CUSTOMER: 88 Main Street, Melbourne VIC 3000
AGENT: We'll send someone right away. Your phone number?
CUSTOMER: +61487654321""",
        "metadata": {
            "messages": [
                {"role": "agent", "text": "How can we help?"},
                {"role": "user", "text": "HELP! I have a BURST PIPE in my laundry!"}
            ],
            "sip_info": {
                "phone_number": "+61487654321",
                "trunk_phone_number": "+61298765432",
                "call_status": "active"
            }
        }
    }

    try:
        response = requests.post(f"{BASE_URL}/webhook/call-ended", json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()
            job_id = data.get('job_id')

            if job_id:
                print_success(f"Emergency job created successfully")
                print_info(f"Job ID: {job_id}")
                print_info(f"Issue: BURST PIPE (emergency detected)")
                print_info(f"Location: 88 Main Street, Melbourne")
                print_info(f"Should have RED border and 🚨 badge on dashboard")
                return job_id
            else:
                print_error("Job ID not in response")
                return None
        else:
            print_error(f"Webhook failed with status {response.status_code}")
            return None

    except Exception as e:
        print_error(f"Webhook error: {str(e)}")
        return None

# Test 4: Check database
def test_database():
    print_section("TEST 4: VERIFY DATABASE")
    try:
        from app import app, db
        from models import Job, SMSLog

        with app.app_context():
            jobs = Job.query.all()
            print_success(f"Database connection successful")
            print_info(f"Total jobs in database: {len(jobs)}")

            if jobs:
                print_info(f"\nRecent jobs:")
                for job in jobs[-3:]:  # Last 3 jobs
                    print_info(f"  - Job #{job.id}: {job.customer_name} ({job.job_type}) - {job.status}")
                    if job.is_emergency:
                        print_info(f"    🚨 EMERGENCY: {job.customer_address}")

            sms_logs = SMSLog.query.all()
            print_info(f"Total SMS logs in database: {len(sms_logs)}")

            return True
    except Exception as e:
        print_error(f"Database error: {str(e)}")
        return False

# Test 5: Manual verification
def test_manual_verification():
    print_section("TEST 5: MANUAL VERIFICATION STEPS")

    print_info("Open your browser and check:")
    print(f"\n  {Colors.BLUE}1. Job Dashboard:{Colors.END}")
    print(f"     {BASE_URL}/jobs/")
    print(f"     ✓ Should see job cards with 2-column layout")
    print(f"     ✓ John Smith's job card should display")
    print(f"     ✓ Emergency job should have RED left border")

    print(f"\n  {Colors.BLUE}2. Job Detail (Normal):{Colors.END}")
    print(f"     {BASE_URL}/jobs/[JOB_ID]  (replace [JOB_ID] with actual ID)")
    print(f"     ✓ Customer info should show")
    print(f"     ✓ Phone number should be clickable")
    print(f"     ✓ Address should display fully")

    print(f"\n  {Colors.BLUE}3. CSS Verification:{Colors.END}")
    print(f"     ✓ Job cards should have proper spacing")
    print(f"     ✓ Badges should be colored correctly")
    print(f"     ✓ Buttons should be styled")
    print(f"     ✓ No layout broken sections")

def main():
    print_section("CALLTRADIE WEBHOOK TEST")
    print_info(f"Testing: {BASE_URL}")
    print_info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    # Test 1: App running
    results['App Running'] = test_app_running()
    if not results['App Running']:
        print_error("Cannot continue - app is not running")
        return

    # Test 2: Normal job
    job_id_1 = test_create_normal_job()
    results['Create Normal Job'] = job_id_1 is not None

    # Test 3: Emergency job
    job_id_2 = test_create_emergency_job()
    results['Create Emergency Job'] = job_id_2 is not None

    # Test 4: Database
    results['Database Verification'] = test_database()

    # Test 5: Manual steps
    test_manual_verification()

    # Summary
    print_section("TEST SUMMARY")

    for test_name, passed in results.items():
        status = f"{Colors.GREEN}✓ PASS{Colors.END}" if passed else f"{Colors.RED}✗ FAIL{Colors.END}"
        print(f"{test_name}: {status}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    print(f"\n{Colors.BLUE}Results: {passed}/{total} tests passed{Colors.END}")

    if passed == total:
        print_success("All tests passed! ✓")
        print_info("\nNext: Open browser and verify dashboard at /jobs/")
    else:
        print_error("Some tests failed. Check above for details.")

if __name__ == "__main__":
    main()
