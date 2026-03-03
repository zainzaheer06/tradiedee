"""
Script to list and cleanup existing LiveKit SIP dispatch rules
"""
import os
import asyncio
from livekit import api
from dotenv import load_dotenv

load_dotenv()

async def list_and_cleanup_dispatch_rules():
    """List all dispatch rules and optionally delete them"""

    livekit_api = api.LiveKitAPI(
        url=os.environ.get('LIVEKIT_URL'),
        api_key=os.environ.get('LIVEKIT_API_KEY'),
        api_secret=os.environ.get('LIVEKIT_API_SECRET')
    )

    try:
        # List all dispatch rules
        print("=" * 60)
        print("Fetching SIP Dispatch Rules...")
        print("=" * 60)

        response = await livekit_api.sip.list_sip_dispatch_rule(
            api.ListSIPDispatchRuleRequest()
        )

        if not response.items:
            print("\nNo dispatch rules found.")
            return

        print(f"\nFound {len(response.items)} dispatch rule(s):\n")

        for idx, rule in enumerate(response.items, 1):
            print(f"{idx}. Rule ID: {rule.sip_dispatch_rule_id}")
            print(f"   Name: {rule.name}")
            print(f"   Trunk IDs: {rule.trunk_ids}")
            print(f"   Metadata: {rule.metadata}")
            print()

        # Ask user if they want to delete all
        delete_all = input("\nDelete ALL dispatch rules? (yes/no): ").strip().lower()

        if delete_all == 'yes':
            print("\nDeleting all dispatch rules...")
            for rule in response.items:
                try:
                    await livekit_api.sip.delete_sip_dispatch_rule(
                        api.DeleteSIPDispatchRuleRequest(
                            sip_dispatch_rule_id=rule.sip_dispatch_rule_id
                        )
                    )
                    print(f"   Deleted: {rule.name} ({rule.sip_dispatch_rule_id})")
                except Exception as e:
                    print(f"   Error deleting {rule.sip_dispatch_rule_id}: {e}")

            print("\n[SUCCESS] All dispatch rules deleted!")
        else:
            print("\nNo changes made.")

    except Exception as e:
        print(f"\n[ERROR] Failed to list dispatch rules: {e}")

if __name__ == "__main__":
    asyncio.run(list_and_cleanup_dispatch_rules())
