"""
Tool Service - Dynamically load and execute custom tools for voice agents

This service:
1. Loads tools from database
2. Creates function_tool instances at runtime
3. Executes different tool types (API call, webhook, RPC)
4. CACHES tools for instant performance (Option 4)
5. PRE-WARMS cache at startup
"""

import json
import logging
import os
import sys
import time
import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from livekit.agents import function_tool, RunContext, get_job_context

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# SQLAlchemy ORM database access (replaces sqlite3)
from database import get_readonly_session, check_connection
from models import Agent, Tool, AgentTool

logger = logging.getLogger("tool_service")


class ToolService:
    """Service for managing and executing custom tools"""

    def __init__(self):
        # Tool cache for instant performance
        self._tool_cache = {}
        self._cache_ttl = 300  # 5 minutes

        # Verify database connection
        if not check_connection():
            logger.warning("Database connection check failed at ToolService init")
        else:
            logger.info("ToolService initialized with SQLAlchemy ORM")

    def preload_all_agents(self):
        """
        Pre-warm tool cache at startup for instant call performance.
        This method should be called once when the worker starts.
        Uses SQLAlchemy ORM for database-agnostic queries.
        """
        logger.info("=" * 60)
        logger.info("🔥 PRE-WARMING TOOL CACHE FOR ALL AGENTS")
        logger.info("=" * 60)

        start_time = time.time()

        try:
            # Get all agents using SQLAlchemy ORM
            with get_readonly_session() as session:
                agent_rows = session.query(Agent.id, Agent.name).order_by(Agent.id).all()
                # Convert to list of tuples (critical - access inside session!)
                agents = [(a.id, a.name) for a in agent_rows]

            if not agents:
                logger.warning("⚠️  No agents found in database")
                return

            logger.info(f"📦 Loading tools for {len(agents)} agents...")

            success_count = 0
            fail_count = 0

            for agent_id, agent_name in agents:
                try:
                    tools = self.create_function_tools(agent_id)
                    success_count += 1
                    logger.info(f"   ✅ Agent {agent_id} ({agent_name}): {len(tools)} tools cached")
                except Exception as e:
                    fail_count += 1
                    logger.warning(f"   ⚠️  Agent {agent_id} ({agent_name}): {e}")

            duration = time.time() - start_time

            # Print summary
            logger.info("=" * 60)
            logger.info(f"✅ TOOL CACHE PRE-WARMING COMPLETE")
            logger.info(f"   Total agents: {len(agents)}")
            logger.info(f"   Successfully cached: {success_count}")
            logger.info(f"   Failed: {fail_count}")
            logger.info(f"   Duration: {duration:.2f}s")
            logger.info(f"   🚀 All calls will now start instantly!")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"❌ Pre-warming failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def get_agent_tools(self, agent_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve all active tools for a specific agent using SQLAlchemy ORM.

        Args:
            agent_id: The agent ID

        Returns:
            List of tool dictionaries
        """
        try:
            with get_readonly_session() as session:
                # Query to get all active tools linked to this agent
                tool_rows = session.query(Tool).join(AgentTool).filter(
                    AgentTool.agent_id == agent_id,
                    Tool.is_active == True
                ).order_by(Tool.created_at.asc()).all()

                # Convert to list of dicts (critical - access inside session!)
                tools = []
                for t in tool_rows:
                    tool = {
                        'id': t.id,
                        'name': t.name,
                        'description': t.description,
                        'tool_type': t.tool_type,
                        'config': json.loads(t.config) if t.config else {}
                    }
                    tools.append(tool)

            logger.debug(f"Loaded {len(tools)} tool configs for agent {agent_id}")
            return tools

        except Exception as e:
            logger.error(f"Error loading tools: {e}")
            return []

    def create_function_tools(self, agent_id: int) -> List:
        """
        Create LiveKit function_tool instances from database tools WITH CACHING

        Args:
            agent_id: The agent ID

        Returns:
            List of function_tool instances ready to use
        """
        # Check cache first
        if agent_id in self._tool_cache:
            cached_data = self._tool_cache[agent_id]
            if time.time() - cached_data['timestamp'] < self._cache_ttl:
                logger.debug(f"📦 Using cached tools for agent {agent_id}")
                return cached_data['tools']
        
        # Cache miss - load from database
        logger.debug(f"🔧 Loading tools from database for agent {agent_id}...")
        start = time.time()
        
        tool_configs = self.get_agent_tools(agent_id)
        function_tools = []

        for tool_config in tool_configs:
            try:
                func_tool = self._create_tool_from_config(tool_config)
                if func_tool:
                    function_tools.append(func_tool)
                    logger.debug(f"Created function tool: {tool_config['name']}")
            except Exception as e:
                logger.error(f"Error creating tool {tool_config['name']}: {e}")

        duration = (time.time() - start) * 1000
        logger.debug(f"✅ Created {len(function_tools)} tools in {duration:.0f}ms")
        
        # Cache the result
        self._tool_cache[agent_id] = {
            'tools': function_tools,
            'timestamp': time.time()
        }
        
        return function_tools

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        return {
            'cached_agents': len(self._tool_cache),
            'cache_size': len(self._tool_cache)
        }

    def _create_tool_from_config(self, tool_config: Dict[str, Any]):
        """
        Create a function_tool from a configuration dictionary

        Args:
            tool_config: Tool configuration from database

        Returns:
            A function_tool instance
        """
        tool_type = tool_config['tool_type']
        name = tool_config['name']
        description = tool_config['description']
        config = tool_config['config']

        # Create the appropriate tool based on type
        if tool_type == 'api_call':
            return self._create_api_call_tool(name, description, config)
        elif tool_type == 'webhook':
            return self._create_webhook_tool(name, description, config)
        elif tool_type == 'rpc':
            return self._create_rpc_tool(name, description, config)
        else:
            logger.warning(f"Unknown tool type: {tool_type}")
            return None

    def _create_api_call_tool(self, name: str, description: str, config: Dict):
        """Create an API call tool"""
        url = config.get('url', '')
        method = config.get('method', 'GET').upper()
        headers = config.get('headers', {})
        parameters = config.get('parameters', {})

        # Build parameter schema from config
        properties = {}
        required = []

        if parameters:
            for param_name, param_def in parameters.items():
                # Handle both formats:
                # Format 1 (correct): {"param": {"type": "string", "description": "...", "required": true}}
                # Format 2 (legacy/template): {"body": "Hi {{name}}", "to": "{{phone}}"} - extract {{vars}}
                if isinstance(param_def, dict):
                    # Correct format - use as-is
                    properties[param_name] = {
                        "type": param_def.get('type', 'string'),
                        "description": param_def.get('description', '')
                    }
                    if param_def.get('required', False):
                        required.append(param_name)
                elif isinstance(param_def, str):
                    # Legacy format - extract template variables like {{var_name}}
                    import re
                    template_vars = re.findall(r'\{\{(\w+)\}\}', param_def)
                    for var in template_vars:
                        if var not in properties:
                            properties[var] = {
                                "type": "string",
                                "description": f"Value for {var}"
                            }
                            required.append(var)
                    logger.debug(f"Extracted template vars from '{param_name}': {template_vars}")

        # Define raw schema with dynamic parameters
        raw_schema = {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False
            }
        }

        # Store the original parameters config for template substitution
        original_params = parameters.copy() if parameters else {}

        # Define the async function that will be called
        async def api_call_handler(raw_arguments: dict, context: RunContext) -> str:
            """Dynamically created API call tool"""
            try:
                # Replace URL template variables like {{param}} with actual values
                final_url = url
                for param_name, param_value in raw_arguments.items():
                    template = f"{{{{{param_name}}}}}"
                    if template in final_url:
                        final_url = final_url.replace(template, str(param_value))

                logger.info(f"API call URL after templating: {final_url}")

                # Build payload: if original_params has template strings, substitute them
                # Otherwise just use raw_arguments directly
                payload = {}
                has_templates = any(isinstance(v, str) and '{{' in v for v in original_params.values())
                
                if has_templates:
                    # Template format: {"body": "Hi {{name}}", "to": "{{phone}}"}
                    # Substitute all {{var}} with actual values from raw_arguments
                    for key, template_str in original_params.items():
                        if isinstance(template_str, str):
                            result = template_str
                            for arg_name, arg_value in raw_arguments.items():
                                result = result.replace(f"{{{{{arg_name}}}}}", str(arg_value))
                            payload[key] = result
                        else:
                            payload[key] = template_str
                    logger.debug(f"Built payload from templates: {payload}")
                else:
                    # Standard format: just pass raw_arguments
                    payload = raw_arguments

                async with aiohttp.ClientSession() as session:
                    if method == 'GET':
                        async with session.get(final_url, headers=headers, params=payload) as resp:
                            if resp.status == 200:
                                data = await resp.text()
                                logger.info(f"API call to {final_url} successful")
                                return f"API call successful: {data[:200]}"
                            else:
                                logger.error(f"API call failed with status {resp.status}")
                                return f"API call failed with status {resp.status}"
                    else:  # POST
                        async with session.post(final_url, headers=headers, json=payload) as resp:
                            if resp.status in [200, 201]:
                                data = await resp.text()
                                logger.info(f"API call to {final_url} successful")
                                return f"API call successful: {data[:200]}"
                            else:
                                logger.error(f"API call failed with status {resp.status}")
                                return f"API call failed with status {resp.status}"
            except Exception as e:
                logger.error(f"API call error: {e}")
                return f"API call error: {str(e)}"

        api_call_handler.__name__ = name
        api_call_handler.__doc__ = description

        return function_tool(raw_schema=raw_schema)(api_call_handler)

    def _create_webhook_tool(self, name: str, description: str, config: Dict):
        """Create a webhook tool"""
        url = config.get('url', '')
        headers = config.get('headers', {})
        parameters = config.get('parameters', {})

        # Build parameter schema from config
        properties = {}
        required = []

        if parameters:
            for param_name, param_def in parameters.items():
                # Handle both formats:
                # Format 1 (correct): {"param": {"type": "string", "description": "...", "required": true}}
                # Format 2 (legacy/template): {"body": "Hi {{name}}", "to": "{{phone}}"} - extract {{vars}}
                if isinstance(param_def, dict):
                    # Correct format - use as-is
                    properties[param_name] = {
                        "type": param_def.get('type', 'string'),
                        "description": param_def.get('description', '')
                    }
                    if param_def.get('required', False):
                        required.append(param_name)
                elif isinstance(param_def, str):
                    # Legacy format - extract template variables like {{var_name}}
                    import re
                    template_vars = re.findall(r'\{\{(\w+)\}\}', param_def)
                    for var in template_vars:
                        if var not in properties:
                            properties[var] = {
                                "type": "string",
                                "description": f"Value for {var}"
                            }
                            required.append(var)
                    logger.debug(f"Extracted template vars from '{param_name}': {template_vars}")

        # Define raw schema with dynamic parameters
        raw_schema = {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False
            }
        }

        async def webhook_handler(raw_arguments: dict, context: RunContext) -> str:
            """Dynamically created webhook tool"""
            try:
                # Get room information from job context
                try:
                    job_ctx = get_job_context()
                    room_name = job_ctx.room.name if job_ctx and job_ctx.room else 'unknown'
                except:
                    room_name = 'unknown'

                timestamp = datetime.now(timezone.utc).isoformat()

                payload = {
                    'room_name': room_name,
                    'timestamp': timestamp,
                    'data': raw_arguments
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status in [200, 201, 202]:
                            data = await resp.text()
                            logger.info(f"Webhook to {url} successful, response: {data[:500]}")
                            
                            # Try to parse JSON and return it nicely for the LLM
                            try:
                                json_data = json.loads(data)
                                # Return the full JSON data so LLM can use it
                                # Limit to 2000 chars to avoid token overflow
                                return json.dumps(json_data, ensure_ascii=False, indent=2)[:2000]
                            except json.JSONDecodeError:
                                # Not JSON, return raw text
                                return data[:2000]
                        else:
                            error_text = await resp.text()
                            logger.error(f"Webhook failed with status {resp.status}: {error_text[:200]}")
                            return f"Error: Request failed with status {resp.status}"
            except Exception as e:
                logger.error(f"Webhook error: {e}")
                return f"Error: {str(e)}"

        webhook_handler.__name__ = name
        webhook_handler.__doc__ = description

        return function_tool(raw_schema=raw_schema)(webhook_handler)

    def _create_rpc_tool(self, name: str, description: str, config: Dict):
        """Create an RPC tool (forwards to frontend)"""
        rpc_method = config.get('method', name)
        timeout = config.get('timeout', 5.0)
        parameters = config.get('parameters', {})

        # Build parameter schema from config
        properties = {}
        required = []

        if parameters:
            for param_name, param_def in parameters.items():
                # Handle both formats:
                # Format 1 (correct): {"param": {"type": "string", "description": "...", "required": true}}
                # Format 2 (legacy/template): {"body": "Hi {{name}}", "to": "{{phone}}"} - extract {{vars}}
                if isinstance(param_def, dict):
                    # Correct format - use as-is
                    properties[param_name] = {
                        "type": param_def.get('type', 'string'),
                        "description": param_def.get('description', '')
                    }
                    if param_def.get('required', False):
                        required.append(param_name)
                elif isinstance(param_def, str):
                    # Legacy format - extract template variables like {{var_name}}
                    import re
                    template_vars = re.findall(r'\{\{(\w+)\}\}', param_def)
                    for var in template_vars:
                        if var not in properties:
                            properties[var] = {
                                "type": "string",
                                "description": f"Value for {var}"
                            }
                            required.append(var)
                    logger.debug(f"Extracted template vars from '{param_name}': {template_vars}")

        # Define raw schema with dynamic parameters
        raw_schema = {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False
            }
        }

        async def rpc_handler(raw_arguments: dict, context: RunContext) -> str:
            """Dynamically created RPC tool"""
            try:
                job_ctx = get_job_context()
                room = job_ctx.room

                # Get first remote participant (frontend)
                participant_identity = next(iter(room.remote_participants))

                # Call RPC method on frontend
                response = await room.local_participant.perform_rpc(
                    destination_identity=participant_identity,
                    method=rpc_method,
                    payload=json.dumps(raw_arguments),
                    response_timeout=timeout,
                )

                logger.info(f"RPC call to {rpc_method} successful")
                return f"RPC call successful: {response}"

            except Exception as e:
                logger.error(f"RPC error: {e}")
                return f"RPC error: {str(e)}"

        rpc_handler.__name__ = name
        rpc_handler.__doc__ = description

        return function_tool(raw_schema=raw_schema)(rpc_handler)


# Global service instance
tool_service = ToolService()