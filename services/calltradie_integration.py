"""
CallTradie Integration Service
Handles availability checking, job creation, and SMS for AI agent calls
"""

import asyncio
import logging
import aiohttp
import re
import os
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger("calltradie-integration")

FLASK_API_BASE = os.environ.get('FLASK_API_BASE', 'http://localhost:5016')


class CallTradeieIntegration:
    """Integration layer between agent and Flask backend"""

    @staticmethod
    async def check_availability(business_id: int, days_ahead: int = 7) -> Dict:
        """
        Check available time slots for a business

        Args:
            business_id: ID of the business
            days_ahead: Number of days to check ahead (default 7)

        Returns:
            Dict with available slots or fallback info
        """
        try:
            url = f"{FLASK_API_BASE}/api/booking/check-availability"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={
                        'business_id': business_id,
                        'days_ahead': days_ahead
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()

                    if resp.status == 200:
                        logger.info(f"✅ Availability check: {len(data.get('available_slots', []))} slots found")
                        return {
                            'success': True,
                            'slots': data.get('available_slots', []),
                            'fallback': data.get('fallback', False)
                        }
                    else:
                        logger.warning(f"⚠️ Availability check failed: {data}")
                        return {
                            'success': False,
                            'fallback': data.get('fallback', True),
                            'message': data.get('message', 'Cannot check availability')
                        }

        except asyncio.TimeoutError:
            logger.error("❌ Availability check timeout")
            return {
                'success': False,
                'fallback': True,
                'message': 'Calendar service timeout'
            }
        except Exception as e:
            logger.error(f"❌ Availability check error: {e}")
            return {
                'success': False,
                'fallback': True,
                'message': str(e)
            }

    @staticmethod
    async def create_job(
        business_id: int,
        customer_name: str,
        customer_phone: str,
        customer_address: str,
        service_type: str,
        description: str,
        scheduled_datetime: Optional[str] = None,
        is_emergency: bool = False,
        call_id: Optional[str] = None
    ) -> Dict:
        """
        Create a job/booking in the database
        Called after call ends via webhook

        Args:
            business_id: ID of the business
            customer_name: Customer name
            customer_phone: Customer phone number
            customer_address: Customer address
            service_type: Type of service (plumbing, electrical, etc.)
            description: Job description
            scheduled_datetime: When the job is scheduled
            is_emergency: Whether it's an emergency
            call_id: Reference to the call

        Returns:
            Dict with job creation result
        """
        try:
            url = f"{FLASK_API_BASE}/api/jobs/create"

            payload = {
                'business_id': business_id,
                'customer_name': customer_name,
                'customer_phone': customer_phone,
                'customer_address': customer_address,
                'service_type': service_type,
                'description': description,
                'scheduled_datetime': scheduled_datetime,
                'is_emergency': is_emergency,
                'call_id': call_id
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()

                    if resp.status == 201:
                        logger.info(f"✅ Job created: ID={data.get('job_id')}")
                        return {
                            'success': True,
                            'job_id': data.get('job_id'),
                            'confirmation': data.get('confirmation')
                        }
                    else:
                        logger.error(f"❌ Job creation failed: {data}")
                        return {
                            'success': False,
                            'error': data.get('error', 'Failed to create job')
                        }

        except Exception as e:
            logger.error(f"❌ Job creation error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    async def send_sms(
        customer_phone: str,
        message: str,
        job_id: Optional[int] = None
    ) -> Dict:
        """
        Send SMS confirmation to customer

        Args:
            customer_phone: Phone number to send SMS
            message: SMS message text
            job_id: Reference to the job

        Returns:
            Dict with SMS result
        """
        try:
            url = f"{FLASK_API_BASE}/api/sms/send"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={
                        'phone': customer_phone,
                        'message': message,
                        'job_id': job_id
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()

                    if resp.status == 200:
                        logger.info(f"✅ SMS sent to {customer_phone}")
                        return {
                            'success': True,
                            'sms_id': data.get('sms_id')
                        }
                    else:
                        logger.error(f"❌ SMS send failed: {data}")
                        return {
                            'success': False,
                            'error': data.get('error', 'Failed to send SMS')
                        }

        except Exception as e:
            logger.error(f"❌ SMS send error: {e}")
            return {
                'success': False,
                'error': str(e)
            }


class EntityExtractor:
    """Extract customer details from conversation using AI"""

    @staticmethod
    def extract_from_transcript_openai_sync(transcript: str) -> Dict:
        """
        Extract customer details using OpenAI synchronously

        Args:
            transcript: Full conversation transcription

        Returns:
            Dict with extracted: name, phone, address, service_type, booking_needed
        """
        try:
            from openai import OpenAI

            client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

            prompt = f"""Analyze this customer service call transcript and extract details. Return JSON only.
Today's date and time: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Transcript:
{transcript}

Extract and return ONLY valid JSON (no markdown, no explanation) with these fields:
{{
  "customer_name": "extracted full name or null",
  "customer_phone": "extracted phone number (Australian format like 0412345678) or null",
  "customer_email": "extracted email address or null",
  "customer_address": "extracted street address or null",
  "customer_suburb": "extracted suburb/city name or null",
  "customer_postcode": "extracted Australian postcode (4 digits) or null",
  "service_type": "plumbing|electrical|hvac|gas|general or null",
  "issue_description": "brief description of the issue or null",
  "urgency": "normal|emergency based on keywords",
  "booking_needed": true or false,
  "scheduled_datetime": "ISO 8601 datetime string or null",
  "call_summary": "2-3 sentence summary of the call from the business owner's perspective"
}}

Rules:
- Only extract if clearly mentioned in the call
- Phone: Australian numbers in format 04XX XXX XXX or 0412345678
- Service type: identify from keywords (water/leak=plumbing, light/power=electrical, etc)
- Urgency: emergency if mentions urgent/leak/flooding/burst
- booking_needed: true if customer asked about times, availability, or scheduling
- scheduled_datetime: if customer agreed on or requested a specific date/time (e.g. "tomorrow 10am", "Monday at 2pm", "today at 4", "this afternoon"), convert to full ISO 8601 datetime using today's date as reference. If no specific time mentioned, use null
- call_summary: write a concise 2-3 sentence summary of what the customer needs, what was discussed, and the outcome. Write from the business perspective (e.g. "Customer called about a burst pipe in their bathroom. They need urgent repair. Appointment booked for tomorrow 10am.")"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                timeout=10
            )

            response_text = response.choices[0].message.content.strip()

            # Clean up markdown if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            import json
            extracted = json.loads(response_text.strip())

            logger.info(f"✅ OpenAI Extracted: name={extracted.get('customer_name')}, phone={extracted.get('customer_phone')}, service={extracted.get('service_type')}, booking_needed={extracted.get('booking_needed')}")

            return extracted

        except Exception as e:
            logger.error(f"⚠️ OpenAI extraction failed ({type(e).__name__}), falling back to regex: {str(e)[:100]}")
            # Fallback to regex extraction
            return EntityExtractor.extract_from_transcript(transcript)

    @staticmethod
    async def extract_from_transcript_openai(transcript: str) -> Dict:
        """
        Extract customer details using OpenAI for intelligent parsing

        Args:
            transcript: Full conversation transcription

        Returns:
            Dict with extracted: name, phone, address, service_type, booking_needed
        """
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

            prompt = f"""Analyze this customer service call transcript and extract details. Return JSON only.
Today's date and time: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Transcript:
{transcript}

Extract and return ONLY valid JSON (no markdown, no explanation) with these fields:
{{
  "customer_name": "extracted full name or null",
  "customer_phone": "extracted phone number (Australian format like 0412345678) or null",
  "customer_email": "extracted email address or null",
  "customer_address": "extracted street address or null",
  "customer_suburb": "extracted suburb/city name or null",
  "customer_postcode": "extracted Australian postcode (4 digits) or null",
  "service_type": "plumbing|electrical|hvac|gas|general or null",
  "issue_description": "brief description of the issue or null",
  "urgency": "normal|emergency based on keywords",
  "booking_needed": true or false,
  "scheduled_datetime": "ISO 8601 datetime string or null",
  "call_summary": "2-3 sentence summary of the call from the business owner's perspective"
}}

Rules:
- Only extract if clearly mentioned in the call
- Phone: Australian numbers in format 04XX XXX XXX or 0412345678
- Service type: identify from keywords (water/leak=plumbing, light/power=electrical, etc)
- Urgency: emergency if mentions urgent/leak/flooding/burst
- booking_needed: true if customer asked about times, availability, or scheduling
- scheduled_datetime: if customer agreed on or requested a specific date/time (e.g. "tomorrow 10am", "Monday at 2pm", "today at 4", "this afternoon"), convert to full ISO 8601 datetime using today's date as reference. If no specific time mentioned, use null
- call_summary: write a concise 2-3 sentence summary of what the customer needs, what was discussed, and the outcome. Write from the business perspective (e.g. "Customer called about a burst pipe in their bathroom. They need urgent repair. Appointment booked for tomorrow 10am.")"""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                timeout=10
            )

            response_text = response.choices[0].message.content.strip()

            # Clean up markdown if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            import json
            extracted = json.loads(response_text.strip())

            logger.info(f"✅ OpenAI Extracted: name={extracted.get('customer_name')}, phone={extracted.get('customer_phone')}, service={extracted.get('service_type')}, booking_needed={extracted.get('booking_needed')}")

            return extracted

        except Exception as e:
            logger.error(f"❌ OpenAI extraction failed: {e}")
            # Fallback to regex extraction
            return EntityExtractor.extract_from_transcript(transcript)

    @staticmethod
    def extract_from_transcript(transcript: str) -> Dict:
        """
        Extract customer details using regex patterns (fallback)

        Args:
            transcript: Full conversation transcription

        Returns:
            Dict with extracted: name, phone, address, service_type
        """
        extracted = {
            'customer_name': None,
            'customer_phone': None,
            'customer_address': None,
            'service_type': None,
            'issue_description': None,
            'urgency': 'normal',
            'booking_needed': False
        }

        # Extract phone number (Australian format)
        phone_patterns = [
            r'\+61\d{9}',           # +61412345678
            r'0\d{9}',              # 0412345678
            r'04\d{2}\s?\d{3}\s?\d{3}',  # 0412 345 678
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, transcript)
            if match:
                extracted['customer_phone'] = match.group(0)
                break

        # Extract service type
        service_keywords = {
            'plumbing': ['pipe', 'water', 'tap', 'drain', 'toilet', 'leak', 'plumber'],
            'electrical': ['light', 'power', 'electric', 'wire', 'switch', 'circuit', 'electrician'],
            'hvac': ['heat', 'cool', 'air', 'conditioning', 'temperature', 'hvac'],
            'gas': ['gas', 'boiler', 'heater'],
        }

        text_lower = transcript.lower()
        for service, keywords in service_keywords.items():
            if any(kw in text_lower for kw in keywords):
                extracted['service_type'] = service
                break

        # Extract urgency/emergency keywords
        emergency_keywords = ['urgent', 'emergency', 'asap', 'immediately', 'burst', 'leak', 'flooding', 'gas leak']
        if any(kw in text_lower for kw in emergency_keywords):
            extracted['urgency'] = 'emergency'

        # Check booking needs
        booking_keywords = ['book', 'appointment', 'available', 'schedule', 'time', 'when']
        if any(kw in text_lower for kw in booking_keywords):
            extracted['booking_needed'] = True

        # Extract name (simple: look for common name patterns)
        name_patterns = [
            r"(?:my name is|i'm|this is|it's)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            r"name[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, transcript, re.IGNORECASE)
            if match:
                extracted['customer_name'] = match.group(1)
                break

        # Extract address
        address_pattern = r"(\d+\s+[A-Za-z\s]+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir))"
        match = re.search(address_pattern, transcript, re.IGNORECASE)
        if match:
            extracted['customer_address'] = match.group(1)

        # Extract issue description
        messages = transcript.split('\n')
        for msg in messages:
            if msg.startswith('CUSTOMER:') or msg.startswith('USER:'):
                content = msg.replace('CUSTOMER:', '').replace('USER:', '').strip()
                if content and len(content) > 10:
                    extracted['issue_description'] = content[:200]
                    break

        logger.info(f"Extracted details: name={extracted['customer_name']}, phone={extracted['customer_phone']}, service={extracted['service_type']}")

        return extracted


# Export for agent integration
calltradie = CallTradeieIntegration()
extractor = EntityExtractor()
