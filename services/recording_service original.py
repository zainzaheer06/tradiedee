"""
Direct Audio Recording Service - Dual Voice (Customer + Agent)
Records both SIP participant and agent with proper audio mixing
Uploads WAV files directly to Alibaba OSS
"""

import os
import asyncio
import logging
import wave
import numpy as np
import oss2
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from collections import defaultdict
from dotenv import load_dotenv
from livekit import rtc

load_dotenv()
logger = logging.getLogger(__name__)

# OSS Configuration
OSS_ACCESS_KEY_ID = os.getenv('OSS_ACCESS_KEY_ID')
OSS_ACCESS_KEY_SECRET = os.getenv('OSS_ACCESS_KEY_SECRET')
OSS_BUCKET_NAME = os.getenv('OSS_BUCKET_NAME')
OSS_ENDPOINT = os.getenv('OSS_ENDPOINT')

# Recording settings - OPTIMIZED FOR VOICE
RECORDINGS_DIR = Path("./recordings_temp")
RECORDINGS_DIR.mkdir(exist_ok=True)
SAMPLE_RATE = 16000  # 16kHz for voice (standard for telephony)
CHANNELS = 1  # Mono (we'll mix to mono)
SAMPLE_WIDTH = 2  # 16-bit


class DualVoiceRecorder:
    """Records and mixes audio from multiple participants"""

    def __init__(self, room_name: str):
        self.room_name = room_name
        self.timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        self.filename = f"{room_name}_{self.timestamp}.wav"
        self.wav_path = RECORDINGS_DIR / self.filename
        self.wav_file = None
        self.is_recording = False
        
        # ✅ Audio mixing buffers (per participant)
        self.audio_buffers: Dict[str, List[np.ndarray]] = defaultdict(list)
        self.buffer_lock = asyncio.Lock()
        self.total_frames = 0

    def start(self):
        """Initialize WAV file"""
        try:
            self.wav_file = wave.open(str(self.wav_path), 'wb')
            self.wav_file.setnchannels(CHANNELS)
            self.wav_file.setsampwidth(SAMPLE_WIDTH)
            self.wav_file.setframerate(SAMPLE_RATE)
            self.is_recording = True
            logger.info(f"🎙️ Dual-voice recording started: {self.filename}")
        except Exception as e:
            logger.error(f"❌ Failed to start recording: {e}")
            self.is_recording = False

    async def write_frame(self, participant_id: str, frame: rtc.AudioFrame):
        """Write audio frame with participant tracking"""
        if not self.is_recording:
            return

        try:
            # Convert frame to target format
            converted_frame = frame.remix_and_resample(
                sample_rate=SAMPLE_RATE,
                num_channels=CHANNELS
            )
            
            # Convert to numpy array
            audio_data = np.frombuffer(
                converted_frame.data,
                dtype=np.int16
            )
            
            # ✅ Store in participant buffer
            async with self.buffer_lock:
                self.audio_buffers[participant_id].append(audio_data)
                
                # ✅ Mix and write every 50 frames (~3 seconds at 16kHz)
                if sum(len(buf) for buf in self.audio_buffers.values()) >= 50:
                    await self._mix_and_write()

        except Exception as e:
            # Fallback for older LiveKit versions
            try:
                if hasattr(frame, 'data'):
                    audio_bytes = bytes(frame.data)
                    audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
                    
                    async with self.buffer_lock:
                        self.audio_buffers[participant_id].append(audio_data)
                        
                        if sum(len(buf) for buf in self.audio_buffers.values()) >= 50:
                            await self._mix_and_write()
            except Exception as fallback_error:
                logger.debug(f"Frame write error: {fallback_error}")

    async def _mix_and_write(self):
        """Mix audio from all participants and write to file"""
        try:
            if not self.audio_buffers:
                return
            
            # Get all audio chunks
            all_chunks = []
            for participant_id, chunks in self.audio_buffers.items():
                if chunks:
                    # Concatenate chunks from this participant
                    participant_audio = np.concatenate(chunks)
                    all_chunks.append(participant_audio)
            
            if not all_chunks:
                return
            
            # ✅ Find the longest audio stream
            max_length = max(len(chunk) for chunk in all_chunks)
            
            # ✅ Pad shorter streams with silence
            padded_chunks = []
            for chunk in all_chunks:
                if len(chunk) < max_length:
                    padding = np.zeros(max_length - len(chunk), dtype=np.int16)
                    padded_chunk = np.concatenate([chunk, padding])
                else:
                    padded_chunk = chunk
                padded_chunks.append(padded_chunk)
            
            # ✅ Mix by averaging (prevents clipping)
            if len(padded_chunks) > 1:
                mixed = np.mean(padded_chunks, axis=0).astype(np.int16)
            else:
                mixed = padded_chunks[0]
            
            # Write mixed audio to file
            self.wav_file.writeframes(mixed.tobytes())
            self.total_frames += len(mixed)
            
            # Clear buffers
            self.audio_buffers.clear()
            
        except Exception as e:
            logger.error(f"❌ Mix error: {e}")

    async def stop(self) -> Optional[Path]:
        """Close WAV file after final mix"""
        if not self.wav_file:
            return None

        try:
            # ✅ Write any remaining buffered audio
            async with self.buffer_lock:
                if self.audio_buffers:
                    await self._mix_and_write()
            
            self.wav_file.close()
            self.is_recording = False

            if self.wav_path.exists() and self.wav_path.stat().st_size > 1000:
                size_mb = self.wav_path.stat().st_size / (1024 * 1024)
                duration_s = self.total_frames / SAMPLE_RATE if self.total_frames > 0 else 0
                logger.info(f"✅ Recording saved: {self.filename} ({size_mb:.1f}MB, {duration_s:.1f}s)")
                return self.wav_path
            else:
                logger.warning(f"⚠️ Recording too small, deleting")
                self.wav_path.unlink(missing_ok=True)
                return None
                
        except Exception as e:
            logger.error(f"❌ Stop error: {e}")
            return None


