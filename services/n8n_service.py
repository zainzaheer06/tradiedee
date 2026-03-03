"""
n8n Workflow Service for WhatsApp Agent Integration

Generates n8n workflow JSON dynamically and manages workflows via the n8n REST API.
Each WhatsApp agent gets its own n8n workflow with:
  - Webhook trigger (receives WhatsApp messages)
  - Message routing (text/voice/image/document)
  - Media handling (download, transcribe, analyze)
  - AI Agent with customer's prompt + tools
  - Response routing (text or voice reply)

n8n API Docs: https://docs.n8n.io/api/
"""
import os
import json
import uuid
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

# n8n API Configuration
N8N_API_URL = os.environ.get('N8N_API_URL', 'https://automation.nevoxai.com/api/v1')
N8N_API_KEY = os.environ.get('N8N_API_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxYjVjYjU4ZC04YWIwLTQ2OWMtYWFkMS1mNTcyNDk4NmJjNzUiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcwODIyMzYxfQ.VOVL0mZvnqAtpeWNvztmuFKIhWFEb_iTpVDq4-RNLCU')
N8N_OPENAI_CREDENTIAL_ID = os.environ.get('N8N_OPENAI_CREDENTIAL_ID', 'KQ0gg0kyk4bsjjJL')
N8N_OPENAI_CREDENTIAL_NAME = os.environ.get('N8N_OPENAI_CREDENTIAL_NAME', 'OpenAi account')


