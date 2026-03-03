"""
Direct Audio Recording Service - Zero Cost Recording
Records audio directly from LiveKit rooms and uploads WAV to Alibaba OSS

For 100+ concurrent calls - NO egress costs
"""

import os
import asyncio
import logging
import wave
import oss2
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
from dotenv import load_dotenv
from livekit import rtc
import threading
from pydub import AudioSegment

load_dotenv()
logger = logging.getLogger(__name__)

# OSS Configuration
OSS_ACCESS_KEY_ID = os.getenv('OSS_ACCESS_KEY_ID')
OSS_ACCESS_KEY_SECRET = os.getenv('OSS_ACCESS_KEY_SECRET')
OSS_BUCKET_NAME = os.getenv('OSS_BUCKET_NAME')
OSS_ENDPOINT = os.getenv('OSS_ENDPOINT')

# Recording settings
RECORDINGS_DIR = Path("./recordings_temp")
RECORDINGS_DIR.mkdir(exist_ok=True)
SAMPLE_RATE = 24000  # 24kHz
CHANNELS = 1  # Mono
SAMPLE_WIDTH = 2  # 16-bit


class AudioRecorder:
    """Records audio from LiveKit room to WAV file"""

    def __init__(self, room_name: str):
        self.room_name = room_name
        self.timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        self.filename = f"{room_name}_{self.timestamp}.wav"
        self.wav_path = RECORDINGS_DIR / self.filename
        self.wav_file = None
        self.is_recording = False
        self.frames_written = 0
        self.wav_configured = False  # Track if WAV format is set from first frame
        self.write_lock = threading.Lock()  # Thread-safe writing for multiple audio sources

    def start(self):
        """Initialize WAV file (format will be set from first frame)"""
        try:
            self.wav_file = wave.open(str(self.wav_path), 'wb')
            # Don't set parameters yet - will configure from first frame
            self.is_recording = True
            logger.info(f"🎙️ Recording: {self.filename}")
        except Exception as e:
            logger.error(f"❌ Failed to start: {e}")
            self.is_recording = False

    def write_frame(self, frame: rtc.AudioFrame):
        """Write audio frame to WAV with proper format detection (thread-safe)"""
        if not self.is_recording or not self.wav_file:
            return

        try:
            with self.write_lock:  # Thread-safe writing for user + agent audio
                # Configure WAV format from first frame
                if not self.wav_configured:
                    # Get actual format from LiveKit frame
                    actual_sample_rate = frame.sample_rate
                    actual_channels = frame.num_channels

                    # LiveKit audio data is typically int16 PCM
                    sample_width = 2  # 16-bit = 2 bytes

                    # Configure WAV file with actual format
                    self.wav_file.setnchannels(actual_channels)
                    self.wav_file.setsampwidth(sample_width)
                    self.wav_file.setframerate(actual_sample_rate)

                    self.wav_configured = True
                    logger.info(f"📊 WAV Format: {actual_sample_rate}Hz, {actual_channels} channel(s), {sample_width*8}-bit")

                # Convert numpy array to bytes and write
                if isinstance(frame.data, np.ndarray):
                    # Ensure int16 format
                    audio_data = frame.data.astype(np.int16)
                    self.wav_file.writeframes(audio_data.tobytes())
                else:
                    # Fallback if not numpy array
                    self.wav_file.writeframes(bytes(frame.data))

                self.frames_written += 1

        except Exception as e:
            logger.error(f"❌ Failed to write frame: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def stop(self) -> Optional[Path]:
        """Close WAV file"""
        if not self.wav_file:
            return None

        try:
            self.wav_file.close()
            self.is_recording = False

            logger.info(f"📊 Frames written: {self.frames_written}")

            if self.wav_path.exists() and self.wav_path.stat().st_size > 1000:
                size_mb = self.wav_path.stat().st_size / (1024 * 1024)
                logger.info(f"✅ Saved: {self.filename} ({size_mb:.1f}MB, {self.frames_written} frames)")
                return self.wav_path
            else:
                logger.warning(f"⚠️ File too small or missing (frames: {self.frames_written})")
                self.wav_path.unlink(missing_ok=True)
                return None
        except Exception as e:
            logger.error(f"❌ Stop error: {e}")
            return None


class AudioRecorderService:
    """Service for direct audio recording"""

    def __init__(self):
        try:
            auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
            self.bucket = oss2.Bucket(auth, f'https://{OSS_ENDPOINT}', OSS_BUCKET_NAME)
            logger.info("✅ OSS ready")
        except Exception as e:
            logger.error(f"❌ OSS init failed: {e}")
            self.bucket = None

        self.active_recordings: Dict[str, AudioRecorder] = {}
        self.recording_urls: Dict[str, str] = {}  # Store recording URLs

    async def start_recording(self, room: rtc.Room) -> Optional[str]:
        """
        Start recording room audio (user only for now - clear quality)

        Args:
            room: LiveKit Room object

        Returns:
            Room name as recording ID
        """
        room_name = room.name

        try:
            recorder = AudioRecorder(room_name)
            recorder.start()

            if not recorder.is_recording:
                return None

            self.active_recordings[room_name] = recorder

            # Subscribe to existing REMOTE participants (users only)
            for participant in room.remote_participants.values():
                asyncio.create_task(self._subscribe(participant, recorder, "User"))

            # Handle new participants
            @room.on("participant_connected")
            def on_participant_connected(participant: rtc.RemoteParticipant):
                asyncio.create_task(self._subscribe(participant, recorder, "User"))

            logger.info(f"🎙️ Recording: {room_name} (user audio)")
            return room_name

        except Exception as e:
            logger.error(f"❌ Start failed: {e}")
            return None

    async def _subscribe(self, participant: rtc.RemoteParticipant, recorder: AudioRecorder, label: str = "Participant"):
        """Subscribe to remote participant audio"""
        try:
            # Find audio track
            audio_track = None
            for pub in participant.track_publications.values():
                if pub.kind == rtc.TrackKind.KIND_AUDIO:
                    if pub.track:
                        audio_track = pub.track
                        break
                    elif pub.subscribed:
                        # Wait for track to be available
                        await asyncio.sleep(0.1)
                        if pub.track:
                            audio_track = pub.track
                            break

            if not audio_track:
                logger.debug(f"No audio track for {participant.identity}")
                return

            logger.info(f"📻 Subscribed to {label} audio: {participant.identity}")

            # Stream audio frames
            audio_stream = rtc.AudioStream(audio_track)
            async for event in audio_stream:
                if not recorder.is_recording:
                    break
                # Extract the actual AudioFrame from the event
                recorder.write_frame(event.frame)

        except Exception as e:
            logger.error(f"❌ Subscribe error ({label}): {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _subscribe_local(self, local_participant: rtc.LocalParticipant, recorder: AudioRecorder):
        """Subscribe to local participant (agent) audio tracks"""
        try:
            # Subscribe to existing local audio tracks
            for track_pub in local_participant.track_publications.values():
                if track_pub.kind == rtc.TrackKind.KIND_AUDIO and track_pub.track:
                    logger.info(f"📻 Found existing agent audio track")
                    asyncio.create_task(self._subscribe_local_track(track_pub.track, recorder))
        except Exception as e:
            logger.error(f"❌ Local subscribe error: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _subscribe_local_track(self, audio_track: rtc.LocalAudioTrack, recorder: AudioRecorder):
        """Subscribe to a specific local audio track (agent's TTS)"""
        try:
            logger.info(f"🎤 Recording agent audio track")

            # Stream audio frames from agent's TTS
            audio_stream = rtc.AudioStream(audio_track)
            async for event in audio_stream:
                if not recorder.is_recording:
                    break
                # Write agent's audio to the same recorder
                recorder.write_frame(event.frame)

        except Exception as e:
            logger.error(f"❌ Agent audio track error: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def stop_recording(self, room_name: str) -> Optional[str]:
        """
        Stop recording and upload

        Args:
            room_name: Room identifier

        Returns:
            Room name (upload happens in background)
        """
        logger.info(f"🛑 Stopping recording: {room_name}")

        recorder = self.active_recordings.pop(room_name, None)
        if not recorder:
            logger.warning(f"⚠️ No active recording: {room_name}")
            logger.warning(f"   Active: {list(self.active_recordings.keys())}")
            return None

        wav_path = recorder.stop()
        if not wav_path:
            logger.warning(f"⚠️ No WAV file generated")
            return None

        # Upload in background
        logger.info(f"📤 Queuing upload: {wav_path.name}")
        asyncio.create_task(self._upload(wav_path, room_name))

        return room_name

    def get_recording_url(self, room_name: str) -> Optional[str]:
        """Get recording URL for a room"""
        return self.recording_urls.get(room_name)

    async def _upload(self, wav_path: Path, room_name: str) -> Optional[str]:
        """Upload WAV to OSS and store URL"""
        try:
            logger.info(f"☁️ Upload started: {wav_path.name}")

            if not self.bucket:
                logger.error("❌ OSS bucket not initialized")
                wav_path.unlink(missing_ok=True)
                return None

            if not wav_path.exists():
                logger.error(f"❌ WAV file not found: {wav_path}")
                return None

            file_size_mb = wav_path.stat().st_size / (1024 * 1024)
            logger.info(f"📦 File size: {file_size_mb:.2f}MB")

            oss_key = f"recordings/{wav_path.name}"

            logger.info(f"⬆️ Uploading to OSS: {oss_key}")
            await asyncio.to_thread(
                self.bucket.put_object_from_file,
                oss_key,
                str(wav_path)
            )

            oss_url = self.bucket.sign_url('GET', oss_key, 7 * 24 * 3600)

            # Store URL for later retrieval
            self.recording_urls[room_name] = oss_url

            logger.info(f"✅ Upload complete: {oss_key}")
            logger.info(f"🔗 URL: {oss_url[:100]}...")

            wav_path.unlink(missing_ok=True)
            logger.info(f"🧹 Local file deleted")
            return oss_url

        except Exception as e:
            logger.error(f"❌ Upload failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            wav_path.unlink(missing_ok=True)
            return None


# Global instance
audio_recorder = AudioRecorderService()
