-analytics
-function tools
-prompt
- qalb e abbas comments
- if there is not trunk then dont use .env file default trunk - check
- if no trunk then dont use in make_call - done
- fixed number from dashboard 
- fixe archi/files
- improve agent  - done
- fixed inbound agent page / remove duplication - done
- recording - done
- make outbound scalable 


-- if user dont join the call ,,,greeting is added in chat transcriptin and that makes the call count and min deducted. - done

-- Call Log call type -  inbound + outbound - done
-- REMOVE Minutes Used  - done
-- Interest in call log table  - 
-- tools
-- inbound agent active 

1. FIX INBOUND FLOW FIRST - done
 - NO AGENT CREATIONS - done
 - CHECK INBOUND trunk setting - done

2. Check temperature 
3. Prompt blocks - done
4. Rags with Q/As - done
5. senti analysis -
6. add convo flow in the prompt - done
-
1. SIP Status - initiated  -> ringing -> active ->  completed/failed/no_answer
2. fix this as well
from_number=os.environ.get('SAUDI_PHONE_NUMBER', '966115108724'),
            
---

d(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
INFO:werkzeug:127.0.0.1 - - [21/Nov/2025 19:12:15] "GET /agent/30 HTTP/1.1" 200 -
2025-11-21 19:12:17,469 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:17,469 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:17,472 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
INFO:werkzeug:127.0.0.1 - - [21/Nov/2025 19:12:24] "GET /agent/create HTTP/1.1" 302 -
INFO:werkzeug:127.0.0.1 - - [21/Nov/2025 19:12:24] "GET /agents HTTP/1.1" 200 -
INFO:werkzeug:127.0.0.1 - - [21/Nov/2025 19:12:26] "GET /agent/30/edit HTTP/1.1" 200 -
2025-11-21 19:12:28,250 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:28,250 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:28,252 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:39,027 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:39,028 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:39,062 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:45,574 - INFO agent - 📊 Worker load: 2/15 active jobs (13% capacity) 
2025-11-21 19:12:49,783 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:49,784 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:49,820 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:12:55,957 - INFO livekit.agents - closing agent session due to participant disconnect (disable via `RoomInputOptions.close_on_disconnect=False`) {"room": "call-30-1763734262.302837", "participant": "phone_user", "reason": "CLIENT_INITIATED"}
2025-11-21 19:12:55,959 - INFO agent - 📴 SIP participant disconnected: phone_user {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:55,959 - DEBUG agent - ✅ Cancelling monitor task (call ended) {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:55,960 - INFO agent - 🔚 Ending room because phone user left... {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:55,964 - DEBUG agent - Monitor task cancelled (expected on call end) {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:55,964 - INFO agent - 🔄 Attempting to delete room (attempt 1/3) {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:55,981 - DEBUG livekit.agents - stream closed {"room": "call-30-1763734262.302837", "participant": "phone_user", "source": "SOURCE_MICROPHONE"}
2025-11-21 19:12:57,218 - DEBUG livekit.agents - shutting down job task {"room": "call-30-1763734262.302837", "reason": "", "user_initiated": false}
2025-11-21 19:12:57,224 - DEBUG livekit.agents - job exiting {"reason": "", "tid": 36544, "job_id": "AJ_vyrRmQ3m75Pa"}
2025-11-21 19:12:57,250 - INFO agent - 📊 Usage: UsageSummary(llm_prompt_tokens=0, llm_prompt_cached_tokens=0, llm_input_audio_tokens=0, llm_completion_tokens=0, llm_output_audio_tokens=0, tts_characters_count=143, tts_audio_duration=10.631836734693886, stt_audio_duration=0.0) {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:57,251 - INFO agent - 📝 Preparing transcription data... {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:57,251 - INFO agent -    Messages captured: 1 {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:57,251 - INFO agent -    Duration: 110s {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:57,252 - WARNING agent - ⚠️ Very few messages captured! Attempting final extraction... {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:57,252 - INFO agent - 📋 Final transcription: 1 messages {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:57,253 - INFO agent -    1. [AGENT] (initial_greeting): السلام عليكم، ؟ أنا نورا من نيفوكس.
نحن نقدم موظفين صوت ذكي للشركات، يردون على ع {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:57,254 - INFO agent - 🚀 Sending webhook: 1 messages, 110s duration {"room": "call-30-1763734262.302837"}
2025-11-21 19:12:57,256 - DEBUG agent - Conversation monitor cancelled {"room": "call-30-1763734262.302837"}
INFO:__main__:📥 Webhook received: {'room_name': 'call-30-1763734262.302837', 'duration': 110, 'transcription': 'AGENT: السلام عليكم، ؟ أنا نورا من نيفوكس.\nنحن نقدم موظفين صوت ذكي للشركات، يردون على عملائك ٢٤ ساعة بلهجة سعودية طبيعية.\nمعك دقيقتين أشرح لك الفكرة؟"', 'metadata': {'start_time': '2025-11-21T19:11:07.014157', 'end_time': '2025-11-21T19:12:57.253025', 'message_count': 1, 'messages': [{'timestamp': '2025-11-21T19:11:11.863771', 'role': 'agent', 'text': 'السلام عليكم، ؟ أنا نورا من نيفوكس.\nنحن نقدم موظفين صوت ذكي للشركات، يردون على عملائك ٢٤ ساعة بلهجة سعودية طبيعية.\nمعك دقيقتين أشرح لك الفكرة؟"', 'source': 'initial_greeting'}], 'sip_info': {'call_status': 'dialing', 'phone_number': '966510033081', 'trunk_phone_number': '2912919101', 'call_id': 'SCL_VJp94ptpZMuP', 'trunk_id': 'ST_tv54VjjFcjNN', 'participant_kind': 'SIP'}, 'recording_id': 'EG_8JYAYkgYbx8d'}, 'message_count': 1}
INFO:__main__:Processing: call-30-1763734262.302837, 1 messages, 110s
INFO:__main__:📞 SIP Status: dialing, Total messages: 1, User messages: 0, Duration: 110s
INFO:__main__:✅ Call completed (1 messages, 0 from user, duration: 110s, minutes: 2)
INFO:__main__:🔍 Analyzing customer interest for 1 messages...
2025-11-21 19:12:58,252 - INFO agent - ✅ Room deleted successfully: call-30-1763734262.302837 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:00,592 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:00,593 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:00,599 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
INFO:httpx:HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
INFO:__main__:✅ Interest analysis complete: Not Interested
INFO:__main__:🎙️ Processing recording EG_8JYAYkgYbx8d for call...
INFO:recording_service:🔍 Egress status: 3
INFO:recording_service:✅ Found OSS file in egress.file.filename: recordings/call-30-1763734262.302837_20251121_141108.mp4
INFO:recording_service:📊 File size: 1958528 bytes
INFO:recording_service:⏱️ Duration: 105824550184ms
INFO:recording_service:☁️ Recording file in OSS: recordings/call-30-1763734262.302837_20251121_141108.mp4
INFO:recording_service:✅ Generated signed URL for recording
INFO:__main__:✅ Recording saved to OSS: https://nevox-ai.oss-me-central-1.aliyuncs.com/recordings%2Fcall-30-1763734262.302837_20251121_14110...
INFO:__main__:💰 Deducted 2 minutes from user example@gmail.com
INFO:__main__:✅ Call log updated: call-30-1763734262.302837
INFO:werkzeug:127.0.0.1 - - [21/Nov/2025 19:13:03] "POST /webhook/call-ended HTTP/1.1" 200 -
2025-11-21 19:13:03,021 - INFO agent - ✅ Webhook delivered successfully! {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:03,021 - INFO agent -    Response: {
  "message": "Call processed: 1 messages",
  "success": true,
  "transcription_length": 150
}
 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:06,290 - DEBUG livekit.plugins.google - stream timed out, restarting. {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:06,353 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:06,354 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:06,555 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:11,366 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:11,367 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:11,400 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:17,585 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:17,586 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:17,600 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:22,297 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:22,297 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:22,309 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:28,545 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:28,545 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:28,548 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:33,179 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:33,180 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:33,182 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:35,641 - INFO agent - 📊 Worker load: 2/15 active jobs (13% capacity) 
2025-11-21 19:13:39,595 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:39,596 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:39,598 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:44,013 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:44,014 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:44,017 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:50,494 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:50,495 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:50,523 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:54,855 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:54,855 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:54,857 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:13:56,009 - INFO agent - 🔄 User state changed: away {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:56,011 - DEBUG agent - ⏭️ Ignoring user state change (call already ended) {"room": "call-30-1763734262.302837"}
2025-11-21 19:13:57,215 - ERROR livekit.agents - job shutdown is taking too much time.. {"tid": 36544, "job_id": "AJ_vyrRmQ3m75Pa"}
2025-11-21 19:14:01,542 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:14:01,542 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:14:01,545 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745800244048 {"room": "call-30-1763734262.302837"}
2025-11-21 19:14:05,919 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:14:05,921 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}
2025-11-21 19:14:05,924 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=2745781270992 {"room": "call-30-1763734100.011048"}

--

remove the trink ids from the .env file

-- i used wrong trunk id,

2025-11-19 03:41:16,990 - INFO livekit.agents - initializing job runner {"tid": 47604}
2025-11-19 03:41:16,990 - DEBUG asyncio - Using proactor: IocpProactor 
2025-11-19 03:41:16,991 - INFO livekit.agents - job runner initialized {"tid": 47604, "elapsed_time": 0.0}
2025-11-19 03:41:16,994 - INFO agent - 🎯 Room: call-28-1763505674.66421 {"room": "call-28-1763505674.66421"}
2025-11-19 03:41:16,995 - INFO agent - 📊 Participants: 0 {"room": "call-28-1763505674.66421"}
2025-11-19 03:41:17,104 - INFO agent - 📊 Worker load: 2/15 active jobs (13% capacity) 
INFO:werkzeug:127.0.0.1 - - [19/Nov/2025 03:41:17] "POST /agent/28/make-call HTTP/1.1" 500 -
2025-11-19 03:41:21,407 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=3201326480784 {"room": "call-28-1763505598.66656"}
2025-11-19 03:41:21,407 - DEBUG grpc._cython.cygrpc - [_cygrpc] Loaded running loop: id(loop)=3201326480784 {"room": "call-28-1763505598.66656"}