class N8nService:
    """Manages n8n workflows for WhatsApp agents"""

    def __init__(self):
        self.api_url = N8N_API_URL.rstrip('/')
        self.api_key = N8N_API_KEY
        self.openai_cred_id = N8N_OPENAI_CREDENTIAL_ID
        self.openai_cred_name = N8N_OPENAI_CREDENTIAL_NAME

    @property
    def headers(self):
        return {
            'X-N8N-API-KEY': self.api_key,
            'Content-Type': 'application/json'
        }

    # =========================================================================
    # n8n API Operations
    # =========================================================================

    def create_workflow(self, whatsapp_agent) -> dict:
        """
        Generate workflow JSON and create it in n8n.

        Args:
            whatsapp_agent: WhatsAppAgent model instance (with agent relationship loaded)

        Returns:
            dict with 'success', 'workflow_id', 'webhook_path', or 'error'
        """
        try:
            webhook_path = f"wa-agent-{whatsapp_agent.id}-{uuid.uuid4().hex[:8]}"
            workflow_json = self._generate_workflow_json(whatsapp_agent, webhook_path)

            resp = requests.post(
                f"{self.api_url}/workflows",
                headers=self.headers,
                json=workflow_json,
                timeout=30
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    'success': True,
                    'workflow_id': str(data.get('id', '')),
                    'webhook_path': webhook_path
                }
            else:
                logger.error(f"n8n create workflow failed: {resp.status_code} - {resp.text}")
                return {
                    'success': False,
                    'error': f"n8n API error ({resp.status_code}): {resp.text[:200]}"
                }

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'n8n API timeout - please try again'}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Cannot connect to n8n - check if automation.nevoxai.com is accessible'}
        except Exception as e:
            logger.exception(f"Error creating n8n workflow: {e}")
            return {'success': False, 'error': str(e)}

    def activate_workflow(self, workflow_id: str) -> dict:
        """Activate a workflow in n8n"""
        try:
            resp = requests.post(
                f"{self.api_url}/workflows/{workflow_id}/activate",
                headers=self.headers,
                timeout=15
            )
            if resp.status_code == 200:
                return {'success': True}
            else:
                return {'success': False, 'error': f"Activate failed ({resp.status_code}): {resp.text[:200]}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def deactivate_workflow(self, workflow_id: str) -> dict:
        """Deactivate a workflow in n8n"""
        try:
            resp = requests.post(
                f"{self.api_url}/workflows/{workflow_id}/deactivate",
                headers=self.headers,
                timeout=15
            )
            if resp.status_code == 200:
                return {'success': True}
            else:
                return {'success': False, 'error': f"Deactivate failed ({resp.status_code}): {resp.text[:200]}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def update_workflow(self, workflow_id: str, whatsapp_agent) -> dict:
        """Update an existing workflow in n8n with new config"""
        try:
            webhook_path = whatsapp_agent.webhook_path
            workflow_json = self._generate_workflow_json(whatsapp_agent, webhook_path)

            resp = requests.put(
                f"{self.api_url}/workflows/{workflow_id}",
                headers=self.headers,
                json=workflow_json,
                timeout=30
            )

            if resp.status_code == 200:
                return {'success': True}
            else:
                return {'success': False, 'error': f"Update failed ({resp.status_code}): {resp.text[:200]}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_workflow(self, workflow_id: str) -> dict:
        """Delete a workflow from n8n"""
        try:
            resp = requests.delete(
                f"{self.api_url}/workflows/{workflow_id}",
                headers=self.headers,
                timeout=15
            )
            if resp.status_code in (200, 204):
                return {'success': True}
            else:
                return {'success': False, 'error': f"Delete failed ({resp.status_code}): {resp.text[:200]}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_workflow_status(self, workflow_id: str) -> dict:
        """Get workflow info from n8n"""
        try:
            resp = requests.get(
                f"{self.api_url}/workflows/{workflow_id}",
                headers=self.headers,
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    'success': True,
                    'active': data.get('active', False),
                    'name': data.get('name', ''),
                    'updated_at': data.get('updatedAt', '')
                }
            else:
                return {'success': False, 'error': f"Status check failed ({resp.status_code})"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def test_connection(self) -> dict:
        """Test the n8n API connection"""
        try:
            resp = requests.get(
                f"{self.api_url}/workflows",
                headers=self.headers,
                params={'limit': 1},
                timeout=10
            )
            if resp.status_code == 200:
                return {'success': True, 'message': 'Connected to n8n successfully'}
            else:
                return {'success': False, 'error': f"Connection test failed ({resp.status_code})"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # Workflow JSON Generation
    # =========================================================================

    def _debug_print_workflow(self, workflow_json: dict):
        """Debug helper - print workflow structure for debugging"""
        print("\n" + "=" * 80)
        print("DEBUG: Generated Workflow Structure")
        print("=" * 80)
        print(f"Nodes count: {len(workflow_json.get('nodes', []))}")
        for node in workflow_json.get('nodes', []):
            print(f"  - {node.get('name', 'UNNAMED')}: type={node.get('type')}")
            if 'toolHttpRequest' in node.get('type', ''):
                print(f"    Description: {node.get('parameters', {}).get('description')}")
                print(f"    URL: {node.get('parameters', {}).get('url')}")
                print(f"    Method: {node.get('parameters', {}).get('method')}")
                print(f"    Has bodyParameters: {'bodyParameters' in node.get('parameters', {})}")
                print(f"    Has queryParameters: {'queryParameters' in node.get('parameters', {})}")
                params = node.get('parameters', {})
                if 'bodyParameters' in params:
                    print(f"    Body Params: {json.dumps(params['bodyParameters'], indent=6)}")
                if 'queryParameters' in params:
                    print(f"    Query Params: {json.dumps(params['queryParameters'], indent=6)}")
        print("=" * 80 + "\n")

    def _generate_workflow_json(self, wa_agent, webhook_path: str) -> dict:
        """
        Generate the complete n8n workflow JSON for a WhatsApp agent.

        Dynamically builds the workflow based on:
        - WhatsApp API config (url, key)
        - Agent prompt + WhatsApp system prompt
        - Agent temperature
        - Feature toggles (voice, image, document)
        - Linked tools (api_call, webhook types)
        - Memory window size
        """
        agent = wa_agent.agent
        api_url = wa_agent.whatsapp_api_url.rstrip('/')
        api_key = wa_agent.whatsapp_api_key
        system_prompt = wa_agent.effective_prompt
        temperature = agent.temperature if agent else 0.5
        memory_window = wa_agent.memory_window or 10

        # Build nodes
        nodes = []
        connections = {}

        # --- 1. Webhook Trigger ---
        nodes.append(self._node_webhook(webhook_path))

        # --- 2. Store Data ---
        nodes.append(self._node_store_data())
        connections['Webhook Trigger'] = {'main': [[{'node': 'Store Data', 'type': 'main', 'index': 0}]]}

        # --- 3. Router (message type switch) ---
        router_outputs = []
        nodes.append(self._node_router(wa_agent))
        connections['Store Data'] = {'main': [[{'node': 'Router', 'type': 'main', 'index': 0}]]}

        # Router output index tracking
        router_output_idx = 0

        # --- 4a. Text Path (always enabled) ---
        nodes.append(self._node_text_data())
        router_outputs.append([{'node': 'Text Data', 'type': 'main', 'index': 0}])
        connections['Text Data'] = {'main': [[{'node': 'AI Agent', 'type': 'main', 'index': 0}]]}
        router_output_idx += 1

        # --- 4b. Audio/Voice Path (always enabled — we accept voice, just control response) ---
        nodes.extend([
            self._node_download_audio(api_url, api_key),
            self._node_add_phone('Add Phone Audio', 'voice'),
            self._node_transcribe(),
            self._node_audio_data()
        ])
        router_outputs.append([{'node': 'Download Audio', 'type': 'main', 'index': 0}])
        connections['Download Audio'] = {'main': [[{'node': 'Add Phone Audio', 'type': 'main', 'index': 0}]]}
        connections['Add Phone Audio'] = {'main': [[{'node': 'Transcribe', 'type': 'main', 'index': 0}]]}
        connections['Transcribe'] = {'main': [[{'node': 'Audio Data', 'type': 'main', 'index': 0}]]}
        connections['Audio Data'] = {'main': [[{'node': 'AI Agent', 'type': 'main', 'index': 0}]]}
        router_output_idx += 1

        # --- 4c. Image Path (if enabled) ---
        if wa_agent.enable_image_analysis:
            nodes.extend([
                self._node_get_image_url(api_url, api_key),
                self._node_download_image(),
                self._node_add_phone('Add Phone Image', 'image'),
                self._node_analyze_image(),
                self._node_image_data()
            ])
            router_outputs.append([{'node': 'Get Image URL', 'type': 'main', 'index': 0}])
            connections['Get Image URL'] = {'main': [[{'node': 'Download Image', 'type': 'main', 'index': 0}]]}
            connections['Download Image'] = {'main': [[{'node': 'Add Phone Image', 'type': 'main', 'index': 0}]]}
            connections['Add Phone Image'] = {'main': [[{'node': 'Analyze Image', 'type': 'main', 'index': 0}]]}
            connections['Analyze Image'] = {'main': [[{'node': 'Image Data', 'type': 'main', 'index': 0}]]}
            connections['Image Data'] = {'main': [[{'node': 'AI Agent', 'type': 'main', 'index': 0}]]}
            router_output_idx += 1

        # --- 4d. Document Path (if enabled) ---
        if wa_agent.enable_document_analysis:
            nodes.extend([
                self._node_get_doc_url(api_url, api_key),
                self._node_download_doc(),
                self._node_add_phone('Add Phone Doc', 'document'),
                self._node_extract_pdf(),
                self._node_pdf_data()
            ])
            router_outputs.append([{'node': 'Get Doc URL', 'type': 'main', 'index': 0}])
            connections['Get Doc URL'] = {'main': [[{'node': 'Download Doc', 'type': 'main', 'index': 0}]]}
            connections['Download Doc'] = {'main': [[{'node': 'Add Phone Doc', 'type': 'main', 'index': 0}]]}
            connections['Add Phone Doc'] = {'main': [[{'node': 'Extract PDF', 'type': 'main', 'index': 0}]]}
            connections['Extract PDF'] = {'main': [[{'node': 'PDF Data', 'type': 'main', 'index': 0}]]}
            connections['PDF Data'] = {'main': [[{'node': 'AI Agent', 'type': 'main', 'index': 0}]]}
            router_output_idx += 1

        # Set router connections
        connections['Router'] = {'main': router_outputs}

        # --- 5. AI Agent + Chat Model + Memory ---
        nodes.append(self._node_ai_agent(system_prompt))
        nodes.append(self._node_chat_model(temperature))
        nodes.append(self._node_memory(memory_window))

        connections['Chat Model'] = {'ai_languageModel': [[{'node': 'AI Agent', 'type': 'ai_languageModel', 'index': 0}]]}
        connections['Memory'] = {'ai_memory': [[{'node': 'AI Agent', 'type': 'ai_memory', 'index': 0}]]}

        # --- 6. Tools (from Agent's linked tools) ---
        tool_nodes = self._generate_tool_nodes(agent)
        nodes.extend(tool_nodes)
        # Connect each tool TO AI Agent (tools are sources, AI Agent is target)
        for tool_node in tool_nodes:
            connections[tool_node['name']] = {
                'ai_tool': [[{'node': 'AI Agent', 'type': 'ai_tool', 'index': 0}]]
            }

        # --- 7. Response Routing ---
        if wa_agent.enable_voice_response:
            # Check if input was voice → respond with voice, else text
            nodes.append(self._node_is_audio_check())
            nodes.append(self._node_tts())
            nodes.append(self._node_send_audio(wa_agent))
            nodes.append(self._node_send_text(wa_agent))

            # Preserve existing 'main' connections if they exist (for tools)
            if 'AI Agent' not in connections:
                connections['AI Agent'] = {}
            connections['AI Agent']['main'] = [[{'node': 'Is Audio?', 'type': 'main', 'index': 0}]]
            connections['Is Audio?'] = {'main': [
                [{'node': 'TTS', 'type': 'main', 'index': 0}],
                [{'node': 'Send Text', 'type': 'main', 'index': 0}]
            ]}
            connections['TTS'] = {'main': [[{'node': 'Send Audio', 'type': 'main', 'index': 0}]]}
        else:
            # Always respond with text
            nodes.append(self._node_send_text(wa_agent))
            # Preserve existing 'main' connections if they exist (for tools)
            if 'AI Agent' not in connections:
                connections['AI Agent'] = {}
            connections['AI Agent']['main'] = [[{'node': 'Send Text', 'type': 'main', 'index': 0}]]

        workflow_json = {
            'name': f"WhatsApp Agent: {wa_agent.name}",
            'nodes': nodes,
            'connections': connections,
            'settings': {
                'executionOrder': 'v1'
            }
        }

        return workflow_json

    # =========================================================================
    # Node Builders
    # =========================================================================

    def _node_webhook(self, webhook_path: str) -> dict:
        return {
            'parameters': {
                'httpMethod': 'POST',
                'path': webhook_path,
                'responseMode': 'lastNode',
                'options': {}
            },
            'name': 'Webhook Trigger',
            'type': 'n8n-nodes-base.webhook',
            'typeVersion': 2,
            'position': [-640, 160],
            'id': str(uuid.uuid4()),
            'webhookId': webhook_path
        }

    def _node_store_data(self) -> dict:
        return {
            'parameters': {
                'assignments': {
                    'assignments': [
                        {'id': 'phone', 'name': 'user_phone', 'value': '={{ $json.body.messages[0].from }}', 'type': 'string'},
                        {'id': 'type', 'name': 'msg_type', 'value': '={{ $json.body.messages[0].type }}', 'type': 'string'},
                        {'id': 'msg', 'name': 'message', 'value': '={{ $json.body.messages[0] }}', 'type': 'object'}
                    ]
                },
                'options': {}
            },
            'name': 'Store Data',
            'type': 'n8n-nodes-base.set',
            'typeVersion': 3.4,
            'position': [-432, 160],
            'id': str(uuid.uuid4())
        }

    def _node_router(self, wa_agent) -> dict:
        """Build message type router with dynamic outputs based on enabled features"""
        values = [
            # Text always
            {
                'conditions': {
                    'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict', 'version': 1},
                    'conditions': [{'id': 'text-cond', 'leftValue': '={{ $json.msg_type }}', 'rightValue': 'text',
                                    'operator': {'type': 'string', 'operation': 'equals', 'singleValue': True}}],
                    'combinator': 'and'
                },
                'renameOutput': True, 'outputKey': 'text'
            },
            # Voice always
            {
                'conditions': {
                    'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict', 'version': 1},
                    'conditions': [{'id': 'audio-cond', 'leftValue': '={{ $json.msg_type }}', 'rightValue': 'voice',
                                    'operator': {'type': 'string', 'operation': 'equals', 'singleValue': True}}],
                    'combinator': 'and'
                },
                'renameOutput': True, 'outputKey': 'audio'
            },
        ]

        if wa_agent.enable_image_analysis:
            values.append({
                'conditions': {
                    'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict', 'version': 1},
                    'conditions': [{'id': 'image-cond', 'leftValue': '={{ $json.msg_type }}', 'rightValue': 'image',
                                    'operator': {'type': 'string', 'operation': 'equals', 'singleValue': True}}],
                    'combinator': 'and'
                },
                'renameOutput': True, 'outputKey': 'image'
            })

        if wa_agent.enable_document_analysis:
            values.append({
                'conditions': {
                    'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict', 'version': 1},
                    'conditions': [{'id': 'doc-cond', 'leftValue': '={{ $json.msg_type }}', 'rightValue': 'document',
                                    'operator': {'type': 'string', 'operation': 'equals', 'singleValue': True}}],
                    'combinator': 'and'
                },
                'renameOutput': True, 'outputKey': 'document'
            })

        return {
            'parameters': {
                'rules': {'values': values},
                'options': {}
            },
            'name': 'Router',
            'type': 'n8n-nodes-base.switch',
            'typeVersion': 3.1,
            'position': [-240, 160],
            'id': str(uuid.uuid4())
        }

    def _node_text_data(self) -> dict:
        return {
            'parameters': {
                'assignments': {
                    'assignments': [
                        {'id': 'txt', 'name': 'text', 'value': '={{ $json.message.text.body }}', 'type': 'string'},
                        {'id': 'from', 'name': 'from', 'value': '={{ $json.user_phone }}', 'type': 'string'},
                        {'id': 'type', 'name': 'input_type', 'value': 'text', 'type': 'string'}
                    ]
                },
                'options': {}
            },
            'name': 'Text Data',
            'type': 'n8n-nodes-base.set',
            'typeVersion': 3.4,
            'position': [0, 0],
            'id': str(uuid.uuid4())
        }

    def _node_download_audio(self, api_url: str, api_key: str) -> dict:
        return {
            'parameters': {
                'url': '={{ $json.message.voice.link }}',
                'options': {
                    'response': {'response': {'responseFormat': 'file'}}
                }
            },
            'name': 'Download Audio',
            'type': 'n8n-nodes-base.httpRequest',
            'typeVersion': 4.2,
            'position': [0, 144],
            'id': str(uuid.uuid4())
        }

    def _node_add_phone(self, name: str, media_type: str) -> dict:
        return {
            'parameters': {
                'assignments': {
                    'assignments': [
                        {'id': f'phone-{media_type}', 'name': 'user_phone',
                         'value': "={{ $('Store Data').item.json.user_phone }}", 'type': 'string'}
                    ]
                },
                'includeOtherFields': True,
                'options': {}
            },
            'name': name,
            'type': 'n8n-nodes-base.set',
            'typeVersion': 3.4,
            'position': [200, 144 if media_type == 'voice' else (272 if media_type == 'image' else 416)],
            'id': str(uuid.uuid4())
        }

    def _node_transcribe(self) -> dict:
        return {
            'parameters': {
                'resource': 'audio',
                'operation': 'transcribe',
                'options': {}
            },
            'name': 'Transcribe',
            'type': '@n8n/n8n-nodes-langchain.openAi',
            'typeVersion': 1.8,
            'position': [400, 144],
            'id': str(uuid.uuid4()),
            'credentials': {
                'openAiApi': {'id': self.openai_cred_id, 'name': self.openai_cred_name}
            }
        }

    def _node_audio_data(self) -> dict:
        return {
            'parameters': {
                'assignments': {
                    'assignments': [
                        {'id': 'txt', 'name': 'text', 'value': '={{ $json.text }}', 'type': 'string'},
                        {'id': 'from', 'name': 'from', 'value': '={{ $json.user_phone }}', 'type': 'string'},
                        {'id': 'type', 'name': 'input_type', 'value': 'audio', 'type': 'string'}
                    ]
                },
                'options': {}
            },
            'name': 'Audio Data',
            'type': 'n8n-nodes-base.set',
            'typeVersion': 3.4,
            'position': [600, 144],
            'id': str(uuid.uuid4())
        }

    def _node_get_image_url(self, api_url: str, api_key: str) -> dict:
        return {
            'parameters': {
                'url': f'={api_url}/media/{{{{ $json.message.image.id }}}}',
                'sendHeaders': True,
                'headerParameters': {
                    'parameters': [{'name': 'Authorization', 'value': f'Bearer {api_key}'}]
                },
                'options': {}
            },
            'name': 'Get Image URL',
            'type': 'n8n-nodes-base.httpRequest',
            'typeVersion': 4.2,
            'position': [0, 272],
            'id': str(uuid.uuid4())
        }

    def _node_download_image(self) -> dict:
        return {
            'parameters': {
                'url': '={{ $json.media[0].url }}',
                'options': {
                    'response': {'response': {'responseFormat': 'file'}}
                }
            },
            'name': 'Download Image',
            'type': 'n8n-nodes-base.httpRequest',
            'typeVersion': 4.2,
            'position': [200, 272],
            'id': str(uuid.uuid4())
        }

    def _node_analyze_image(self) -> dict:
        return {
            'parameters': {
                'resource': 'image',
                'operation': 'analyze',
                'modelId': {'__rl': True, 'mode': 'list', 'value': 'gpt-4.1'},
                'text': 'Describe this image in detail.',
                'inputType': 'base64',
                'options': {}
            },
            'name': 'Analyze Image',
            'type': '@n8n/n8n-nodes-langchain.openAi',
            'typeVersion': 1.8,
            'position': [600, 272],
            'id': str(uuid.uuid4()),
            'credentials': {
                'openAiApi': {'id': self.openai_cred_id, 'name': self.openai_cred_name}
            }
        }

    def _node_image_data(self) -> dict:
        return {
            'parameters': {
                'assignments': {
                    'assignments': [
                        {'id': 'img-txt', 'name': 'text', 'value': '={{ $json.response }}', 'type': 'string'},
                        {'id': 'img-from', 'name': 'from', 'value': '={{ $json.user_phone }}', 'type': 'string'},
                        {'id': 'img-type', 'name': 'input_type', 'value': 'image', 'type': 'string'}
                    ]
                },
                'options': {}
            },
            'name': 'Image Data',
            'type': 'n8n-nodes-base.set',
            'typeVersion': 3.4,
            'position': [800, 272],
            'id': str(uuid.uuid4())
        }

    def _node_get_doc_url(self, api_url: str, api_key: str) -> dict:
        return {
            'parameters': {
                'url': f'={api_url}/media/{{{{ $json.message.document.id }}}}',
                'sendHeaders': True,
                'headerParameters': {
                    'parameters': [{'name': 'Authorization', 'value': f'Bearer {api_key}'}]
                },
                'options': {}
            },
            'name': 'Get Doc URL',
            'type': 'n8n-nodes-base.httpRequest',
            'typeVersion': 4.2,
            'position': [0, 416],
            'id': str(uuid.uuid4())
        }

    def _node_download_doc(self) -> dict:
        return {
            'parameters': {
                'url': '={{ $json.media[0].url }}',
                'options': {
                    'response': {'response': {'responseFormat': 'file'}}
                }
            },
            'name': 'Download Doc',
            'type': 'n8n-nodes-base.httpRequest',
            'typeVersion': 4.2,
            'position': [200, 416],
            'id': str(uuid.uuid4())
        }

    def _node_extract_pdf(self) -> dict:
        return {
            'parameters': {
                'operation': 'pdf',
                'options': {}
            },
            'name': 'Extract PDF',
            'type': 'n8n-nodes-base.extractFromFile',
            'typeVersion': 1,
            'position': [600, 416],
            'id': str(uuid.uuid4())
        }

    def _node_pdf_data(self) -> dict:
        return {
            'parameters': {
                'assignments': {
                    'assignments': [
                        {'id': 'pdf-txt', 'name': 'text', 'value': '={{ $json.data }}', 'type': 'string'},
                        {'id': 'pdf-from', 'name': 'from', 'value': '={{ $json.user_phone }}', 'type': 'string'},
                        {'id': 'pdf-type', 'name': 'input_type', 'value': 'document', 'type': 'string'}
                    ]
                },
                'options': {}
            },
            'name': 'PDF Data',
            'type': 'n8n-nodes-base.set',
            'typeVersion': 3.4,
            'position': [800, 416],
            'id': str(uuid.uuid4())
        }

    def _node_ai_agent(self, system_prompt: str) -> dict:
        return {
            'parameters': {
                'promptType': 'define',
                'text': '={{ $json.text }}',
                'tools': [],  # Tools will be populated via connections
                'options': {
                    'systemMessage': system_prompt
                }
            },
            'name': 'AI Agent',
            'type': '@n8n/n8n-nodes-langchain.agent',
            'typeVersion': 1.8,
            'position': [1040, 192],
            'id': str(uuid.uuid4())
        }

    def _node_chat_model(self, temperature: float) -> dict:
        return {
            'parameters': {
                'model': {
                    '__rl': True,
                    'value': 'gpt-4.1',
                    'mode': 'list',
                    'cachedResultName': 'gpt-4.1'
                },
                'options': {
                    'maxTokens': 500,
                    'temperature': temperature
                }
            },
            'name': 'Chat Model',
            'type': '@n8n/n8n-nodes-langchain.lmChatOpenAi',
            'typeVersion': 1.2,
            'position': [1040, 384],
            'id': str(uuid.uuid4()),
            'credentials': {
                'openAiApi': {'id': self.openai_cred_id, 'name': self.openai_cred_name}
            }
        }

    def _node_memory(self, window_size: int) -> dict:
        return {
            'parameters': {
                'sessionIdType': 'customKey',
                'sessionKey': '={{ $json.from }}',
                'contextWindowLength': window_size
            },
            'name': 'Memory',
            'type': '@n8n/n8n-nodes-langchain.memoryBufferWindow',
            'typeVersion': 1.3,
            'position': [1104, 560],
            'id': str(uuid.uuid4())
        }

    def _node_is_audio_check(self) -> dict:
        return {
            'parameters': {
                'conditions': {
                    'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict', 'version': 2},
                    'conditions': [{
                        'id': 'check-audio',
                        'leftValue': '={{ $node["Store Data"].json["msg_type"] }}',
                        'rightValue': 'voice',
                        'operator': {'type': 'string', 'operation': 'equals', 'singleValue': True}
                    }],
                    'combinator': 'and'
                },
                'options': {}
            },
            'name': 'Is Audio?',
            'type': 'n8n-nodes-base.if',
            'typeVersion': 2.2,
            'position': [1312, 208],
            'id': str(uuid.uuid4())
        }

    def _node_tts(self) -> dict:
        return {
            'parameters': {
                'resource': 'audio',
                'model': 'tts-1-hd',
                'input': '={{$json.output}}',
                'options': {}
            },
            'name': 'TTS',
            'type': '@n8n/n8n-nodes-langchain.openAi',
            'typeVersion': 1.8,
            'position': [1520, 96],
            'id': str(uuid.uuid4()),
            'credentials': {
                'openAiApi': {'id': self.openai_cred_id, 'name': self.openai_cred_name}
            }
        }

    def _get_send_text_url(self, wa_agent) -> str:
        """Get the send-text endpoint URL based on provider"""
        provider = getattr(wa_agent, 'whatsapp_provider', 'whapi') or 'whapi'
        api_url = wa_agent.whatsapp_api_url.rstrip('/')

        if provider == 'custom' and wa_agent.send_text_endpoint:
            return wa_agent.send_text_endpoint
        elif provider == 'meta':
            return f'{api_url}/messages'
        elif provider == 'unifonic':
            return f'{api_url}/messages'
        else:  # whapi (default)
            return f'{api_url}/messages/text'

    def _get_send_voice_url(self, wa_agent) -> str:
        """Get the send-voice endpoint URL based on provider"""
        provider = getattr(wa_agent, 'whatsapp_provider', 'whapi') or 'whapi'
        api_url = wa_agent.whatsapp_api_url.rstrip('/')

        if provider == 'custom' and wa_agent.send_voice_endpoint:
            return wa_agent.send_voice_endpoint
        elif provider == 'meta':
            return f'{api_url}/messages'
        elif provider == 'unifonic':
            return f'{api_url}/messages'
        else:  # whapi (default)
            return f'{api_url}/messages/voice'

    def _get_send_text_body(self, wa_agent) -> dict:
        """Get the request body config for sending text based on provider"""
        provider = getattr(wa_agent, 'whatsapp_provider', 'whapi') or 'whapi'

        if provider == 'meta':
            return {
                'sendBody': True,
                'specifyBody': 'json',
                'jsonBody': '={\n  "messaging_product": "whatsapp",\n  "to": "{{ $(\'Store Data\').item.json.user_phone }}",\n  "type": "text",\n  "text": {\n    "body": "{{ $json.output }}"\n  }\n}'
            }
        else:  # whapi, unifonic, custom — Whapi-style body
            return {
                'sendBody': True,
                'bodyParameters': {
                    'parameters': [
                        {'name': '=to', 'value': "={{ $('Store Data').item.json.user_phone }}"},
                        {'name': 'body', 'value': '={{ $json.output }}'}
                    ]
                }
            }

    def _get_send_audio_body(self, wa_agent) -> dict:
        """Get the request body config for sending audio based on provider"""
        provider = getattr(wa_agent, 'whatsapp_provider', 'whapi') or 'whapi'

        if provider == 'meta':
            return {
                'sendBody': True,
                'specifyBody': 'json',
                'jsonBody': '={\n  "messaging_product": "whatsapp",\n  "to": "{{ $(\'Store Data\').item.json.user_phone }}",\n  "type": "audio",\n  "audio": {\n    "link": "{{$node[\\"TTS\\"].binary.data}}"\n  }\n}'
            }
        else:  # whapi, unifonic, custom
            return {
                'sendBody': True,
                'specifyBody': 'json',
                'jsonBody': '={\n  "to": "{{ $(\'Store Data\').item.json.user_phone }}",\n  "media": "{{$node[\\"TTS\\"].binary.data}}"\n}'
            }

    def _node_send_audio(self, wa_agent) -> dict:
        api_key = wa_agent.whatsapp_api_key
        url = self._get_send_voice_url(wa_agent)
        body_config = self._get_send_audio_body(wa_agent)

        params = {
            'method': 'POST',
            'url': url,
            'sendHeaders': True,
            'headerParameters': {
                'parameters': [
                    {'name': 'Authorization', 'value': f'Bearer {api_key}'},
                    {'name': 'Content-Type', 'value': 'application/json'}
                ]
            },
            'options': {}
        }
        params.update(body_config)

        return {
            'parameters': params,
            'name': 'Send Audio',
            'type': 'n8n-nodes-base.httpRequest',
            'typeVersion': 4.2,
            'position': [1760, 96],
            'id': str(uuid.uuid4())
        }

    def _node_send_text(self, wa_agent) -> dict:
        api_key = wa_agent.whatsapp_api_key
        url = self._get_send_text_url(wa_agent)
        body_config = self._get_send_text_body(wa_agent)

        params = {
            'method': 'POST',
            'url': url,
            'sendHeaders': True,
            'headerParameters': {
                'parameters': [
                    {'name': 'Authorization', 'value': f'Bearer {api_key}'},
                    {'name': 'Content-Type', 'value': 'application/json'}
                ]
            },
            'options': {}
        }
        params.update(body_config)

        return {
            'parameters': params,
            'name': 'Send Text',
            'type': 'n8n-nodes-base.httpRequest',
            'typeVersion': 4.2,
            'position': [1520, 304],
            'id': str(uuid.uuid4())
        }

    # =========================================================================
    # Tool Node Generation
    # =========================================================================

    def _generate_tool_nodes(self, agent) -> list:
        """
        Generate n8n tool nodes from agent's linked tools.
        Only supports api_call and webhook types for v1.
        """
        if not agent:
            return []

        tool_nodes = []
        x_pos = 900  # Starting x position for tool nodes
        y_pos = 600  # y position below the AI Agent

        try:
            # Import here to avoid circular imports
            from models import AgentTool, Tool
            agent_tools = AgentTool.query.filter_by(agent_id=agent.id).all()

            for i, at in enumerate(agent_tools):
                tool = Tool.query.get(at.tool_id)
                if not tool or not tool.is_active:
                    continue

                if tool.tool_type in ('api_call', 'webhook'):
                    try:
                        config = json.loads(tool.config) if isinstance(tool.config, str) else tool.config
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"Skipping tool {tool.name}: invalid config JSON")
                        continue

                    tool_node = self._build_http_tool_node(
                        name=tool.name,
                        description=tool.description,
                        config=config,
                        position=[x_pos + (i * 200), y_pos]
                    )
                    tool_nodes.append(tool_node)
                else:
                    logger.info(f"Skipping tool {tool.name}: type '{tool.tool_type}' not supported for WhatsApp agents")

        except Exception as e:
            logger.error(f"Error generating tool nodes: {e}")

        return tool_nodes
        
    def _build_http_tool_node(self, name: str, description: str, config: dict, position: list) -> dict:
        import re

        url = config.get('url', '')
        method = config.get('method', 'GET').upper()
        headers = config.get('headers', {})
        params = config.get('parameters', {})

        # =========================================================
        # Build placeholders list from structured OR legacy format
        # =========================================================
        placeholders = []

        if params and isinstance(params, dict):
            for param_name, param_config in params.items():
                if isinstance(param_config, dict):
                    # Structured format: {"to": {"type": "string", "description": "...", "required": true}}
                    placeholders.append({
                        'name': param_name,
                        'description': param_config.get('description', param_name),
                        'type': param_config.get('type', 'string'),
                        'required': param_config.get('required', False)
                    })
                elif isinstance(param_config, str):
                    # Legacy template format: extract {{var}} from values
                    template_vars = re.findall(r'\{\{(\w+)\}\}', param_config)
                    for var in template_vars:
                        if not any(p['name'] == var for p in placeholders):
                            placeholders.append({
                                'name': var,
                                'description': f'Value for {var}',
                                'type': 'string',
                                'required': True
                            })
        else:
            # No parameters defined — scan all config values for {{templates}}
            for key, value in config.items():
                if isinstance(value, str):
                    template_vars = re.findall(r'\{\{(\w+)\}\}', value)
                    for var in template_vars:
                        if not any(p['name'] == var for p in placeholders):
                            placeholders.append({
                                'name': var,
                                'description': f'Value for {var}',
                                'type': 'string',
                                'required': True
                            })

        # =========================================================
        # Build the node parameters
        # =========================================================
        node_params = {
            'url': url,
            'method': method,
            'toolDescription': description,  # ✅ correct field for toolHttpRequest
            'options': {}
        }

        # ✅ Placeholders — this is how n8n toolHttpRequest exposes params to the AI
        if placeholders:
            node_params['placeholderDefinitions'] = {
                'values': [
                    {
                        'name': p['name'],
                        'description': p['description'],
                        'type': p['type']
                    }
                    for p in placeholders
                ]
            }

        # ✅ Body for POST/PUT — use {placeholder} syntax (single braces, n8n's format)
        if method in ('POST', 'PUT', 'PATCH') and placeholders:
            node_params['sendBody'] = True
            node_params['specifyBody'] = 'json'
            body_obj = {p['name']: f"{{{p['name']}}}" for p in placeholders}
            node_params['jsonBody'] = json.dumps(body_obj)
            # Result: {"to": "{to}", "body": "{body}"}

        # ✅ Query params for GET — embed {placeholder} directly in the URL
        elif method == 'GET' and placeholders:
            # Build query string with {placeholder} syntax directly in URL
            query_parts = [f"{p['name']}={{{p['name']}}}" for p in placeholders]
            query_string = '&'.join(query_parts)
            
            # Append to URL (handle existing query params)
            if '?' in url:
                node_params['url'] = f"{url}&{query_string}"
            else:
                node_params['url'] = f"{url}?{query_string}"

        # ✅ Headers
        if headers:
            node_params['sendHeaders'] = True
            node_params['headerParameters'] = {
                'parameters': [{'name': k, 'value': v} for k, v in headers.items()]
            }

        return {
            'parameters': node_params,
            'name': name,
            'type': '@n8n/n8n-nodes-langchain.toolHttpRequest',
            'typeVersion': 1.1,
            'position': position,
            'id': str(uuid.uuid4())
        }
# Singleton instance
n8n_service = N8nService()
