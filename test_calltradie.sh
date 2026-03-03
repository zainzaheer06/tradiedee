#!/bin/bash

# CallTradie Quick Test Script (Bash/Curl)
# Fast testing without Python dependencies

BASE_URL="http://localhost:5015"
TIMESTAMP=$(date +%s)

echo "================================================"
echo "  CallTradie API Test Script"
echo "================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test 1: Check if app is running
echo -e "${BLUE}TEST 1: Check if app is running${NC}"
if curl -s "$BASE_URL/" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ App is running on $BASE_URL${NC}"
else
    echo -e "${RED}✗ App is not running. Start it with: python app.py${NC}"
    exit 1
fi
echo ""

# Test 2: Create job via webhook
echo -e "${BLUE}TEST 2: Create job via webhook${NC}"
RESPONSE=$(curl -s -X POST "$BASE_URL/webhook/call-ended" \
  -H "Content-Type: application/json" \
  -d '{
    "room_name": "test-call-'$TIMESTAMP'",
    "duration": 345,
    "transcription": "AGENT: G'"'"'day! CUSTOMER: Hi, I am John Smith and I have a leaking tap at 42 Smith Street, Sydney NSW 2000",
    "metadata": {
      "messages": [
        {"role": "agent", "text": "G'"'"'day!"},
        {"role": "user", "text": "Hi, I am John Smith and I have a leaking tap at 42 Smith Street, Sydney NSW 2000"}
      ],
      "sip_info": {
        "phone_number": "+61412345678",
        "trunk_phone_number": "+61298765432",
        "call_status": "active"
      }
    }
  }')

JOB_ID=$(echo $RESPONSE | grep -o '"job_id":[0-9]*' | grep -o '[0-9]*' | tail -1)

if [ ! -z "$JOB_ID" ]; then
    echo -e "${GREEN}✓ Job created: ID=$JOB_ID${NC}"
    echo "  Customer: John Smith"
    echo "  Phone: +61412345678"
    echo "  Address: 42 Smith Street, Sydney"
    echo "  Service: Plumbing (leaking tap)"
else
    echo -e "${RED}✗ Job creation failed${NC}"
    echo "Response: $RESPONSE"
fi
echo ""

# Test 3: Test dashboard
echo -e "${BLUE}TEST 3: Load job dashboard${NC}"
if curl -s "$BASE_URL/jobs/" | grep -q "John Smith"; then
    echo -e "${GREEN}✓ Job appears on dashboard${NC}"
else
    echo -e "${RED}✗ Job not found on dashboard${NC}"
fi
echo ""

# Test 4: Test job detail page
echo -e "${BLUE}TEST 4: Load job detail page${NC}"
if [ ! -z "$JOB_ID" ]; then
    if curl -s "$BASE_URL/jobs/$JOB_ID" | grep -q "John Smith"; then
        echo -e "${GREEN}✓ Job detail page loaded (Job #$JOB_ID)${NC}"
    else
        echo -e "${RED}✗ Job detail page failed${NC}"
    fi
else
    echo -e "${RED}✗ Cannot test job detail (no job ID)${NC}"
fi
echo ""

# Test 5: Create emergency job
echo -e "${BLUE}TEST 5: Create emergency job${NC}"
EMERGENCY=$(curl -s -X POST "$BASE_URL/webhook/call-ended" \
  -H "Content-Type: application/json" \
  -d '{
    "room_name": "emergency-test-'$TIMESTAMP'",
    "duration": 180,
    "transcription": "AGENT: Help! CUSTOMER: BURST PIPE at 88 Main Street, Melbourne!",
    "metadata": {
      "messages": [
        {"role": "user", "text": "BURST PIPE at 88 Main Street, Melbourne!"}
      ],
      "sip_info": {
        "phone_number": "+61487654321",
        "trunk_phone_number": "+61298765432",
        "call_status": "active"
      }
    }
  }')

EMERGENCY_ID=$(echo $EMERGENCY | grep -o '"job_id":[0-9]*' | grep -o '[0-9]*' | tail -1)

if [ ! -z "$EMERGENCY_ID" ]; then
    echo -e "${GREEN}✓ Emergency job created: ID=$EMERGENCY_ID${NC}"
    echo "  Issue: BURST PIPE (should have emergency indicator)"
else
    echo -e "${RED}✗ Emergency job creation failed${NC}"
fi
echo ""

# Test 6: Test SMS endpoint
echo -e "${BLUE}TEST 6: Test SMS endpoint${NC}"
SMS_RESPONSE=$(curl -s -X POST "$BASE_URL/api/sms/send" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+61412345678",
    "message": "Test SMS from CallTradie",
    "job_id": 1
  }')

if echo $SMS_RESPONSE | grep -q "success"; then
    echo -e "${GREEN}✓ SMS endpoint working${NC}"
    echo "Response: $SMS_RESPONSE"
else
    echo -e "${RED}✗ SMS endpoint failed${NC}"
    echo "Response: $SMS_RESPONSE"
fi
echo ""

# Summary
echo "================================================"
echo -e "${GREEN}✓ Basic tests completed!${NC}"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Open browser: $BASE_URL/jobs/"
echo "2. Check if job cards display correctly"
echo "3. Click 'View Details' to see full job page"
echo "4. Verify emergency indicators on emergency job"
echo ""
