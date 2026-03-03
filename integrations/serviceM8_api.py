"""
ServiceM8 Integration Module
Handles all ServiceM8 API interactions for job management and availability checking
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class ServiceM8Integration:
    """
    ServiceM8 API integration for CallTradie
    Handles job creation, availability checking, and status updates
    """

    def __init__(self, api_key: str, customer_id: str, timeout: int = 10):
        """
        Initialize ServiceM8 client

        Args:
            api_key: ServiceM8 API key
            customer_id: ServiceM8 customer ID
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.customer_id = customer_id
        self.base_url = "https://api.service-m8.com/api_1_0"
        self.timeout = timeout

    def get_available_slots(
        self,
        days_ahead: int = 7,
        slot_duration_hours: int = 2,
        business_hours_start: int = 9,
        business_hours_end: int = 17
    ) -> Optional[List[datetime]]:
        """
        Get available appointment slots from ServiceM8

        Args:
            days_ahead: Number of days to check ahead
            slot_duration_hours: Duration of each slot in hours
            business_hours_start: Start of business hours (24-hour format)
            business_hours_end: End of business hours (24-hour format)

        Returns:
            List of available datetime slots, or None if check failed
        """
        try:
            # Get all jobs for the next N days
            endpoint = f"{self.base_url}/Job.json"

            end_date = datetime.now() + timedelta(days=days_ahead)

            params = {
                'auth': self.api_key,
                'filter': f'JobDate >= TODAY() AND JobDate <= DATE("{end_date.strftime("%Y-%m-%d")}")',
                'order': 'JobDate',
            }

            response = requests.get(
                endpoint,
                params=params,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()

            jobs = response.json()
            if not isinstance(jobs, list):
                jobs = [jobs] if jobs else []

            logger.info(f"Retrieved {len(jobs)} jobs from ServiceM8")

            # Extract occupied times
            occupied_slots = []
            for job in jobs:
                try:
                    job_date_str = job.get('JobDate', '')
                    if job_date_str:
                        # Parse date - ServiceM8 returns ISO format
                        job_date = datetime.fromisoformat(job_date_str.split('T')[0])
                        job_date = job_date.replace(hour=job.get('JobStartTime', 9) or 9)

                        occupied_slots.append({
                            'start': job_date,
                            'end': job_date + timedelta(hours=slot_duration_hours)
                        })
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse job date: {job.get('JobDate')}, {str(e)}")
                    continue

            logger.info(f"Occupied slots: {len(occupied_slots)}")

            # Generate available slots
            available_slots = []
            current = datetime.now().replace(hour=business_hours_start, minute=0, second=0, microsecond=0)

            # Move to next day if past business hours
            if current.hour >= business_hours_end:
                current += timedelta(days=1)
                current = current.replace(hour=business_hours_start)

            end_time = current + timedelta(days=days_ahead)

            while current < end_time:
                # Skip weekends
                if current.weekday() < 5:  # Monday = 0, Friday = 4
                    # Check if within business hours
                    if business_hours_start <= current.hour < business_hours_end:
                        # Check if slot is occupied
                        is_occupied = any(
                            slot['start'] <= current < slot['end']
                            for slot in occupied_slots
                        )

                        if not is_occupied:
                            available_slots.append(current)

                current += timedelta(hours=slot_duration_hours)

            logger.info(f"Found {len(available_slots)} available slots")
            return available_slots

        except requests.RequestException as e:
            logger.error(f"ServiceM8 API request failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting available slots: {str(e)}")
            return None

    def is_available(self, proposed_datetime: datetime) -> Optional[bool]:
        """
        Quick check if a specific datetime is available

        Args:
            proposed_datetime: Datetime to check

        Returns:
            True if available, False if booked, None if check failed
        """
        try:
            slots = self.get_available_slots(days_ahead=1)
            if slots is None:
                return None
            return proposed_datetime in slots
        except Exception as e:
            logger.error(f"Error checking specific time availability: {str(e)}")
            return None

    def create_job(
        self,
        customer_data: Dict,
        job_details: Dict
    ) -> Optional[str]:
        """
        Create a job in ServiceM8

        Args:
            customer_data: {
                'name': str,
                'phone': str,
                'email': str,
                'address': str,
                'suburb': str,
                'postcode': str
            }
            job_details: {
                'description': str,
                'scheduled_datetime': datetime,
                'notes': str,
                'job_type': str
            }

        Returns:
            Job ID if successful, None if failed
        """
        try:
            endpoint = f"{self.base_url}/Job.json"

            # Format datetime for ServiceM8
            scheduled_dt = job_details['scheduled_datetime']
            job_date = scheduled_dt.strftime("%Y-%m-%d")
            job_time = scheduled_dt.strftime("%H:%M")

            payload = {
                'auth': self.api_key,
                'CompanyName': customer_data.get('name', '')[:50],
                'CompanyPhone': customer_data.get('phone', '')[:20],
                'CompanyEmail': customer_data.get('email', '')[:100],
                'CompanyAddress': customer_data.get('address', '')[:100],
                'CompanySuburb': customer_data.get('suburb', '')[:50],
                'CompanyPostcode': customer_data.get('postcode', '')[:10],
                'JobDate': job_date,
                'JobStartTime': job_time,
                'JobDescription': job_details.get('description', '')[:500],
                'JobNotes': job_details.get('notes', '')[:1000],
                'JobType': job_details.get('job_type', 'General')[:100],
            }

            response = requests.post(
                endpoint,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()

            job_data = response.json()
            job_id = job_data.get('JobID') or job_data.get('id')

            logger.info(f"Job created in ServiceM8: {job_id}")
            return str(job_id)

        except requests.RequestException as e:
            logger.error(f"ServiceM8 job creation API request failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating job: {str(e)}")
            return None

    def update_job_status(
        self,
        job_id: str,
        status: str,
        notes: str = ""
    ) -> bool:
        """
        Update job status in ServiceM8

        Args:
            job_id: ServiceM8 job ID
            status: New status (e.g., 'Scheduled', 'In Progress', 'Completed')
            notes: Optional notes to append

        Returns:
            True if successful, False if failed
        """
        try:
            endpoint = f"{self.base_url}/Job/{job_id}.json"

            payload = {
                'auth': self.api_key,
                'JobStatus': status,
            }

            if notes:
                payload['JobNotes'] = notes

            response = requests.patch(
                endpoint,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()

            logger.info(f"Job {job_id} status updated to {status}")
            return True

        except requests.RequestException as e:
            logger.error(f"ServiceM8 status update failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating job status: {str(e)}")
            return False

    def get_job(self, job_id: str) -> Optional[Dict]:
        """
        Get job details from ServiceM8

        Args:
            job_id: ServiceM8 job ID

        Returns:
            Job data dict or None if not found
        """
        try:
            endpoint = f"{self.base_url}/Job/{job_id}.json"

            params = {'auth': self.api_key}

            response = requests.get(
                endpoint,
                params=params,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            logger.error(f"ServiceM8 get job failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting job: {str(e)}")
            return None

    def health_check(self) -> bool:
        """
        Check if ServiceM8 API is accessible

        Returns:
            True if accessible, False otherwise
        """
        try:
            endpoint = f"{self.base_url}/Company.json"
            params = {'auth': self.api_key, 'limit': 1}

            response = requests.get(
                endpoint,
                params=params,
                timeout=5
            )
            response.raise_for_status()

            logger.info("ServiceM8 health check passed")
            return True

        except Exception as e:
            logger.error(f"ServiceM8 health check failed: {str(e)}")
            return False
