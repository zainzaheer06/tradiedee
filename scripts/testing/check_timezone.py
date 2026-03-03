"""
Check server timezone and datetime settings
Run this to verify timezone configuration
"""
import os
import time
from datetime import datetime, timezone, timedelta
from models import db, CallLog
from app import app

def check_timezone():
    """Check server and application timezone settings"""

    print("=" * 60)
    print("TIMEZONE CHECK - Saudi Arabia Server")
    print("=" * 60)

    # 1. Server Timezone
    print("\n1. SERVER TIMEZONE:")
    print(f"   TZ Environment Variable: {os.environ.get('TZ', 'Not Set')}")
    print(f"   System Timezone (time.tzname): {time.tzname}")
    print(f"   Daylight Saving Time: {time.daylight}")

    # 2. Current Times
    print("\n2. CURRENT TIMES:")
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now()
    saudi_tz = timezone(timedelta(hours=3))
    now_saudi = datetime.now(saudi_tz)

    print(f"   UTC Time:         {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"   Server Local:     {now_local.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Saudi (UTC+3):    {now_saudi.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"   Time Difference:  UTC+{(now_local.hour - now_utc.hour) % 24} hours")

    # 3. Database Check
    print("\n3. DATABASE TIMES:")
    with app.app_context():
        # Get latest call log
        latest_call = CallLog.query.order_by(CallLog.created_at.desc()).first()
        if latest_call:
            print(f"   Latest Call Log Time: {latest_call.created_at}")
            print(f"   Timezone Info: {latest_call.created_at.tzinfo}")

            # Show in different formats
            print(f"   \nFormatted:")
            print(f"   - As stored: {latest_call.created_at}")
            print(f"   - Saudi time (if UTC): {latest_call.created_at + timedelta(hours=3)}")
        else:
            print("   No call logs found in database")

    # 4. Python datetime defaults
    print("\n4. PYTHON DATETIME:")
    test_time = datetime.now()
    print(f"   datetime.now():           {test_time}")
    print(f"   datetime.now().tzinfo:    {test_time.tzinfo}")

    test_time_utc = datetime.now(timezone.utc)
    print(f"   datetime.now(timezone.utc): {test_time_utc}")

    saudi_tz = timezone(timedelta(hours=3))
    test_time_saudi = datetime.now(saudi_tz)
    print(f"   datetime.now(Saudi TZ):   {test_time_saudi}")

    # 5. Recommendations
    print("\n5. RECOMMENDATIONS:")
    hour_diff = (now_local.hour - now_utc.hour) % 24

    if hour_diff == 3:
        print("   ✓ Server is already in Saudi timezone (UTC+3)")
        print("   → You can use datetime.now() without timezone conversion")
        print("   → Current code using timezone.utc adds 3 hours offset")
    elif hour_diff == 0:
        print("   ✗ Server is in UTC timezone")
        print("   → Need to convert all times to Saudi (UTC+3)")
        print("   → Or set server timezone to Asia/Riyadh")
    else:
        print(f"   ? Server is in UTC+{hour_diff} timezone")
        print("   → Verify this is correct for Saudi Arabia")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    check_timezone()
