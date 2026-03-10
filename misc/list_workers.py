import asyncio
import os
from livekit import api
from dotenv import load_dotenv

async def list_workers():
    load_dotenv(".env")

    lkapi = api.LiveKitAPI(
        url=os.environ.get("LIVEKIT_URL"),
        api_key=os.environ.get("LIVEKIT_API_KEY"),
        api_secret=os.environ.get("LIVEKIT_API_SECRET")
    )

    # List all active rooms
    print("=" * 60)
    print("ACTIVE ROOMS:")
    print("=" * 60)
    try:
        rooms = await lkapi.room.list_rooms(api.ListRoomsRequest())
        if rooms.rooms:
            for room in rooms.rooms:
                print(f"  Room: {room.name} | Participants: {room.num_participants} | ID: {room.sid}")
        else:
            print("  No active rooms")
    except Exception as e:
        print(f"  Error listing rooms: {e}")

    # List SIP dispatch rules
    print("\n" + "=" * 60)
    print("SIP DISPATCH RULES:")
    print("=" * 60)
    try:
        rules = await lkapi.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())
        if rules.items:
            for rule in rules.items:
                print(f"  ID: {rule.sip_dispatch_rule_id}")
                print(f"  Name: {rule.name}")
                print(f"  Trunk IDs: {rule.trunk_ids}")
                if rule.rule and rule.rule.dispatch_rule_individual:
                    print(f"  Room Prefix: {rule.rule.dispatch_rule_individual.room_prefix}")
                if rule.room_config and rule.room_config.agents:
                    for agent in rule.room_config.agents:
                        print(f"  Agent Name: {agent.agent_name}")
                print("  ---")
        else:
            print("  No dispatch rules found")
    except Exception as e:
        print(f"  Error listing dispatch rules: {e}")

    # List SIP trunks
    print("\n" + "=" * 60)
    print("SIP INBOUND TRUNKS:")
    print("=" * 60)
    try:
        trunks = await lkapi.sip.list_sip_inbound_trunk(api.ListSIPInboundTrunkRequest())
        if trunks.items:
            for trunk in trunks.items:
                print(f"  ID: {trunk.sip_trunk_id} | Name: {trunk.name}")
                print(f"  Numbers: {trunk.numbers}")
                print("  ---")
        else:
            print("  No inbound trunks")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n" + "=" * 60)
    print(f"Connected to: {os.environ.get('LIVEKIT_URL')}")
    print("=" * 60)

    await lkapi.aclose()

if __name__ == "__main__":
    asyncio.run(list_workers())
