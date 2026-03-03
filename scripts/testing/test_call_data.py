"""Quick script to check the latest call log data"""
from app import app, db, CallLog

with app.app_context():
    # Get the latest call log
    latest_call = CallLog.query.order_by(CallLog.id.desc()).first()

    if latest_call:
        print("=" * 50)
        print("LATEST CALL LOG")
        print("=" * 50)
        print(f"ID: {latest_call.id}")
        print(f"Room Name: {latest_call.room_name}")
        print(f"To Number: {latest_call.to_number}")
        print(f"Duration: {latest_call.duration_seconds} seconds")
        print(f"Minutes Used: {latest_call.minutes_used}")
        print(f"Status: {latest_call.status}")
        print(f"Created: {latest_call.created_at}")
        print(f"\nTranscription:")
        print("-" * 50)
        if latest_call.transcription:
            print(latest_call.transcription)
        else:
            print("(No transcription)")
        print("-" * 50)
    else:
        print("No call logs found")