class AudioRecorderService:
    """Service for dual-voice audio recording"""

    def __init__(self):
        try:
            auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
            self.bucket = oss2.Bucket(auth, f'https://{OSS_ENDPOINT}', OSS_BUCKET_NAME)
            logger.info("✅ OSS client initialized")
        except Exception as e:
            logger.error(f"❌ OSS init failed: {e}")
            self.bucket = None

        self.active_recordings: Dict[str, DualVoiceRecorder] = {}
        self.recording_urls: Dict[str, str] = {}  # Store URLs for retrieval

    async def start_recording(self, room: rtc.Room) -> Optional[str]:
        """
        Start recording room audio - BOTH customer AND agent

        Args:
            room: LiveKit Room object

        Returns:
            Room name as recording ID
        """
        room_name = room.name

        try:
            recorder = DualVoiceRecorder(room_name)
            recorder.start()

            if not recorder.is_recording:
                logger.error(f"❌ Failed to initialize recorder")
                return None

            self.active_recordings[room_name] = recorder
            logger.info(f"🎙️ Dual-voice recorder initialized: {room_name}")

            # ✅ Subscribe to ALL remote participants (customer + agent)
            for participant in room.remote_participants.values():
                logger.info(f"📻 Found participant: {participant.identity} (Kind: {participant.kind})")
                asyncio.create_task(self._subscribe(participant, recorder))

            # ✅ Handle NEW participants
            @room.on("participant_connected")
            def on_participant_connected(participant: rtc.RemoteParticipant):
                logger.info(f"📻 New participant: {participant.identity} (Kind: {participant.kind})")
                asyncio.create_task(self._subscribe(participant, recorder))

            logger.info(f"✅ Recording active (dual-voice mode)")
            return room_name

        except Exception as e:
            logger.error(f"❌ Start recording failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def _subscribe(self, participant: rtc.RemoteParticipant, recorder: DualVoiceRecorder):
        """Subscribe to participant audio (customer OR agent)"""
        try:
            participant_id = participant.identity
            participant_type = "SIP (Customer)" if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP else "Agent"
            
            logger.info(f"🔍 Subscribing to {participant_type}: {participant_id}")
            
            # Wait for tracks
            await asyncio.sleep(0.5)
            
            # Find audio track
            audio_track = None
            for track_sid, publication in participant.track_publications.items():
                if publication.kind == rtc.TrackKind.KIND_AUDIO:
                    if publication.track:
                        audio_track = publication.track
                        logger.info(f"✅ Found audio track: {track_sid} ({participant_type})")
                        break

            if not audio_track:
                logger.warning(f"⚠️ No audio track for {participant_id}")
                return

            logger.info(f"📻 Recording {participant_type} audio: {participant_id}")

            # ✅ Stream audio frames with participant ID for mixing
            audio_stream = rtc.AudioStream(audio_track)
            
            frame_count = 0
            async for frame in audio_stream:
                if not recorder.is_recording:
                    logger.info(f"🛑 Recording stopped, ending stream for {participant_id}")
                    break
                
                await recorder.write_frame(participant_id, frame)
                frame_count += 1
                
                # Log progress every 500 frames
                if frame_count % 500 == 0:
                    logger.debug(f"📊 {participant_type} stream: {frame_count} frames")

            logger.info(f"✅ Stream complete: {frame_count} frames from {participant_type}")

        except Exception as e:
            logger.error(f"❌ Subscribe error for {participant.identity}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def stop_recording(self, room_name: str) -> Optional[str]:
        """Stop recording and upload WAV"""
        logger.info(f"🛑 Stopping dual-voice recording: {room_name}")

        recorder = self.active_recordings.pop(room_name, None)
        if not recorder:
            logger.warning(f"⚠️ No active recording: {room_name}")
            return None

        wav_path = await recorder.stop()
        if not wav_path:
            logger.warning(f"⚠️ No valid WAV file generated")
            return None

        # Upload WAV directly (no conversion)
        logger.info(f"📤 Uploading WAV file...")
        upload_url = await self._upload(wav_path)

        # Store URL for later retrieval
        if upload_url:
            self.recording_urls[room_name] = upload_url

        return upload_url

    def get_recording_url(self, room_name: str) -> Optional[str]:
        """Get recording URL for a room"""
        return self.recording_urls.get(room_name)

    async def _upload(self, file_path: Path) -> Optional[str]:
        """Upload WAV file to OSS with retry"""
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"☁️ Upload attempt {attempt}/{max_retries}: {file_path.name}")

                if not self.bucket:
                    logger.error("❌ OSS bucket not initialized")
                    file_path.unlink(missing_ok=True)
                    return None

                if not file_path.exists():
                    logger.error(f"❌ File not found: {file_path}")
                    return None

                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                logger.info(f"📦 File size: {file_size_mb:.2f}MB")

                oss_key = f"recordings/{file_path.name}"

                # Upload with timeout
                await asyncio.wait_for(
                    asyncio.to_thread(
                        self.bucket.put_object_from_file,
                        oss_key,
                        str(file_path)
                    ),
                    timeout=60
                )

                # Generate signed URL
                oss_url = self.bucket.sign_url('GET', oss_key, 7 * 24 * 3600)
                logger.info(f"✅ Upload successful: {oss_key}")
                logger.info(f"🔗 URL: {oss_url[:100]}...")

                # Clean up
                file_path.unlink(missing_ok=True)
                logger.info(f"🧹 Local file deleted")

                return oss_url

            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Upload timeout (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)

            except Exception as e:
                logger.error(f"❌ Upload error (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)

        logger.error(f"❌ Upload failed after {max_retries} attempts")
        file_path.unlink(missing_ok=True)
        return None


# Global instance
audio_recorder = AudioRecorderService()