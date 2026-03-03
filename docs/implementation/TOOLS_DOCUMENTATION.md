# Custom Tools System Documentation

## Overview

The Custom Tools System allows you to extend your voice agents with custom functionality without modifying code. Tools can make API calls, trigger webhooks, or communicate with your frontend application.

## Features

- **API Call Tools**: Make HTTP GET/POST requests to external APIs
- **Webhook Tools**: POST data to custom webhooks for integrations
- **RPC Tools**: Forward calls to your frontend application via LiveKit RPC
- **Dynamic Loading**: Tools are loaded automatically when agents start
- **Multi-Agent Support**: Assign different tools to different agents

## Quick Start

### 1. Run the Migration

First, create the necessary database tables:

```bash
python migrate_tools.py
```

### 2. Access the Dashboard

Navigate to your dashboard and find the **Tools** section in the navigation menu.

### 3. Create Your First Tool

1. Click **"Create New Tool"**
2. Fill in the form:
   - **Name**: `get_weather` (use snake_case)
   - **Description**: "Get current weather for a given city. Use when user asks about weather."
   - **Tool Type**: Select "API Call"
   - **API URL**: `https://api.openweathermap.org/data/2.5/weather`
   - **Method**: GET
   - **Headers**: `{"Authorization": "Bearer YOUR_API_KEY"}`
3. Click **"Create Tool"**

### 4. Assign Tool to Agent

1. Go to **Agents** > Select your agent > **Edit**
2. Click **"Manage Tools"** or navigate to `/agents/{agent_id}/tools`
3. Check the tools you want to assign
4. Click **"Save Tool Selection"**

### 5. Test It

Make a call to your agent and ask about the weather! The agent will automatically use the tool when appropriate.

## Tool Types

### API Call Tool

Makes HTTP requests to external APIs.

**Configuration:**
- **URL**: The API endpoint
- **Method**: GET or POST
- **Headers**: JSON object with custom headers (optional)

**Example Use Cases:**
- Fetch weather data
- Look up product information
- Check stock prices
- Verify user information

**Example:**
```
Name: get_product_details
Description: Look up product details by product ID
URL: https://api.yourstore.com/products/{product_id}
Method: GET
Headers: {"Authorization": "Bearer YOUR_TOKEN"}
```

### Webhook Tool

POSTs data to a custom webhook URL.

**Configuration:**
- **URL**: The webhook endpoint
- **Headers**: JSON object with custom headers (optional)

**Payload Format:**
The webhook will receive:
```json
{
  "room_name": "call-123-456789",
  "timestamp": "2025-01-01T12:00:00",
  "data": {
    // Parameters passed by the agent
  }
}
```

**Example Use Cases:**
- Notify your CRM of call events
- Send data to Zapier/Make.com
- Trigger notifications in Slack/Discord
- Log events to external systems

**Example:**
```
Name: notify_crm
Description: Notify CRM when customer shows interest in a product
URL: https://hooks.zapier.com/hooks/catch/xxx/yyy/
Headers: {}
```

### RPC Tool

Forwards calls to your frontend application via LiveKit RPC.

**Configuration:**
- **Method**: The RPC method name (defaults to tool name)
- **Timeout**: How long to wait for response (seconds)

**Frontend Implementation Required:**
```javascript
import { RoomEvent } from 'livekit-client';

// Register RPC method handler
localParticipant.registerRpcMethod(
    'get_user_location',
    async (data) => {
        const position = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject);
        });

        return JSON.stringify({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
        });
    }
);
```

**Example Use Cases:**
- Get user's location from browser
- Trigger UI actions (show modal, navigate page)
- Access browser/device features
- Retrieve session-specific data

**Example:**
```
Name: get_user_location
Description: Get the user's current geolocation coordinates
Method: get_user_location
Timeout: 5.0
```

## Best Practices

### Tool Naming

- Use `snake_case` for tool names (e.g., `get_weather`, `send_email`)
- Make names descriptive and action-oriented
- Keep names concise (2-3 words max)

### Tool Descriptions

The description is **critical** for the AI to understand when to use the tool. Be specific:

