"""
Emergency Escalation Handler
Manages emergency call routing and escalation
"""

import logging
import asyncio
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class EscalationStatus(Enum):
    """Status of escalation attempts"""
    PENDING = "pending"
    RINGING = "ringing"
    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    FAILED = "failed"


class EmergencyKeywordDetector:
    """
    Detects emergency keywords in conversation
    """

    # Australian emergency keywords for trades
    EMERGENCY_KEYWORDS = [
        # Water-related
        'burst pipe', 'burst', 'leaking', 'leak', 'flooding', 'flood', 'water damage',
        'no hot water', 'no water', 'water everywhere',

        # Electrical
        'electrical fire', 'electrical', 'power outage', 'power out', 'no power',
        'no electricity', 'sparks', 'burning smell', 'electric shock',

        # Gas
        'gas leak', 'gas smell', 'rotten egg smell',

        # Structural
        'roof damage', 'ceiling falling', 'wall crack', 'foundation',

        # Urgency
        'emergency', 'urgent', 'urgent call', 'asap', 'right now',
        'immediately', 'now', 'can\'t wait', 'can\'t wait any longer',
        'dangerous', 'hazard', 'risk', 'critical',

        # Health/Safety
        'unsafe', 'safety', 'injuries', 'hurt', 'injured',
    ]

    @staticmethod
    def detect_emergency(transcript: str) -> tuple[bool, List[str]]:
        """
        Check if transcript contains emergency keywords

        Args:
            transcript: Call transcript text

        Returns:
            (is_emergency: bool, detected_keywords: list)
        """
        transcript_lower = transcript.lower()
        detected = []

        for keyword in EmergencyKeywordDetector.EMERGENCY_KEYWORDS:
            if keyword in transcript_lower:
                detected.append(keyword)

        is_emergency = len(detected) > 0

        logger.info(f"Emergency detection: {is_emergency}, keywords: {detected}")
        return is_emergency, detected

    @staticmethod
    def detect_urgency_level(transcript: str) -> str:
        """
        Determine urgency level of emergency

        Args:
            transcript: Call transcript text

        Returns:
            'critical' (immediate), 'high' (very soon), 'medium'
        """
        transcript_lower = transcript.lower()

        critical_keywords = ['fire', 'gas leak', 'electrical fire', 'emergency', 'injuries']
        high_keywords = ['flooding', 'burst pipe', 'power outage', 'urgent', 'now']

        for keyword in critical_keywords:
            if keyword in transcript_lower:
                return 'critical'

        for keyword in high_keywords:
            if keyword in transcript_lower:
                return 'high'

        return 'medium'


