"""
Tool Service - Dynamically load and execute custom tools for voice agents

This service:
1. Loads tools from database
2. Creates function_tool instances at runtime
3. Executes different tool types (API call, webhook, RPC)
"""

import json
import logging
import sqlite3
import os
import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from livekit.agents import function_tool, RunContext, get_job_context

logger = logging.getLogger("tool_service")


class ToolService:
    """Service for managing and executing custom tools"""

    def __init__(self):
        self.db_path = self._get_db_path()
        logger.info(f"ToolService initialized with database: {self.db_path}")

    def _get_db_path(self) -> str:
        """Get the database path"""
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'voice_agent.db')
        if not os.path.exists(db_path):
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'voice_agent.db')
        return db_path

    def get_agent_tools(self, agent_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve all active tools for a specific agent

        Args:
            agent_id: The agent ID

        Returns:
            List of tool dictionaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Query to get all tools linked to this agent
            cursor.execute("""
                SELECT t.*
                FROM tool t
                INNER JOIN agent_tool at ON t.id = at.tool_id
                WHERE at.agent_id = ? AND t.is_active = 1
                ORDER BY t.created_at ASC
            """, (agent_id,))

            rows = cursor.fetchall()
            conn.close()

            tools = []
            for row in rows:
                tool = {
                    'id': row['id'],
                    'name': row['name'],
                    'description': row['description'],
                    'tool_type': row['tool_type'],
                    'config': json.loads(row['config']) if row['config'] else {}
                }
                tools.append(tool)

            logger.info(f"Loaded {len(tools)} tools for agent {agent_id}")
            return tools

        except sqlite3.Error as e:
            logger.error(f"Database error loading tools: {e}")
            return []
        except Exception as e:
            logger.error(f"Error loading tools: {e}")
            return []

    def create_function_tools(self, agent_id: int) -> List:
        """
        Create LiveKit function_tool instances from database tools

        Args:
            agent_id: The agent ID

        Returns:
            List of function_tool instances ready to use
        """
        tool_configs = self.get_agent_tools(agent_id)
        function_tools = []

        for tool_config in tool_configs:
            try:
                func_tool = self._create_tool_from_config(tool_config)
                if func_tool:
                    function_tools.append(func_tool)
                    logger.info(f"Created function tool: {tool_config['name']}")
            except Exception as e:
                logger.error(f"Error creating tool {tool_config['name']}: {e}")

        return function_tools

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
        parameters = config.get('parameters', {})  # Get parameter definition from config

        # Build parameter schema from config
        properties = {}
        required = []

        if parameters:
            for param_name, param_def in parameters.items():
                properties[param_name] = {
                    "type": param_def.get('type', 'string'),
                    "description": param_def.get('description', '')
                }
                if param_def.get('required', False):
                    required.append(param_name)

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

        # Define the async function that will be called
        async def api_call_handler(raw_arguments: dict, context: RunContext) -> str:
            """Dynamically created API call tool"""
            try:
                # Replace URL template variables like {{param}} with actual values
                final_url = url
                remaining_args = raw_arguments.copy()

                for param_name, param_value in raw_arguments.items():
                    template = f"{{{{{param_name}}}}}"  # {{param}}
                    if template in final_url:
                        final_url = final_url.replace(template, str(param_value))
                        # Remove from remaining args so it's not also passed as query param
                        remaining_args.pop(param_name, None)

                logger.info(f"API call URL after templating: {final_url}")

                async with aiohttp.ClientSession() as session:
                    if method == 'GET':
                        async with session.get(final_url, headers=headers, params=remaining_args) as resp:
                            if resp.status == 200:
                                data = await resp.text()
                                logger.info(f"API call to {final_url} successful")
                                return f"API call successful: {data[:200]}"
                            else:
                                logger.error(f"API call failed with status {resp.status}")
                                return f"API call failed with status {resp.status}"
                    else:  # POST
                        async with session.post(final_url, headers=headers, json=remaining_args) as resp:
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

        # Set the function name and docstring
        api_call_handler.__name__ = name
        api_call_handler.__doc__ = description

        # Create and return the function_tool with raw schema
        return function_tool(raw_schema=raw_schema)(api_call_handler)

    def _create_webhook_tool(self, name: str, description: str, config: Dict):
        """Create a webhook tool"""
        url = config.get('url', '')
        headers = config.get('headers', {})
        parameters = config.get('parameters', {})  # Get parameter definition from config

        # Build parameter schema from config
        properties = {}
        required = []

        if parameters:
            for param_name, param_def in parameters.items():
                properties[param_name] = {
                    "type": param_def.get('type', 'string'),
                    "description": param_def.get('description', '')
                }
                if param_def.get('required', False):
                    required.append(param_name)

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

                # Get current timestamp
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
                            logger.info(f"Webhook to {url} successful")
                            return f"Webhook successful: {data[:200]}"
                        else:
                            logger.error(f"Webhook failed with status {resp.status}")
                            return f"Webhook failed with status {resp.status}"
            except Exception as e:
                logger.error(f"Webhook error: {e}")
                return f"Webhook error: {str(e)}"

        webhook_handler.__name__ = name
        webhook_handler.__doc__ = description

        return function_tool(raw_schema=raw_schema)(webhook_handler)

    def _create_rpc_tool(self, name: str, description: str, config: Dict):
        """Create an RPC tool (forwards to frontend)"""
        rpc_method = config.get('method', name)
        timeout = config.get('timeout', 5.0)
        parameters = config.get('parameters', {})  # Get parameter definition from config

        # Build parameter schema from config
        properties = {}
        required = []

        if parameters:
            for param_name, param_def in parameters.items():
                properties[param_name] = {
                    "type": param_def.get('type', 'string'),
                    "description": param_def.get('description', '')
                }
                if param_def.get('required', False):
                    required.append(param_name)

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
