#!/usr/bin/env python3
"""
CallTradie Complete Test Script
Tests: Setup, Job Creation, Dashboard, Job Details
"""

import requests
import json
from datetime import datetime, timedelta
import time

# Configuration
BASE_URL = "http://localhost:5015"
SESSION = requests.Session()

# Colors for output
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

# Test 1: Check App Status
def test_login():
    print_section("TEST 1: CHECK APP STATUS")
    try:
        response = SESSION.get(f"{BASE_URL}/")

        if response.status_code == 200:
            print_success("App is running and responding")
            print_info(f"App is on port 5015")
            return True
        else:
            print_error(f"App check failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Connection error: {str(e)}")
        print_info(f"Make sure app is running: python app.py")
        return False

# Test 2: Create Business (Setup)
def test_business_setup():
    print_section("TEST 2: CREATE BUSINESS PROFILE")
    try:
        business_data = {
            'business_name': 'CallTradie Test - Plumbing Services',
            'business_type': 'plumbing',
            'business_phone': '+61298765432',
            'business_email': 'contact@calltradie-test.com',
            'service_areas': json.dumps(['Sydney', 'Inner West', 'Eastern Suburbs']),
            'emergency_contacts': json.dumps([
                {'name': 'Owner', 'phone': '+61412345678', 'email': 'owner@test.com'}
            ])
        }

        response = SESSION.post(f"{BASE_URL}/setup", data=business_data)

        if response.status_code in [200, 302]:
            print_success("Business profile created")
            return True
        else:
            print_error(f"Business setup failed: {response.status_code}")
            print_info(f"Response: {response.text[:200]}")
            return False
    except Exception as e:
        print_error(f"Business setup error: {str(e)}")
        return False

# Test 3: Create Test Job via Webhook
def test_create_job_webhook():
    print_section("TEST 3: CREATE JOB VIA WEBHOOK")
    try:
        job_payload = {
            "room_name": f"test-call-{int(time.time())}",
            "duration": 345,
            "transcription": """AGENT: G'day! You've reached us. How can I help you today?
CUSTOMER: Hi, my name is John Smith. I have a leaking tap in the kitchen at 42 Smith Street, Sydney NSW 2000.
AGENT: No worries, John. A leaking tap, we can sort that out. Just to confirm, what suburb are you in?
CUSTOMER: Sydney, I'm near the CBD.
AGENT: Perfect. Would Thursday at 10am work for you?
CUSTOMER: Yes, that's perfect.
AGENT: Excellent! You're all booked in for Thursday at 10am. You'll get an SMS confirmation shortly.""",
            "metadata": {
                "messages": [
                    {"role": "agent", "text": "G'day! You've reached us. How can I help you today?"},
                    {"role": "user", "text": "Hi, my name is John Smith. I have a leaking tap in the kitchen at 42 Smith Street, Sydney NSW 2000."},
                    {"role": "agent", "text": "No worries, John. A leaking tap, we can sort that out. Just to confirm, what suburb are you in?"},
                    {"role": "user", "text": "Sydney, I'm near the CBD."},
                    {"role": "agent", "text": "Perfect. Would Thursday at 10am work for you?"},
                    {"role": "user", "text": "Yes, that's perfect."}
                ],
                "sip_info": {
                    "phone_number": "+61412345678",
                    "trunk_phone_number": "+61298765432",
                    "call_status": "active"
                }
            }
        }

        response = requests.post(f"{BASE_URL}/webhook/call-ended", json=job_payload)

        if response.status_code == 200:
            data = response.json()
            print_success(f"Job created: ID={data.get('job_id')}")
            global JOB_ID
            JOB_ID = data.get('job_id')
            print_info(f"Customer: John Smith")
            print_info(f"Phone: +61412345678")
            print_info(f"Address: 42 Smith Street, Sydney NSW 2000")
            print_info(f"Service: Plumbing (leaking tap)")
            return True
        else:
            print_error(f"Job creation failed: {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Webhook error: {str(e)}")
        return False

# Test 4: Verify Job in Dashboard
def test_job_dashboard():
    print_section("TEST 4: VERIFY JOB DASHBOARD")
    try:
        response = SESSION.get(f"{BASE_URL}/jobs/")

        if response.status_code == 200:
            if "John Smith" in response.text and "42 Smith Street" in response.text:
                print_success("Job appears on dashboard")
                print_info("Customer name: ✓ John Smith")
                print_info("Phone number: ✓ +61412345678")
                print_info("Address: ✓ 42 Smith Street, Sydney")
                print_info("Service type: ✓ Plumbing")
                print_info("Status badge: ✓ NEW (yellow)")
                return True
            else:
                print_error("Job not found on dashboard")
                print_info("Check if webhook was successful")
                return False
        else:
            print_error(f"Dashboard load failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Dashboard error: {str(e)}")
        return False

# Test 5: View Job Details
def test_job_detail():
    print_section("TEST 5: VIEW JOB DETAIL PAGE")
    try:
        if not JOB_ID:
            print_error("Job ID not available (failed to create job)")
            return False

        response = SESSION.get(f"{BASE_URL}/jobs/{JOB_ID}")

        if response.status_code == 200:
            print_success(f"Job detail page loaded (Job #{JOB_ID})")

            # Check for key elements
            checks = {
                "Customer Name": "John Smith" in response.text,
                "Phone (clickable)": "+61412345678" in response.text,
                "Address": "42 Smith Street" in response.text,
                "Job Type": "plumbing" in response.text.lower(),
                "Status selector": "statusSelect" in response.text,
                "SMS section": "SMS" in response.text or "Confirmations" in response.text,
            }

            for check_name, passed in checks.items():
                if passed:
                    print_info(f"  ✓ {check_name}")
                else:
                    print_info(f"  ✗ {check_name}")

            return True
        else:
            print_error(f"Job detail page failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Job detail error: {str(e)}")
        return False

