"""
Test Agent Routes Blueprint
Allows users to test their agents via browser-based WebRTC calls
"""
import os
import time
import math
import asyncio
import logging
from flask import Blueprint, render_template, request, session, jsonify
from livekit import api

from models import db, Agent, User
from utils.decorators import login_required, approved_required

logger = logging.getLogger(__name__)

# Create blueprint
test_agent_bp = Blueprint('test_agent', __name__)

# Store active test calls with start times (for minutes calculation)
active_test_calls = {}


@test_agent_bp.route('/')
@login_required
@approved_required
def test_agent_page():
    """Test agent interface - talk to your agent via browser"""
    user = db.session.get(User, session['user_id'])
    agents = Agent.query.filter_by(user_id=user.id).order_by(Agent.name).all()
    return render_template('calls/test_agent.html', user=user, agents=agents)


@test_agent_bp.route('/start', methods=['POST'])
@login_required
@approved_required
def start_test_call():
    """Start a test call with the selected agent"""
    try:
        data = request.json
        agent_id = data.get('agent_id')

        if not agent_id:
            return jsonify({'error': 'Agent ID is required'}), 400

        # Get user and check minutes balance
        user = db.session.get(User, session['user_id'])
        if user.minutes_balance <= 0:
            return jsonify({'error': 'Insufficient minutes. Please add more minutes to test agents.'}), 400

        # Verify agent belongs to user
        agent = Agent.query.filter_by(
            id=agent_id,
            user_id=session['user_id']
        ).first()

        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

        # Get LiveKit credentials
        livekit_url = os.environ.get('LIVEKIT_URL')
        api_key = os.environ.get('LIVEKIT_API_KEY')
        api_secret = os.environ.get('LIVEKIT_API_SECRET')

        if not all([livekit_url, api_key, api_secret]):
            return jsonify({'error': 'LiveKit credentials not configured'}), 500

        # Generate room name in format that agent recognizes: call-{agent_id}-test-{timestamp}
        room_name = f"call-{agent_id}-test-{int(time.time())}"
        participant_identity = f"test-user-{session['user_id']}"

        # Create token for browser participant
        token = api.AccessToken(api_key, api_secret) \
            .with_identity(participant_identity) \
            .with_name(session.get('username', 'Test User')) \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            ))

        jwt_token = token.to_jwt()

        # Dispatch the agent to the room
        async def dispatch_agent():
            lkapi = api.LiveKitAPI()

            dispatch = await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name="agent",
                    room=room_name,
                    metadata=str(agent_id)
                )
            )

            await lkapi.aclose()
            return dispatch

        dispatch = asyncio.run(dispatch_agent())

        # Store start time for minutes calculation
        active_test_calls[room_name] = {
            'user_id': session['user_id'],
            'start_time': time.time(),
            'agent_id': agent_id
        }

        logger.info(f"Test call started: room={room_name}, agent={agent.name}, user={user.username}")

        return jsonify({
            'success': True,
            'token': jwt_token,
            'url': livekit_url,
            'room_name': room_name,
            'agent_name': agent.name
        })

    except Exception as e:
        logger.error(f"Error starting test call: {e}")
        return jsonify({'error': str(e)}), 500


@test_agent_bp.route('/end', methods=['POST'])
@login_required
@approved_required
def end_test_call():
    """End a test call and deduct minutes"""
    try:
        data = request.json
        room_name = data.get('room_name')

        if not room_name:
            return jsonify({'error': 'Room name is required'}), 400

        # Calculate duration and deduct minutes
        minutes_used = 0
        if room_name in active_test_calls:
            call_info = active_test_calls.pop(room_name)
            duration_seconds = int(time.time() - call_info['start_time'])
            minutes_used = math.ceil(duration_seconds / 60)  # Round up to nearest minute

            # Deduct minutes from user
            if minutes_used > 0:
                user = db.session.get(User, call_info['user_id'])
                if user:
                    user.minutes_balance = max(0, user.minutes_balance - minutes_used)
                    user.minutes_used = (user.minutes_used or 0) + minutes_used
                    db.session.commit()
                    logger.info(f"Test call: deducted {minutes_used} min from {user.username} (duration: {duration_seconds}s)")

        # Delete the room to end the call
        async def delete_room():
            lkapi = api.LiveKitAPI()
            await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
            await lkapi.aclose()

        asyncio.run(delete_room())

        logger.info(f"Test call ended: room={room_name}, minutes_used={minutes_used}")

        return jsonify({
            'success': True,
            'message': 'Call ended',
            'minutes_used': minutes_used
        })

    except Exception as e:
        logger.error(f"Error ending test call: {e}")
        return jsonify({'error': str(e)}), 500