❌ Bad: "Gets information"
✅ Good: "Look up product details by product ID. Use when user asks about a specific product."

❌ Bad: "Sends data somewhere"
✅ Good: "Notify sales team via webhook when customer expresses interest in premium plans."

### Security

- **Never expose API keys in URLs** - use headers instead
- Use environment variables for sensitive data
- Implement authentication on your webhook endpoints
- Validate all data on the receiving end

### Performance

- Keep API calls under 2-3 seconds when possible
- Use appropriate timeouts for RPC calls
- Consider caching for frequently accessed data

## Troubleshooting

### Tool Not Being Called

**Problem**: Agent doesn't use the tool even when expected.

**Solutions:**
1. Check tool description - make it more specific
2. Verify tool is assigned to the agent
3. Check tool is marked as "Active"
4. Review agent logs for errors

### API Call Failing

**Problem**: Tool returns error or doesn't work.

**Solutions:**
1. Test the API endpoint manually (Postman/curl)
2. Check headers are valid JSON
3. Verify API key/authentication
4. Check the API endpoint is accessible

### RPC Timeout

**Problem**: RPC tool times out.

**Solutions:**
1. Increase timeout value
2. Verify frontend RPC handler is registered
3. Check participant is connected
4. Review browser console for errors

## Advanced Usage

### Dynamic Parameters

Tools can accept parameters from the agent's conversation. The AI will automatically extract relevant information.

Example:
- User: "What's the weather in New York?"
- Agent calls: `get_weather(city="New York")`

### Error Handling

Tools automatically handle errors and report them back to the agent. The agent will inform the user if a tool fails.

### Tool Chaining

Agents can call multiple tools in sequence:

1. User: "Find the nearest store and get directions"
2. Agent calls: `find_nearest_store(city="New York")`
3. Agent calls: `get_directions(destination=store_address)`

## API Reference

### Database Schema

**Tool Table:**
```sql
CREATE TABLE tool (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    tool_type VARCHAR(20) NOT NULL,  -- 'api_call', 'webhook', 'rpc'
    config TEXT NOT NULL,  -- JSON configuration
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**AgentTool Table:**
```sql
CREATE TABLE agent_tool (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER NOT NULL,
    tool_id INTEGER NOT NULL,
    created_at TIMESTAMP,
    UNIQUE(agent_id, tool_id)
);
```

### Python API

You can also programmatically create tools:

```python
from app import db, Tool, AgentTool
import json

# Create a tool
tool = Tool(
    user_id=1,
    name='get_weather',
    description='Get weather for a city',
    tool_type='api_call',
    config=json.dumps({
        'url': 'https://api.weather.com/data',
        'method': 'GET',
        'headers': {}
    }),
    is_active=True
)
db.session.add(tool)
db.session.commit()

# Assign to agent
agent_tool = AgentTool(agent_id=1, tool_id=tool.id)
db.session.add(agent_tool)
db.session.commit()
```

## Examples

### Example 1: Weather API Tool

```
Name: get_weather
Description: Get current weather information for a specific city. Use when user asks about weather conditions.
Type: API Call
URL: https://api.openweathermap.org/data/2.5/weather?q={city}&appid=YOUR_API_KEY
Method: GET
Headers: {}
```

### Example 2: CRM Notification Webhook

```
Name: notify_sales_team
Description: Notify sales team via webhook when customer shows high interest in products or requests a callback.
Type: Webhook
URL: https://your-crm.com/webhooks/sales-notification
Headers: {"X-API-Key": "your_secret_key"}
```

### Example 3: Frontend Location RPC

```
Name: get_user_location
Description: Get the user's current browser geolocation. Use when user needs location-based services.
Type: RPC
Method: getUserLocation
Timeout: 5.0
```

## Support

For issues or questions:
1. Check agent logs in `/var/log/` or console output
2. Review this documentation
3. Test tools manually before assigning to agents
4. Check the LiveKit Agents documentation: https://docs.livekit.io/agents/

## Future Enhancements

Planned features:
- [ ] Custom Python code execution (sandboxed)
- [ ] Task groups for multi-step workflows
- [ ] Tool templates library
- [ ] Tool usage analytics
- [ ] Version control for tools
