"""
Recording Service for LiveKit + Alibaba OSS
Handles call recording management and storage
"""

import os
import logging
import oss2
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from livekit import api
from livekit.api.twirp_client import TwirpError

load_dotenv()
logger = logging.getLogger(__name__)

# OSS Configuration
OSS_ACCESS_KEY_ID = os.getenv('OSS_ACCESS_KEY_ID')
OSS_ACCESS_KEY_SECRET = os.getenv('OSS_ACCESS_KEY_SECRET')
OSS_BUCKET_NAME = os.getenv('OSS_BUCKET_NAME')
OSS_ENDPOINT = os.getenv('OSS_ENDPOINT')
OSS_REGION = os.getenv('OSS_REGION')

# LiveKit Configuration
LIVEKIT_URL = os.getenv('LIVEKIT_URL')
LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET')


class RecordingService:
    """Service for managing call recordings with LiveKit and Alibaba OSS"""

    def __init__(self):
        """Initialize OSS client"""
        try:
            auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
            self.bucket = oss2.Bucket(auth, f'https://{OSS_ENDPOINT}', OSS_BUCKET_NAME)
            logger.info("✅ OSS client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize OSS client: {e}")
            self.bucket = None

    async def start_recording(self, room_name: str):
        """
        Start recording a LiveKit room

        Args:
            room_name: Name of the LiveKit room to record

        Returns:
            str: Recording ID (egress_id) or None if failed
        """
        # Skip recording for mock or missing rooms (e.g., local dev sessions)
        if not room_name or room_name == "mock_room":
            logger.debug(f"⏭️  Skipping recording (invalid room): {room_name}")
            return None

        lk_api = None

        try:
            # Create LiveKit API client
            lk_api = api.LiveKitAPI(
                LIVEKIT_URL,
                LIVEKIT_API_KEY,
                LIVEKIT_API_SECRET
            )

            # Configure recording output (audio only, MP4 format)
            # Note: Using RoomCompositeEgressRequest for audio-only recording
            # Must use file_outputs= (plural) as a list, not file= (singular)
            # LiveKit has native AliOSSUpload support (not S3Upload)
            recording_request = api.RoomCompositeEgressRequest(
                room_name=room_name,
                audio_only=True,
                file_outputs=[api.EncodedFileOutput(
                    file_type=api.EncodedFileType.MP4,
                    filepath=f"recordings/{room_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.mp4",
                    aliOSS=api.AliOSSUpload(
                        access_key=OSS_ACCESS_KEY_ID,
                        secret=OSS_ACCESS_KEY_SECRET,
                        bucket=OSS_BUCKET_NAME,
                        region=OSS_REGION,
                        endpoint=OSS_ENDPOINT,
                    ),
                )]
            )

            # Start recording via egress
            response = await lk_api.egress.start_room_composite_egress(recording_request)

            logger.info(f"🎙️ Recording started for room {room_name}, egress_id: {response.egress_id}")
            return response.egress_id

        except TwirpError as err:
            if err.code == "not_found":
                logger.warning(
                    f"⚠️ Recording skipped for room {room_name} - LiveKit does not have this room yet"
                )
                return None
            logger.error(f"❌ LiveKit Twirp error while starting recording: {err}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to start recording for room {room_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
        finally:
            if lk_api:
                await lk_api.aclose()

    async def stop_recording(self, egress_id: str):
        """
        Stop an active recording

        Args:
            egress_id: Recording ID to stop

        Returns:
            bool: True if stopped successfully
        """
        try:
            lk_api = api.LiveKitAPI(
                LIVEKIT_URL,
                LIVEKIT_API_KEY,
                LIVEKIT_API_SECRET
            )

            await lk_api.egress.stop_egress(egress_id)
            await lk_api.aclose()

            logger.info(f"⏹️ Recording stopped: {egress_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to stop recording {egress_id}: {e}")
            return False

    def upload_to_oss(self, file_path: str, oss_key: str):
        """
        Upload a file to Alibaba OSS

        Args:
            file_path: Local file path to upload
            oss_key: OSS object key (path in bucket)

        Returns:
            str: Public URL of uploaded file or None if failed
        """
        if not self.bucket:
            logger.error("❌ OSS bucket not initialized")
            return None

        try:
            # Upload file
            self.bucket.put_object_from_file(oss_key, file_path)

            # Generate signed URL (valid for 365 days)
            url = self.bucket.sign_url('GET', oss_key, 365 * 24 * 3600)

            logger.info(f"✅ File uploaded to OSS: {oss_key}")
            return url

        except Exception as e:
            logger.error(f"❌ Failed to upload to OSS: {e}")
            return None

    def download_from_url(self, url: str, local_path: str):
        """
        Download file from URL

        Args:
            url: URL to download from
            local_path: Local path to save file

        Returns:
            bool: True if downloaded successfully
        """
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"✅ Downloaded file from {url}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to download file: {e}")
            return False

    async def process_recording(self, egress_id: str, room_name: str):
        """
        Process completed recording: Since LiveKit uploads directly to OSS,
        we just need to find the file and generate a signed URL

        Args:
            egress_id: Recording ID
            room_name: Room name for reference

        Returns:
            str: OSS signed URL of the recording or None if failed
        """
        try:
            # Get egress info to find the file location
            lk_api = api.LiveKitAPI(
                LIVEKIT_URL,
                LIVEKIT_API_KEY,
                LIVEKIT_API_SECRET
            )

            # List egress with proper request object (filter by room_name)
            list_request = api.ListEgressRequest(room_name=room_name)
            egress_response = await lk_api.egress.list_egress(list_request)

            await lk_api.aclose()

            if not egress_response or not egress_response.items:
                logger.error(f"❌ No egress info found for room {room_name}")
                return None

            # Find the specific egress by ID
            egress = None
            for eg in egress_response.items:
                if eg.egress_id == egress_id:
                    egress = eg
                    break

            if not egress:
                logger.error(f"❌ Egress {egress_id} not found in list")
                return None

            # Debug: Log egress structure
            logger.info(f"🔍 Egress status: {egress.status}")

            # Check for errors
            if hasattr(egress, 'error') and egress.error:
                logger.error(f"❌ Egress failed with error: {egress.error}")
                return None

            # Check if recording is complete
            # Status: EGRESS_STARTING=0, EGRESS_ACTIVE=1, EGRESS_ENDING=2, EGRESS_COMPLETE=3, EGRESS_FAILED=4
            if egress.status == 4:  # Failed
                logger.error(f"❌ Recording failed (status: 4)")
                return None
            elif egress.status < 3:  # Not complete yet
                logger.warning(f"⏳ Recording still in progress (status: {egress.status}), will retry later")
                return None

            # LiveKit uploaded directly to OSS using native AliOSSUpload
            # File information is in egress.file (singular), not file_results (plural)
            oss_filepath = None

            # Check file field - this is where AliOSS stores file info
            if hasattr(egress, 'file') and egress.file:
                # Try filename first
                if hasattr(egress.file, 'filename') and egress.file.filename:
                    oss_filepath = egress.file.filename
                    logger.info(f"✅ Found OSS file in egress.file.filename: {oss_filepath}")
                # Try location as fallback
                elif hasattr(egress.file, 'location') and egress.file.location:
                    oss_filepath = egress.file.location
                    logger.info(f"✅ Found OSS file in egress.file.location: {oss_filepath}")

                # Log additional file metadata
                if oss_filepath:
                    if hasattr(egress.file, 'size'):
                        logger.info(f"📊 File size: {egress.file.size} bytes")
                    if hasattr(egress.file, 'duration'):
                        logger.info(f"⏱️ Duration: {egress.file.duration}ms")
                else:
                    logger.error(f"⚠️ egress.file exists but filename and location are both empty")
            else:
                logger.error(f"❌ egress.file does not exist or is empty")

            if not oss_filepath:
                logger.error(f"❌ No file path found in egress")
                return None

            logger.info(f"☁️ Recording file in OSS: {oss_filepath}")

            # Generate signed URL for the OSS file (365 days expiry)
            oss_url = self.get_signed_url(oss_filepath, expires_in_days=365)

            if oss_url:
                logger.info(f"✅ Generated signed URL for recording")
                return oss_url
            else:
                logger.error(f"❌ Failed to generate signed URL")
                return None

        except Exception as e:
            logger.error(f"❌ Failed to process recording {egress_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def get_signed_url(self, oss_key: str, expires_in_days: int = 365):
        """
        Generate a signed URL for an OSS object

        Args:
            oss_key: OSS object key
            expires_in_days: URL expiration in days

        Returns:
            str: Signed URL or None if failed
        """
        if not self.bucket:
            return None

        try:
            url = self.bucket.sign_url('GET', oss_key, expires_in_days * 24 * 3600)
            return url
        except Exception as e:
            logger.error(f"❌ Failed to generate signed URL: {e}")
            return None


# Global instance
recording_service = RecordingService()