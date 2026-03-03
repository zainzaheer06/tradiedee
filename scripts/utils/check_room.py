#!/usr/bin/env python3
"""
Emergency LiveKit Room Cleanup Script
Deletes all active rooms to prevent billing charges
"""

import asyncio
import os
import sys
import argparse
from dotenv import load_dotenv
from livekit.api import LiveKitAPI, ListRoomsRequest, DeleteRoomRequest

# Load environment variables
load_dotenv()

async def list_rooms(lkapi):
    """List all active rooms"""
    try:
        response = await lkapi.room.list_rooms(ListRoomsRequest())
        # The response has a 'rooms' attribute containing the list
        return response.rooms if hasattr(response, 'rooms') else []
    except Exception as e:
        print(f"❌ Error listing rooms: {e}")
        return []

async def delete_room(lkapi, room_name):
    """Delete a specific room"""
    try:
        await lkapi.room.delete_room(DeleteRoomRequest(room=room_name))
        print(f"✅ Deleted room: {room_name}")
        return True
    except Exception as e:
        print(f"❌ Failed to delete room {room_name}: {e}")
        return False

async def cleanup_all_rooms(force=False):
    """Clean up all active LiveKit rooms"""
    print("🧹 LiveKit Room Cleanup Tool")
    print("=" * 40)
    
    # Initialize LiveKit API client
    try:
        async with LiveKitAPI() as lkapi:
            # List all rooms
            print("📋 Listing active rooms...")
            rooms = await list_rooms(lkapi)
            
            if not rooms:
                print("✅ No active rooms found!")
                return
            
            print(f"🔍 Found {len(rooms)} active room(s):")
            for i, room in enumerate(rooms, 1):
                participants = getattr(room, 'num_participants', 0)
                created_at = getattr(room, 'creation_time', 'unknown')
                print(f"   {i}. {room.name} ({participants} participants, created: {created_at})")
            
            # Confirm deletion unless force mode
            if not force:
                print("\n⚠️  This will DELETE ALL ROOMS and disconnect all participants!")
                confirm = input("Type 'DELETE ALL' to confirm: ").strip()
                if confirm != "DELETE ALL":
                    print("❌ Cancelled - rooms NOT deleted")
                    return
            
            # Delete all rooms
            print(f"\n🗑️  Deleting {len(rooms)} room(s)...")
            deleted_count = 0
            failed_count = 0
            
            for room in rooms:
                success = await delete_room(lkapi, room.name)
                if success:
                    deleted_count += 1
                else:
                    failed_count += 1
            
            # Summary
            print("\n" + "=" * 40)
            print(f"✅ Successfully deleted: {deleted_count} rooms")
            if failed_count > 0:
                print(f"❌ Failed to delete: {failed_count} rooms")
            else:
                print("🎉 All rooms cleaned up successfully!")
            
    except Exception as e:
        print(f"❌ Critical error: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Clean up LiveKit rooms to prevent billing charges")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--list-only", action="store_true", help="Only list rooms, don't delete")
    
    args = parser.parse_args()
    
    # Check environment variables
    required_vars = ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file")
        sys.exit(1)
    
    if args.list_only:
        # List rooms only
        async def list_only():
            async with LiveKitAPI() as lkapi:
                rooms = await list_rooms(lkapi)
                if rooms:
                    print(f"Active rooms ({len(rooms)}):")
                    for room in rooms:
                        print(f"  - {room.name}")
                else:
                    print("No active rooms")
        
        asyncio.run(list_only())
    else:
        # Clean up rooms
        asyncio.run(cleanup_all_rooms(force=args.force))

if __name__ == "__main__":
    main()