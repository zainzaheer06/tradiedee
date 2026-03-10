"""
Delete the bad dispatch rule (no agent_name, no trunk filter)
and create a proper one for agent-tradiedee.
"""
import asyncio
import os
from livekit import api
from dotenv import load_dotenv

async def fix_dispatch():
    load_dotenv(".env")

    lkapi = api.LiveKitAPI(
        url=os.environ.get("LIVEKIT_URL"),
        api_key=os.environ.get("LIVEKIT_API_KEY"),
        api_secret=os.environ.get("LIVEKIT_API_SECRET")
    )

    # 1. Delete the bad rule
    bad_rule_id = "SDR_nVDu7v4n4tNA"
    print(f"🗑️  Deleting bad dispatch rule: {bad_rule_id}")
    try:
        await lkapi.sip.delete_sip_dispatch_rule(
            api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=bad_rule_id)
        )
        print("✅ Deleted!")
    except Exception as e:
        print(f"❌ Error deleting: {e}")

    # 2. Create a proper dispatch rule with agent_name
    print("\n📝 Creating new dispatch rule for agent-tradiedee...")
    rule = api.SIPDispatchRule(
        dispatch_rule_individual=api.SIPDispatchRuleIndividual(
            room_prefix='call-',
        )
    )

    request = api.CreateSIPDispatchRuleRequest(
        dispatch_rule=api.SIPDispatchRuleInfo(
            rule=rule,
            name='Tradiedee English Agent',
            trunk_ids=[],  # match all trunks on this project
            room_config=api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name="agent-tradiedee",
                        metadata='{"language": "en", "model": "gpt-4o-realtime"}'
                    )
                ]
            ),
            metadata='{"auto_ai": true}',
            attributes={
                "project": "Tradiedee",
                "type": "ai_call"
            }
        )
    )

    dispatch = await lkapi.sip.create_sip_dispatch_rule(request)
    print(f"✅ Created new dispatch rule: {dispatch.sip_dispatch_rule_id}")
    print(f"   Name: Tradiedee English Agent")
    print(f"   Agent: agent-tradiedee")

    await lkapi.aclose()

if __name__ == "__main__":
    asyncio.run(fix_dispatch())
