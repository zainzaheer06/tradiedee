import asyncio
import os
from livekit import api
from dotenv import load_dotenv

async def create_dispatch_rule():
    # Load environment variables
    load_dotenv(".env")
    
    # Initialize LiveKit API with credentials
    lkapi = api.LiveKitAPI(
        url=os.environ.get("LIVEKIT_URL"),
        api_key=os.environ.get("LIVEKIT_API_KEY"),
        api_secret=os.environ.get("LIVEKIT_API_SECRET")
    )

    # Create a dispatch rule to give each caller its own AI room
    rule = api.SIPDispatchRule(
      dispatch_rule_individual = api.SIPDispatchRuleIndividual(
        room_prefix = 'call-',
      )
    )

    request = api.CreateSIPDispatchRuleRequest(
      dispatch_rule = api.SIPDispatchRuleInfo(
        rule = rule,
        name = 'Nevox AI Inbound Rule',
        # optional trunk IDs (omit to match all)
        trunk_ids = [],
        room_config = api.RoomConfiguration(
          agents = [
            api.RoomAgentDispatch(
              agent_name = "agent-inbound",
              metadata = "{\"language\": \"ar\", \"model\": \"gpt-4o-realtime\"}"
            )
          ]
        ),
        metadata = "{\"auto_ai\": true}",
        attributes = {
          "project": "Nevox",
          "type": "ai_call"
        }
      )
    )

    dispatch = await lkapi.sip.create_sip_dispatch_rule(request)
    print("✅ Created dispatch rule:", dispatch)
    await lkapi.aclose()

if __name__ == "__main__":
    asyncio.run(create_dispatch_rule())
