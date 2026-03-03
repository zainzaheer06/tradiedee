"""
API Key Service
Handles generation, validation, and management of API keys for external integrations
"""
import secrets
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

# Saudi Arabia Timezone (UTC+3)
SAUDI_TZ = timezone(timedelta(hours=3))

logger = logging.getLogger(__name__)


class ApiKeyService:
    """
    Service for managing API keys

    Key Format: nvx_{32_random_chars}
    Storage: SHA-256 hash (never store raw key)
    """

    PREFIX = "nvx_"
    KEY_LENGTH = 32  # Characters after prefix

    def generate_key(self) -> Tuple[str, str, str]:
        """
        Generate a new API key

        Returns:
            Tuple of (raw_key, key_hash, key_prefix)
            - raw_key: Full key to show user ONCE (nvx_abc123...)
            - key_hash: SHA-256 hash to store in database
            - key_prefix: First 8 chars for display (nvx_abc1...)
        """
        # Generate random key
        random_part = secrets.token_hex(self.KEY_LENGTH // 2)  # 32 hex chars
        raw_key = f"{self.PREFIX}{random_part}"

        # Hash for storage
        key_hash = self._hash_key(raw_key)

        # Prefix for display
        key_prefix = raw_key[:12] + "..."

        logger.info(f"Generated new API key with prefix: {key_prefix}")

        return raw_key, key_hash, key_prefix

    def _hash_key(self, raw_key: str) -> str:
        """
        Hash an API key using SHA-256

        Args:
            raw_key: The raw API key string

        Returns:
            SHA-256 hex digest
        """
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def validate_key(self, raw_key: str) -> Optional['User']:
        """
        Validate an API key and return the associated user

        Args:
            raw_key: The raw API key from request header

        Returns:
            User object if valid, None if invalid
        """
        if not raw_key:
            logger.warning("API key validation failed: No key provided")
            return None

        # Check prefix
        if not raw_key.startswith(self.PREFIX):
            logger.warning(f"API key validation failed: Invalid prefix")
            return None

        # Hash and look up
        key_hash = self._hash_key(raw_key)

        # Import here to avoid circular imports
        from models import ApiKey, db

        api_key = ApiKey.query.filter_by(
            key_hash=key_hash,
            is_active=True
        ).first()

        if not api_key:
            logger.warning(f"API key validation failed: Key not found or inactive")
            return None

        # Update last used
        api_key.last_used_at = datetime.utcnow()
        api_key.total_calls += 1

        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"Error updating API key usage: {e}")
            db.session.rollback()

        logger.info(f"API key validated for user_id={api_key.user_id}")
        return api_key.user

    def create_key_for_user(self, user_id: int, name: str = "Default API Key") -> Optional[str]:
        """
        Create a new API key for a user (replaces existing key)

        Args:
            user_id: The user's ID
            name: Optional name for the key

        Returns:
            Raw API key string (show to user ONCE) or None on error
        """
        from models import ApiKey, db

        # Generate new key
        raw_key, key_hash, key_prefix = self.generate_key()

        # Check if user already has a key
        existing_key = ApiKey.query.filter_by(user_id=user_id).first()

        try:
            if existing_key:
                # UPDATE existing record with new key
                existing_key.key_hash = key_hash
                existing_key.key_prefix = key_prefix
                existing_key.name = name
                existing_key.is_active = True
                existing_key.created_at = datetime.now(SAUDI_TZ).replace(tzinfo=None)
                existing_key.revoked_at = None  # Clear revoked timestamp
                existing_key.last_used_at = None  # Reset usage
                existing_key.total_calls = 0  # Reset counter
                logger.info(f"Updated API key for user_id={user_id}: {key_prefix}")
            else:
                # CREATE new record
                new_key = ApiKey(
                    user_id=user_id,
                    key_hash=key_hash,
                    key_prefix=key_prefix,
                    name=name,
                    is_active=True
                )
                db.session.add(new_key)
                logger.info(f"Created new API key for user_id={user_id}: {key_prefix}")

            db.session.commit()
            return raw_key
        except Exception as e:
            logger.error(f"Error creating API key: {e}")
            db.session.rollback()
            return None

    def revoke_key(self, user_id: int) -> bool:
        """
        Revoke the API key for a user

        Args:
            user_id: The user's ID

        Returns:
            True if revoked, False if not found
        """
        from models import ApiKey, db

        api_key = ApiKey.query.filter_by(user_id=user_id, is_active=True).first()

        if not api_key:
            logger.warning(f"No active API key found for user_id={user_id}")
            return False

        api_key.is_active = False
        api_key.revoked_at = datetime.utcnow()

        try:
            db.session.commit()
            logger.info(f"Revoked API key for user_id={user_id}")
            return True
        except Exception as e:
            logger.error(f"Error revoking API key: {e}")
            db.session.rollback()
            return False

    def get_key_info(self, user_id: int) -> Optional[dict]:
        """
        Get API key info for display (never returns raw key)

        Args:
            user_id: The user's ID

        Returns:
            Dict with key info or None if no key exists
        """
        from models import ApiKey

        api_key = ApiKey.query.filter_by(user_id=user_id).first()

        if not api_key:
            return None

        return {
            'id': api_key.id,
            'key_prefix': api_key.key_prefix,
            'name': api_key.name,
            'is_active': api_key.is_active,
            'created_at': api_key.created_at,
            'last_used_at': api_key.last_used_at,
            'total_calls': api_key.total_calls,
            'revoked_at': api_key.revoked_at
        }


# Singleton instance
api_key_service = ApiKeyService()
