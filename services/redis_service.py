"""
Redis Service for Caching and Metrics
Handles agent configs, metrics, and shared state across processes
"""
import redis
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class RedisService:
    """
    Redis service for caching and metrics
    Works across multiple worker processes
    """

    def __init__(self, host='localhost', port=6379, db=0, password=None):
        """Initialize Redis connection with optional password authentication"""
        self.host = host
        self.port = port
        try:
            self.client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,  # Support password authentication
                decode_responses=True,  # Auto-decode bytes to strings
                socket_connect_timeout=1,  # Fast timeout - don't block startup
                socket_timeout=1,  # Fast timeout for operations
                socket_keepalive=True,
                max_connections=200, 
                health_check_interval=30
            )
            # Test connection (with quick timeout)
            self.client.ping()
            logger.info(f"✅ Redis connected: {host}:{port}")
        except Exception as e:
            # Catch ALL exceptions - don't let Redis failure crash the app
            logger.warning(f"⚠️ Redis unavailable ({host}:{port}): {e}")
            logger.warning(f"⚠️ App will continue without caching. Cache operations will be skipped.")
            self.client = None

    def is_connected(self) -> bool:
        """Check if Redis is connected (with lazy reconnection attempt)"""
        if not self.client:
            # Try to reconnect if we haven't tried recently
            try:
                self.client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    decode_responses=True,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                    socket_keepalive=True
                )
                self.client.ping()
                logger.info(f"✅ Redis reconnected: {self.host}:{self.port}")
                return True
            except:
                self.client = None
                return False

        try:
            self.client.ping()
            return True
        except:
            self.client = None
            return False

    # ==========================================
    # AGENT CONFIGURATION CACHING
    # ==========================================

    def cache_agent_config(self, agent_id: int, config: Dict[str, Any], ttl: int = 3600):
        """
        Cache agent configuration

        Args:
            agent_id: Agent ID
            config: Agent configuration dict
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        if not self.is_connected():
            return False

        try:
            key = f"agent:config:{agent_id}"
            self.client.setex(
                key,
                ttl,
                json.dumps(config)
            )
            logger.info(f"📦 Cached agent {agent_id} config (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to cache agent config: {e}")
            return False

    def get_agent_config(self, agent_id: int) -> Optional[Dict[str, Any]]:
        """
        Get cached agent configuration

        Returns:
            Agent config dict or None if not cached
        """
        if not self.is_connected():
            return None

        try:
            key = f"agent:config:{agent_id}"
            data = self.client.get(key)
            if data:
                logger.debug(f"✅ Cache HIT: agent {agent_id}")
                return json.loads(data)
            else:
                logger.debug(f"❌ Cache MISS: agent {agent_id}")
                return None
        except Exception as e:
            logger.error(f"❌ Failed to get agent config: {e}")
            return None

    def invalidate_agent_config(self, agent_id: int):
        """Invalidate cached agent configuration"""
        if not self.is_connected():
            return

        try:
            key = f"agent:config:{agent_id}"
            self.client.delete(key)
            logger.info(f"🗑️ Invalidated cache for agent {agent_id}")
        except Exception as e:
            logger.error(f"❌ Failed to invalidate cache: {e}")

    # ==========================================
    # METRICS (Multiprocess-safe!)
    # ==========================================

    def increment_metric(self, metric_name: str, agent_id: int, value: float = 1):
        """
        Increment a counter metric
        Works across all worker processes!

        Args:
            metric_name: Metric name (e.g., 'calls_total', 'cost_cents')
            agent_id: Agent ID
            value: Value to increment by
        """
        if not self.is_connected():
            return

        try:
            # Daily key
            today = datetime.now().strftime('%Y-%m-%d')
            key = f"metrics:{today}:{metric_name}:agent:{agent_id}"
            self.client.incrbyfloat(key, value)

            # Set expiry (keep for 30 days)
            self.client.expire(key, 30 * 24 * 3600)
        except Exception as e:
            logger.error(f"❌ Failed to increment metric: {e}")

    def get_metric(self, metric_name: str, agent_id: int, date: str = None) -> float:
        """
        Get metric value

        Args:
            metric_name: Metric name
            agent_id: Agent ID
            date: Date string (YYYY-MM-DD), defaults to today

        Returns:
            Metric value
        """
        if not self.is_connected():
            return 0

        try:
            if not date:
                date = datetime.now().strftime('%Y-%m-%d')

            key = f"metrics:{date}:{metric_name}:agent:{agent_id}"
            value = self.client.get(key)
            return float(value) if value else 0
        except Exception as e:
            logger.error(f"❌ Failed to get metric: {e}")
            return 0

    def set_gauge(self, metric_name: str, agent_id: int, value: float):
        """
        Set a gauge metric (for current values like active_calls)

        Args:
            metric_name: Metric name (e.g., 'active_calls')
            agent_id: Agent ID
            value: Current value
        """
        if not self.is_connected():
            return

        try:
            key = f"metrics:gauge:{metric_name}:agent:{agent_id}"
            self.client.set(key, value)
        except Exception as e:
            logger.error(f"❌ Failed to set gauge: {e}")

    def get_gauge(self, metric_name: str, agent_id: int) -> float:
        """Get current gauge value"""
        if not self.is_connected():
            return 0

        try:
            key = f"metrics:gauge:{metric_name}:agent:{agent_id}"
            value = self.client.get(key)
            return float(value) if value else 0
        except Exception as e:
            logger.error(f"❌ Failed to get gauge: {e}")
            return 0

    def track_histogram(self, metric_name: str, agent_id: int, value: float):
        """
        Track histogram values (for durations, sizes, etc.)

        Args:
            metric_name: Metric name (e.g., 'call_duration')
            agent_id: Agent ID
            value: Observed value
        """
        if not self.is_connected():
            return

        try:
            today = datetime.now().strftime('%Y-%m-%d')
            key = f"metrics:{today}:histogram:{metric_name}:agent:{agent_id}"

            # Store last 1000 values
            self.client.lpush(key, value)
            self.client.ltrim(key, 0, 999)
            self.client.expire(key, 30 * 24 * 3600)
        except Exception as e:
            logger.error(f"❌ Failed to track histogram: {e}")

    def get_histogram_stats(self, metric_name: str, agent_id: int, date: str = None) -> Dict[str, float]:
        """
        Get histogram statistics

        Returns:
            dict with min, max, avg, p50, p95, p99
        """
        if not self.is_connected():
            return {}

        try:
            if not date:
                date = datetime.now().strftime('%Y-%m-%d')

            key = f"metrics:{date}:histogram:{metric_name}:agent:{agent_id}"
            values = [float(v) for v in self.client.lrange(key, 0, -1)]

            if not values:
                return {}

            values.sort()
            count = len(values)

            return {
                'count': count,
                'min': values[0],
                'max': values[-1],
                'avg': sum(values) / count,
                'p50': values[int(count * 0.50)],
                'p95': values[int(count * 0.95)],
                'p99': values[int(count * 0.99)]
            }
        except Exception as e:
            logger.error(f"❌ Failed to get histogram stats: {e}")
            return {}

    # ==========================================
    # USER TRUNK CACHING
    # ==========================================
    # WHY: Every outbound call queries user.outbound_trunk_id from Google Cloud PostgreSQL
    # IMPACT: 5-20ms per call (network latency to Google Cloud from Hetzner)
    # BENEFIT: 30x speedup (20ms → 0.5ms), 95% reduction in DB queries
    # INVALIDATION: When user changes their trunk configuration
    # ==========================================

    def cache_user_trunk(self, user_id: int, trunk_id: str, ttl: int = 3600):
        """
        Cache user's SIP trunk ID for outbound calls

        WHY THIS MATTERS:
        - Campaign worker needs trunk_id for every outbound call
        - 100 calls/min = 100 DB queries to Google Cloud PostgreSQL
        - Each query: 5-20ms (network latency from Hetzner to Google Cloud)
        - With cache: < 1ms (localhost Redis on Hetzner)

        PERFORMANCE IMPACT:
        - Without cache: 100 calls × 20ms = 2,000ms/min = database bottleneck
        - With cache: 5 calls × 20ms = 100ms/min (95% hit rate)
        - Speedup: 20x faster! Database queries reduced by 95%

        Args:
            user_id: User ID
            trunk_id: SIP trunk ID for outbound calls
            ttl: Time-to-live in seconds (default: 1 hour)

        Example:
            >>> redis_service.cache_user_trunk(42, 'trunk_abc123', ttl=3600)
            📦 Cached trunk for user 42 (TTL: 3600s)
        """
        if not self.is_connected():
            return False

        try:
            key = f"user:trunk:{user_id}"
            self.client.setex(key, ttl, trunk_id)
            logger.info(f"📦 Cached trunk for user {user_id} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to cache user trunk: {e}")
            return False

    def get_user_trunk(self, user_id: int) -> Optional[str]:
        """
        Get cached user trunk ID (or None if not cached)

        USAGE PATTERN:
        ```python
        # Try cache first (fast!)
        trunk_id = redis_service.get_user_trunk(user_id)

        if not trunk_id:
            # Cache miss - query database (slow)
            user = User.query.get(user_id)
            trunk_id = user.outbound_trunk_id or os.getenv('SIP_OUTBOUND_TRUNK_ID')

            # Cache it for next time
            redis_service.cache_user_trunk(user_id, trunk_id, ttl=3600)

        # Use trunk_id for outbound call
        ```

        Returns:
            Trunk ID string or None if not cached

        Example:
            >>> trunk_id = redis_service.get_user_trunk(42)
            ✅ Cache HIT: user 42 trunk
            >>> print(trunk_id)
            'trunk_abc123'
        """
        if not self.is_connected():
            return None

        try:
            key = f"user:trunk:{user_id}"
            trunk_id = self.client.get(key)

            if trunk_id:
                logger.debug(f"✅ Cache HIT: user {user_id} trunk")
                return trunk_id
            else:
                logger.debug(f"❌ Cache MISS: user {user_id} trunk")
                return None
        except Exception as e:
            logger.error(f"❌ Failed to get user trunk: {e}")
            return None

    def invalidate_user_trunk(self, user_id: int):
        """
        Invalidate cached user trunk (call when user changes trunk configuration)

        WHEN TO CALL:
        - User updates trunk settings in admin panel
        - Admin assigns different trunk to user
        - Trunk configuration changes

        USAGE IN FLASK ROUTES:
        ```python
        @app.route('/admin/users/<int:user_id>/trunk', methods=['POST'])
        def update_user_trunk(user_id):
            user = User.query.get(user_id)
            user.outbound_trunk_id = request.form.get('trunk_id')
            db.session.commit()

            # ⚡ CRITICAL: Invalidate cache immediately!
            redis_service.invalidate_user_trunk(user_id)

            flash('Trunk updated!', 'success')
            return redirect('/admin/users')
        ```

        Example:
            >>> redis_service.invalidate_user_trunk(42)
            🗑️ Invalidated trunk cache for user 42
        """
        if not self.is_connected():
            return

        try:
            key = f"user:trunk:{user_id}"
            self.client.delete(key)
            logger.info(f"🗑️ Invalidated trunk cache for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Failed to invalidate trunk cache: {e}")

    # ==========================================
    # WORKFLOW CACHING
    # ==========================================
    # WHY: webhook_service.py queries workflow config for every webhook trigger
    # IMPACT: 10-20ms per call (database query to Google Cloud)
    # BENEFIT: 40x speedup (20ms → 0.5ms), 95% reduction in DB queries
    # INVALIDATION: When workflow is edited/disabled in admin panel
    # ==========================================

    def cache_workflow(self, workflow_id: int, workflow_config: Dict[str, Any], ttl: int = 1800):
        """
        Cache workflow configuration for webhook triggers

        WHY THIS MATTERS:
        - Every call triggers webhook after completion
        - webhook_service queries workflow config: URL, API key, is_active
        - 100 calls/min = 100 DB queries to Google Cloud PostgreSQL
        - Each query: 10-20ms (network + query time)
        - With cache: < 1ms (localhost Redis)

        PERFORMANCE IMPACT:
        - Without cache: 100 webhooks × 20ms = 2,000ms/min database load
        - With cache: 5 webhooks × 20ms = 100ms/min (95% hit rate)
        - Speedup: 40x faster! Database queries reduced by 95%

        WHAT GETS CACHED:
        ```python
        {
            'id': 123,
            'url': 'https://api.example.com/webhook',
            'api_key': 'sk_live_abc123',
            'is_active': True,
            'retry_count': 3,
            'timeout_seconds': 30
        }
        ```

        Args:
            workflow_id: Workflow ID
            workflow_config: Workflow configuration dict
            ttl: Time-to-live in seconds (default: 30 minutes)

        Note: Shorter TTL (30min vs 1hr) because webhooks change more frequently

        Example:
            >>> config = {
            ...     'id': 123,
            ...     'url': 'https://api.example.com/webhook',
            ...     'api_key': 'sk_live_abc123',
            ...     'is_active': True
            ... }
            >>> redis_service.cache_workflow(123, config, ttl=1800)
            📦 Cached workflow 123 config (TTL: 1800s)
        """
        if not self.is_connected():
            return False

        try:
            key = f"workflow:config:{workflow_id}"
            self.client.setex(key, ttl, json.dumps(workflow_config))
            logger.info(f"📦 Cached workflow {workflow_id} config (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to cache workflow: {e}")
            return False

    def get_workflow(self, workflow_id: int) -> Optional[Dict[str, Any]]:
        """
        Get cached workflow configuration (or None if not cached)

        USAGE PATTERN IN webhook_service.py:
        ```python
        # Try cache first (fast!)
        workflow_config = redis_service.get_workflow(workflow_id)

        if not workflow_config:
            # Cache miss - query database (slow)
            workflow = Workflow.query.get(workflow_id)

            if not workflow or not workflow.is_active:
                return None  # Don't cache inactive workflows

            workflow_config = {
                'id': workflow.id,
                'url': workflow.webhook_url,
                'api_key': workflow.api_key,
                'is_active': workflow.is_active
            }

            # Cache for 30 minutes
            redis_service.cache_workflow(workflow_id, workflow_config, ttl=1800)

        # Trigger webhook using cached config
        requests.post(
            workflow_config['url'],
            headers={'Authorization': f"Bearer {workflow_config['api_key']}"},
            json=webhook_data
        )
        ```

        Returns:
            Workflow config dict or None if not cached

        Example:
            >>> config = redis_service.get_workflow(123)
            ✅ Cache HIT: workflow 123
            >>> print(config['url'])
            'https://api.example.com/webhook'
        """
        if not self.is_connected():
            return None

        try:
            key = f"workflow:config:{workflow_id}"
            data = self.client.get(key)

            if data:
                logger.debug(f"✅ Cache HIT: workflow {workflow_id}")
                return json.loads(data)
            else:
                logger.debug(f"❌ Cache MISS: workflow {workflow_id}")
                return None
        except Exception as e:
            logger.error(f"❌ Failed to get workflow: {e}")
            return None

    def invalidate_workflow(self, workflow_id: int):
        """
        Invalidate cached workflow (call when workflow is edited or disabled)

        WHEN TO CALL:
        - Workflow URL changed
        - Workflow API key rotated
        - Workflow enabled/disabled
        - Workflow retry settings changed

        USAGE IN FLASK ROUTES:
        ```python
        @app.route('/admin/workflows/<int:workflow_id>/edit', methods=['POST'])
        def edit_workflow(workflow_id):
            workflow = Workflow.query.get(workflow_id)
            workflow.webhook_url = request.form.get('url')
            workflow.api_key = request.form.get('api_key')
            workflow.is_active = request.form.get('is_active') == 'true'
            db.session.commit()

            # ⚡ CRITICAL: Invalidate cache immediately!
            redis_service.invalidate_workflow(workflow_id)

            flash('Workflow updated!', 'success')
            return redirect('/admin/workflows')
        ```

        Example:
            >>> redis_service.invalidate_workflow(123)
            🗑️ Invalidated cache for workflow 123
        """
        if not self.is_connected():
            return

        try:
            key = f"workflow:config:{workflow_id}"
            self.client.delete(key)
            logger.info(f"🗑️ Invalidated cache for workflow {workflow_id}")
        except Exception as e:
            logger.error(f"❌ Failed to invalidate workflow cache: {e}")

    # ==========================================
    # CAMPAIGN METADATA CACHING
    # ==========================================
    # WHY: campaign_worker.py calls get_agent_config() 100+ times on startup
    # IMPACT: 100 × 20ms = 2,000ms startup delay before campaign begins
    # BENEFIT: Campaign starts 2 seconds faster, ready to dial immediately
    # INVALIDATION: When campaign or agent configuration changes
    # ==========================================

    def cache_campaign_metadata(self, campaign_id: int, metadata: Dict[str, Any], ttl: int = 1800):
        """
        Cache complete campaign metadata including agent config

        WHY THIS MATTERS:
        - campaign_worker.py starts up and needs to know:
          * Which agent to use
          * Agent's prompt, voice, greeting
          * How many concurrent calls to make
          * What phone numbers to dial
        - Currently: 100+ database queries to Google Cloud on startup
        - Each query: 10-20ms = 2,000ms total startup time
        - With cache: 1 query × 0.5ms = Campaign starts 2 seconds faster!

        PERFORMANCE IMPACT:
        - Without cache: Campaign startup = 2-3 seconds (users wait)
        - With cache: Campaign startup = 0.1 seconds (instant!)
        - Benefit: Calls start dialing 2-3 seconds earlier

        WHAT GETS CACHED:
        ```python
        {
            'campaign_id': 456,
            'campaign_name': 'NHC Ramadan Campaign',
            'agent_id': 50,
            'agent_config': {
                'id': 50,
                'name': 'naqi',
                'prompt': '...',
                'greeting': 'السلام عليكم',
                'voice_id': 'KjDucWgG5NYuMBznv52L',
                'voice_name': 'Hiba'
            },
            'concurrent_calls': 10,
            'call_window_start': '09:00',
            'call_window_end': '21:00',
            'total_contacts': 5000,
            'status': 'active'
        }
        ```

        Args:
            campaign_id: Campaign ID
            metadata: Complete campaign metadata dict
            ttl: Time-to-live in seconds (default: 30 minutes)

        Example:
            >>> metadata = {
            ...     'campaign_id': 456,
            ...     'agent_id': 50,
            ...     'agent_config': {...},
            ...     'concurrent_calls': 10
            ... }
            >>> redis_service.cache_campaign_metadata(456, metadata, ttl=1800)
            📦 Cached campaign 456 metadata (TTL: 1800s)
        """
        if not self.is_connected():
            return False

        try:
            key = f"campaign:metadata:{campaign_id}"
            self.client.setex(key, ttl, json.dumps(metadata))
            logger.info(f"📦 Cached campaign {campaign_id} metadata (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to cache campaign metadata: {e}")
            return False

    def get_campaign_metadata(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        """
        Get cached campaign metadata (or None if not cached)

        USAGE PATTERN IN campaign_worker.py:
        ```python
        def start_campaign(campaign_id: int):
            # Try cache first (instant!)
            metadata = redis_service.get_campaign_metadata(campaign_id)

            if not metadata:
                # Cache miss - load from database (slow)
                campaign = Campaign.query.get(campaign_id)
                agent = Agent.query.get(campaign.agent_id)

                metadata = {
                    'campaign_id': campaign.id,
                    'agent_id': agent.id,
                    'agent_config': {
                        'name': agent.name,
                        'prompt': agent.prompt,
                        'greeting': agent.greeting,
                        'voice_id': agent.voice_id
                    },
                    'concurrent_calls': campaign.concurrent_calls
                }

                # Cache for 30 minutes
                redis_service.cache_campaign_metadata(campaign_id, metadata, ttl=1800)

            # Campaign starts IMMEDIATELY with cached data!
            agent_config = metadata['agent_config']
            concurrent_calls = metadata['concurrent_calls']

            # Start dialing...
        ```

        PERFORMANCE BENEFIT:
        - First run: 2 seconds (loads from DB, caches)
        - Subsequent runs: 0.1 seconds (loads from Redis cache)
        - Campaign restarts: 20x faster!

        Returns:
            Campaign metadata dict or None if not cached

        Example:
            >>> metadata = redis_service.get_campaign_metadata(456)
            ✅ Cache HIT: campaign 456
            >>> print(metadata['agent_config']['name'])
            'naqi'
        """
        if not self.is_connected():
            return None

        try:
            key = f"campaign:metadata:{campaign_id}"
            data = self.client.get(key)

            if data:
                logger.debug(f"✅ Cache HIT: campaign {campaign_id}")
                return json.loads(data)
            else:
                logger.debug(f"❌ Cache MISS: campaign {campaign_id}")
                return None
        except Exception as e:
            logger.error(f"❌ Failed to get campaign metadata: {e}")
            return None

    def invalidate_campaign_metadata(self, campaign_id: int):
        """
        Invalidate cached campaign metadata

        WHEN TO CALL:
        - Campaign settings changed (concurrent calls, schedule, etc.)
        - Campaign's agent changed
        - Agent configuration updated (prompt, voice, greeting)

        IMPORTANT CASCADE INVALIDATION:
        If agent is edited, invalidate ALL campaigns using that agent:

        ```python
        @app.route('/admin/agents/<int:agent_id>/edit', methods=['POST'])
        def edit_agent(agent_id):
            agent = Agent.query.get(agent_id)
            agent.prompt = request.form.get('prompt')
            db.session.commit()

            # Invalidate agent cache
            redis_service.invalidate_agent_config(agent_id)

            # ⚡ ALSO invalidate all campaigns using this agent!
            campaigns = Campaign.query.filter_by(agent_id=agent_id).all()
            for campaign in campaigns:
                redis_service.invalidate_campaign_metadata(campaign.id)

            flash('Agent updated! All campaigns refreshed.', 'success')
        ```

        USAGE IN FLASK ROUTES:
        ```python
        @app.route('/admin/campaigns/<int:campaign_id>/edit', methods=['POST'])
        def edit_campaign(campaign_id):
            campaign = Campaign.query.get(campaign_id)
            campaign.concurrent_calls = int(request.form.get('concurrent_calls'))
            campaign.agent_id = int(request.form.get('agent_id'))
            db.session.commit()

            # ⚡ CRITICAL: Invalidate cache immediately!
            redis_service.invalidate_campaign_metadata(campaign_id)

            flash('Campaign updated!', 'success')
            return redirect('/admin/campaigns')
        ```

        Example:
            >>> redis_service.invalidate_campaign_metadata(456)
            🗑️ Invalidated cache for campaign 456
        """
        if not self.is_connected():
            return

        try:
            key = f"campaign:metadata:{campaign_id}"
            self.client.delete(key)
            logger.info(f"🗑️ Invalidated cache for campaign {campaign_id}")
        except Exception as e:
            logger.error(f"❌ Failed to invalidate campaign cache: {e}")

    # ==========================================
    # TOOL CACHING
    # ==========================================

    def cache_tools(self, agent_id: int, tools_config: list, ttl: int = 3600):
        """Cache tool configurations for an agent"""
        if not self.is_connected():
            return False

        try:
            key = f"agent:tools:{agent_id}"
            self.client.setex(key, ttl, json.dumps(tools_config))
            logger.info(f"📦 Cached {len(tools_config)} tools for agent {agent_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to cache tools: {e}")
            return False

    def get_tools(self, agent_id: int) -> Optional[list]:
        """Get cached tools for an agent"""
        if not self.is_connected():
            return None

        try:
            key = f"agent:tools:{agent_id}"
            data = self.client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"❌ Failed to get tools: {e}")
            return None

    # ==========================================
    # SESSION DATA
    # ==========================================

    def set_session_data(self, room_name: str, data: Dict[str, Any], ttl: int = 7200):
        """Store temporary session data (expires after 2 hours by default)"""
        if not self.is_connected():
            return

        try:
            key = f"session:{room_name}"
            self.client.setex(key, ttl, json.dumps(data))
        except Exception as e:
            logger.error(f"❌ Failed to set session data: {e}")

    def get_session_data(self, room_name: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        if not self.is_connected():
            return None

        try:
            key = f"session:{room_name}"
            data = self.client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"❌ Failed to get session data: {e}")
            return None

    # ==========================================
    # HELPER METHODS
    # ==========================================

    def flush_all(self):
        """⚠️ WARNING: Clears ALL Redis data!"""
        if not self.is_connected():
            return

        try:
            self.client.flushdb()
            logger.warning("🗑️ Redis database flushed!")
        except Exception as e:
            logger.error(f"❌ Failed to flush Redis: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get Redis server stats"""
        if not self.is_connected():
            return {}

        try:
            info = self.client.info()
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', '0'),
                'total_keys': self.client.dbsize(),
                'uptime_seconds': info.get('uptime_in_seconds', 0)
            }
        except Exception as e:
            logger.error(f"❌ Failed to get Redis stats: {e}")
            return {}


# ==========================================
# GLOBAL REDIS INSTANCE WITH ENVIRONMENT CONFIG
# ==========================================
# Reads Redis configuration from environment variables (.env file)
# REDIS_HOST: Redis server hostname (default: localhost)
# REDIS_PORT: Redis server port (default: 6379)
# REDIS_DB: Redis database number (default: 0)
# REDIS_PASSWORD: Redis password for authentication (default: None)
# ==========================================

import os

# Read Redis configuration from environment variables
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

# Initialize global Redis service with environment config
redis_service = RedisService(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD
)

logger.info(f"📦 Redis service initialized: {REDIS_HOST}:{REDIS_PORT} (db: {REDIS_DB}, auth: {'enabled' if REDIS_PASSWORD else 'disabled'})")
