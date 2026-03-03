# Voice Agent Platform - Flask Dashboard

A Flask-based dashboard for managing LiveKit voice agents with user authentication, call logs, and admin controls.

## Features

### User Features
- User signup and login
- Create and manage voice agents with custom prompts
- Make calls using agents
- View call logs and transcriptions
- Track minutes usage

### Admin Features
- Approve new user accounts
- Grant 5000 free minutes to approved users
- Add additional minutes to users
- Monitor all users and their activity
- View total calls and minutes usage

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Make sure your `.env` file has the following configurations:

```env
# Flask
FLASK_APP=app.py
SECRET_KEY=your-secret-key-here

# LiveKit
LIVEKIT_URL=wss://your-livekit-url
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
SIP_OUTBOUND_TRUNK_ID=ST_your_trunk_id

# Twilio
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
TWILIO_PHONE_NUMBER=+1234567890

# OpenAI
OPENAI_API_KEY=your-openai-key

# ElevenLabs
ELEVEN_LABS_API_KEY=your-elevenlabs-key
```

### 3. Initialize Database

Run the Flask app to create the database and default admin user:

```bash
python app.py
```

This will create:
- SQLite database: `voice_agent.db`
- Default admin user:
  - Username: `admin`
  - Password: `admin123`

**IMPORTANT:** Change the admin password after first login!

### 4. Run the Application

**CRITICAL: You need to run TWO separate processes!**

**Terminal 1 - LiveKit Agent (MUST BE RUNNING FOR CALLS):**
```bash
python agent.py dev
```
or double-click `run_agent.bat`

**Terminal 2 - Flask Dashboard:**
```bash
python app.py
```
or double-click `run_dashboard.bat`

The dashboard will be at `http://localhost:5000`

**⚠️ IMPORTANT: Keep the agent running in Terminal 1 at all times for calls to work!**

## Usage

### For Users

1. **Sign Up**
   - Go to `/signup` and create an account
   - Wait for admin approval

2. **Create Agent**
   - After approval, login and go to Dashboard
   - Click "Create New Agent"
   - Enter agent name, prompt, and voice ID
   - Submit to create

3. **Make Calls**
   - Click on an agent to view details
   - Enter phone number (with country code, e.g., +1234567890)
   - Click "Make Call"

4. **View Call Logs**
   - Click "Call Logs" in navigation
   - View all calls, transcriptions, and minutes used

### For Admins

1. **Login**
   - Username: `admin`
   - Password: `admin123`

2. **Approve Users**
   - View pending users in the dashboard
   - Click "Approve" to grant access and 5000 free minutes

3. **Add Minutes**
   - In the users table, click "Add Minutes"
   - Enter amount and submit

4. **Monitor Activity**
   - View total users, calls, and minutes
   - Monitor user balances and activity

## Database Schema

### User
- id, username, email, password
- is_admin, is_approved
- minutes_balance
- created_at

### Agent
- id, user_id, name, prompt, voice_id
- created_at

### CallLog
- id, user_id, agent_id
- from_number, to_number
- duration_seconds, minutes_used
- transcription, room_name, status
- created_at

## File Structure

```
nevox-livekit/
├── app.py                 # Main Flask application
├── agent.py              # LiveKit agent script
├── mak_call.py          # Call making utility
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables
├── voice_agent.db       # SQLite database
└── templates/           # HTML templates
    ├── base.html
    ├── login.html
    ├── signup.html
    ├── pending_approval.html
    ├── user_dashboard.html
    ├── admin_dashboard.html
    ├── create_agent.html
    ├── view_agent.html
    ├── call_logs.html
    └── view_call_log.html
```

## Security Notes

1. Change the default admin password immediately
2. Update `SECRET_KEY` in `.env` for production
3. Use HTTPS in production
4. Keep API keys secure and never commit them to version control
5. Consider using a production database (PostgreSQL/MySQL) instead of SQLite

## Future Enhancements

- Real-time call status updates via WebSocket
- Automatic transcription from LiveKit
- Call recording storage and playback
- Multiple voice IDs per agent
- User billing and payment integration
- Advanced analytics and reporting
- API endpoints for programmatic access

## Troubleshooting

### Call Shows "initiated" but Never Connects ⚠️ MOST COMMON ISSUE
**Problem:** The LiveKit agent is NOT running!

**Solution:**
1. Open a **NEW** terminal/command prompt window
2. Navigate to the project directory
3. Run: `python agent.py dev`
4. You should see output like "Connected to LiveKit server"
5. Keep this terminal open and running
6. Now try making a call from the dashboard

### Database Issues
```bash
# Delete database and recreate
rm voice_agent.db
python app.py
```

### Port Already in Use
```bash
# Change port in app.py
app.run(debug=True, port=5001)
```

### LiveKit Connection Issues
- Verify LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET in .env
- Check SIP_OUTBOUND_TRUNK_ID is correct (starts with ST_)
- Make sure the LiveKit agent is running: `python agent.py dev`
- Verify your Twilio phone number is set up correctly

## Support

For issues or questions, please check:
- LiveKit documentation: https://docs.livekit.io
- Flask documentation: https://flask.palletsprojects.com