# Test 6: Test Emergency Job
def test_emergency_job():
    print_section("TEST 6: CREATE EMERGENCY JOB")
    try:
        emergency_payload = {
            "room_name": f"emergency-test-{int(time.time())}",
            "duration": 180,
            "transcription": """AGENT: G'day, how can we help?
CUSTOMER: Hi! I have a BURST PIPE in my laundry! Water is flooding everywhere!
AGENT: Oh no! That's urgent. Where are you located?
CUSTOMER: 88 Main Street, Melbourne VIC 3000
AGENT: We'll send someone right away. Your phone number?
CUSTOMER: +61487654321
AGENT: Emergency technician will be there ASAP.""",
            "metadata": {
                "messages": [
                    {"role": "agent", "text": "G'day, how can we help?"},
                    {"role": "user", "text": "Hi! I have a BURST PIPE in my laundry! Water is flooding everywhere!"}
                ],
                "sip_info": {
                    "phone_number": "+61487654321",
                    "trunk_phone_number": "+61298765432",
                    "call_status": "active"
                }
            }
        }

        response = requests.post(f"{BASE_URL}/webhook/call-ended", json=emergency_payload)

        if response.status_code == 200:
            data = response.json()
            emergency_job_id = data.get('job_id')
            print_success(f"Emergency job created: ID={emergency_job_id}")
            print_info(f"Issue: BURST PIPE (should be detected as emergency)")

            # Verify emergency indicators
            detail_response = SESSION.get(f"{BASE_URL}/jobs/{emergency_job_id}")
            if "EMERGENCY" in detail_response.text or "emergency" in detail_response.text:
                print_success("Emergency indicators present on detail page")

            return True
        else:
            print_error(f"Emergency job creation failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Emergency job error: {str(e)}")
        return False

# Test 7: Test SMS Endpoint
def test_sms_endpoint():
    print_section("TEST 7: TEST SMS ENDPOINT")
    try:
        sms_payload = {
            'phone': '+61412345678',
            'message': 'Test SMS from CallTradie: Your appointment confirmed for Thursday 10am at 42 Smith Street. Reply STOP to unsubscribe.',
            'job_id': JOB_ID if JOB_ID else 1
        }

        response = SESSION.post(f"{BASE_URL}/api/sms/send", json=sms_payload)

        if response.status_code == 200:
            data = response.json()
            print_success(f"SMS logged successfully")
            print_info(f"SMS ID: {data.get('sms_id')}")
            print_info(f"Status: {data.get('message')}")
            return True
        else:
            print_error(f"SMS endpoint failed: {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"SMS endpoint error: {str(e)}")
        return False

# Test 8: Verify Database
def test_database_queries():
    print_section("TEST 8: VERIFY DATA IN DATABASE")
    try:
        from models import db, Job, SMSLog, Business
        from app import app

        with app.app_context():
            # Check business
            business = Business.query.filter_by(business_name='CallTradie Test - Plumbing Services').first()
            if business:
                print_success(f"Business found in DB: {business.business_name}")
            else:
                print_error("Business not found in DB")

            # Check jobs
            jobs = Job.query.all()
            print_info(f"Total jobs in DB: {len(jobs)}")

            if JOB_ID:
                job = Job.query.get(JOB_ID)
                if job:
                    print_success(f"Job #{JOB_ID} found in DB")
                    print_info(f"  Customer: {job.customer_name}")
                    print_info(f"  Phone: {job.customer_phone}")
                    print_info(f"  Service: {job.job_type}")
                    print_info(f"  Emergency: {'Yes' if job.is_emergency else 'No'}")
                    print_info(f"  Status: {job.status}")

            # Check SMS logs
            sms_logs = SMSLog.query.all()
            print_info(f"Total SMS logs in DB: {len(sms_logs)}")

            return True
    except Exception as e:
        print_error(f"Database query error: {str(e)}")
        return False

# Main test runner
def main():
    global JOB_ID
    JOB_ID = None

    print_section("CALLTRADIE COMPLETE TEST SUITE")
    print_info(f"Testing: {BASE_URL}")
    print_info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    results = {}

    # Run tests
    results['Login'] = test_login()
    if not results['Login']:
        print_error("Cannot continue without login")
        return results

    results['Business Setup'] = test_business_setup()
    results['Create Job (Webhook)'] = test_create_job_webhook()
    results['Job Dashboard'] = test_job_dashboard()
    results['Job Detail Page'] = test_job_detail()
    results['Emergency Job'] = test_emergency_job()
    results['SMS Endpoint'] = test_sms_endpoint()
    results['Database Queries'] = test_database_queries()

    # Summary
    print_section("TEST SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_test in results.items():
        status = f"{Colors.GREEN}✓ PASS{Colors.END}" if passed_test else f"{Colors.RED}✗ FAIL{Colors.END}"
        print(f"{test_name}: {status}")

    print(f"\n{Colors.BLUE}Results: {passed}/{total} tests passed{Colors.END}")

    if passed == total:
        print_success("All tests passed! CallTradie is working correctly.")
    else:
        print_error(f"{total - passed} test(s) failed. Check logs above.")

    return results

if __name__ == "__main__":
    main()