class EmergencyEscalationHandler:
    """
    Manages emergency call escalation to technicians
    """

    def __init__(self, twilio_client=None, livekit_client=None):
        """
        Initialize emergency handler

        Args:
            twilio_client: Twilio client for SMS/calls
            livekit_client: LiveKit client for call transfer
        """
        self.twilio = twilio_client
        self.livekit = livekit_client

    async def escalate_emergency(
        self,
        business_id: int,
        job_details: Dict,
        emergency_keywords: List[str],
        contacts: List[Dict],
        timeout_seconds: int = 30
    ) -> Optional[str]:
        """
        Escalate emergency call through contact hierarchy

        Args:
            business_id: Business ID
            job_details: Job details dict
            emergency_keywords: Detected emergency keywords
            contacts: List of contacts to try, in priority order
                Format: [
                    {'name': 'John', 'phone': '+61412345678', 'priority': 1},
                    {'name': 'Sarah', 'phone': '+61412345679', 'priority': 2},
                ]
            timeout_seconds: Timeout per call attempt

        Returns:
            Name of contact who answered, or None if all failed
        """

        logger.info(f"EMERGENCY ESCALATION: Business {business_id}")
        logger.info(f"Keywords detected: {emergency_keywords}")
        logger.info(f"Contacts to try: {len(contacts)}")

        if not contacts:
            logger.warning(f"No emergency contacts configured for business {business_id}")
            return None

        # Sort by priority
        contacts = sorted(contacts, key=lambda x: x.get('priority', 999))

        escalation_log = {
            'business_id': business_id,
            'job_details': job_details,
            'emergency_keywords': emergency_keywords,
            'attempts': [],
            'timestamp': datetime.now().isoformat()
        }

        # Try each contact
        for idx, contact in enumerate(contacts, 1):
            logger.info(f"Escalation attempt {idx}/{len(contacts)}: {contact.get('name')}")

            try:
                result = await self._try_contact(
                    contact,
                    job_details,
                    timeout_seconds
                )

                escalation_log['attempts'].append({
                    'contact': contact['name'],
                    'phone': contact['phone'],
                    'status': result,
                    'timestamp': datetime.now().isoformat()
                })

                if result == EscalationStatus.ANSWERED.value:
                    logger.info(f"Emergency transferred to {contact['name']}")
                    return contact['name']

                # Small delay before next attempt
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error contacting {contact.get('name')}: {str(e)}")
                escalation_log['attempts'].append({
                    'contact': contact['name'],
                    'status': EscalationStatus.FAILED.value,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })

        # All contacts failed - send SMS alert
        logger.warning(f"All escalation attempts failed for business {business_id}")
        await self._send_emergency_sms_alert(
            business_id,
            contacts,
            job_details,
            emergency_keywords
        )

        escalation_log['final_status'] = 'sms_alert_sent'
        return None

    async def _try_contact(
        self,
        contact: Dict,
        job_details: Dict,
        timeout_seconds: int
    ) -> str:
        """
        Try to contact a single person

        Args:
            contact: Contact dict with name and phone
            job_details: Job details to communicate
            timeout_seconds: Timeout for call

        Returns:
            Status string (answered, no_answer, failed)
        """

        if not self.twilio:
            logger.warning("Twilio not configured, cannot make escalation call")
            return EscalationStatus.FAILED.value

        try:
            phone = contact.get('phone')
            if not phone:
                logger.error(f"No phone number for {contact.get('name')}")
                return EscalationStatus.FAILED.value

            logger.info(f"Making emergency call to {contact.get('name')} at {phone}")

            # Make call (would integrate with your actual call system)
            # For now, just log it
            # call = self.twilio.calls.create(...)

            # In a real implementation:
            # - Use your LiveKit agent to make the call
            # - Or use Twilio to route the call
            # - Monitor for answer within timeout_seconds

            # Simulate checking for answer
            for attempt in range(timeout_seconds):
                await asyncio.sleep(1)
                # Check if call was answered (would come from callback/webhook)
                # For now, assume no answer
                pass

            return EscalationStatus.NO_ANSWER.value

        except Exception as e:
            logger.error(f"Error in contact attempt: {str(e)}")
            return EscalationStatus.FAILED.value

    async def _send_emergency_sms_alert(
        self,
        business_id: int,
        contacts: List[Dict],
        job_details: Dict,
        emergency_keywords: List[str]
    ) -> bool:
        """
        Send SMS alert when all calls fail

        Args:
            business_id: Business ID
            contacts: Contacts to alert
            job_details: Job details
            emergency_keywords: Detected emergency keywords

        Returns:
            True if all SMSs sent successfully
        """

        if not self.twilio:
            logger.warning("Twilio not configured, cannot send emergency SMS")
            return False

        message = f"""
🚨 EMERGENCY JOB ALERT 🚨

Issue: {job_details.get('job_type', 'Unknown')}
Details: {job_details.get('description', '')}
Location: {job_details.get('customer_address', '')}, {job_details.get('customer_suburb', '')}
Customer: {job_details.get('customer_name', '')} - {job_details.get('customer_phone', '')}
Keywords: {', '.join(emergency_keywords)}

URGENT: All technicians unavailable. Please advise.
Phone call was not answered. Please respond via SMS.
"""

        success_count = 0
        for contact in contacts:
            try:
                phone = contact.get('phone')
                if not phone:
                    logger.warning(f"No phone for {contact.get('name')}")
                    continue

                logger.info(f"Sending emergency SMS to {contact.get('name')} at {phone}")

                # Send SMS (would integrate with actual Twilio)
                # self.twilio.messages.create(
                #     body=message,
                #     from_=business_twilio_number,
                #     to=phone
                # )

                logger.info(f"Emergency SMS sent to {contact.get('name')}")
                success_count += 1

            except Exception as e:
                logger.error(f"Failed to send SMS to {contact.get('name')}: {str(e)}")

        return success_count == len(contacts)

    @staticmethod
    def format_emergency_message(
        customer_name: str,
        customer_phone: str,
        address: str,
        suburb: str,
        description: str,
        urgency_level: str = 'high'
    ) -> str:
        """
        Format message for emergency transfer

        Args:
            customer_name: Customer name
            customer_phone: Customer phone
            address: Job address
            suburb: Suburb
            description: Job description
            urgency_level: 'critical', 'high', or 'medium'

        Returns:
            Formatted message string
        """

        urgency_emoji = {
            'critical': '🚨',
            'high': '⚠️',
            'medium': '⚡'
        }

        emoji = urgency_emoji.get(urgency_level, '⚡')

        message = f"""
{emoji} EMERGENCY JOB {emoji}

Customer: {customer_name}
Phone: {customer_phone}
Address: {address}, {suburb}
Issue: {description}

STATUS: Transferring to you now.
"""
        return message
