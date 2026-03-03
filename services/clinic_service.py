"""
Clinic Service — Phase 2 Backend

Handles clinic feature configuration and workflow creation.
This service is completely isolated and can be deleted with:
  - Delete this file
  - Remove clinic_feature_type and clinic_config from Workflow model
  - Delete the clinic migration

Dependencies: models.Workflow, models.Agent, webhook_service
"""

import json
import logging
from datetime import datetime
from models import db, Workflow, Agent, SAUDI_TZ
from services.webhook_service import webhook_service

logger = logging.getLogger(__name__)


class ClinicService:
    """Manages clinic feature workflows and configurations"""

    @staticmethod
    def create_clinic_workflow(user_id, feature_type, config_data):
        """
        Create or update a clinic feature workflow.

        Args:
            user_id (int): User ID creating the workflow
            feature_type (str): Clinic feature type
                - 'appointment_booking'
                - 'noshow_recovery'
                - 'patient_reminders'
                - 'vaccination_campaign'
                - 'new_patient_intake'
            config_data (dict): Configuration with:
                - agent_id: required
                - pre_call_webhook_url: optional
                - post_call_webhook_url: optional
                - ... feature-specific fields ...

        Returns:
            Workflow: Created or updated workflow object

        Raises:
            ValueError: If agent not found or required fields missing
        """
        # Validate agent exists
        agent_id = config_data.get('agent_id')
        if not agent_id:
            raise ValueError('Agent ID is required')

        agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            raise ValueError('Agent not found or does not belong to this user')

        # Extract webhook URLs from config (don't store them in clinic_config)
        pre_call_url = config_data.pop('pre_call_webhook_url', None)
        post_call_url = config_data.pop('post_call_webhook_url', None)

        # Check if workflow already exists for this feature
        workflow = Workflow.query.filter_by(
            user_id=user_id,
            clinic_feature_type=feature_type
        ).first()

        if workflow:
            # Update existing workflow
            workflow.webhook_url = post_call_url or workflow.webhook_url
            workflow.pre_call_webhook_url = pre_call_url
            workflow.pre_call_enabled = bool(pre_call_url)
            workflow.post_call_enabled = True
            workflow.clinic_config = json.dumps(config_data)
            workflow.updated_at = datetime.now(SAUDI_TZ).replace(tzinfo=None)

            logger.info(f"Updated clinic workflow: {feature_type} (workflow_id: {workflow.id}, user: {user_id})")
        else:
            # Create new workflow
            workflow_name = feature_type.replace('_', ' ').title()
            workflow = Workflow(
                user_id=user_id,
                name=workflow_name,
                clinic_feature_type=feature_type,
                webhook_url=post_call_url or f"https://n8n.yourdomain.com/webhook/{feature_type}/post",
                pre_call_webhook_url=pre_call_url,
                pre_call_enabled=bool(pre_call_url),
                post_call_enabled=True,
                api_key=webhook_service.generate_api_key(),
                clinic_config=json.dumps(config_data),
                is_active=True
            )
            db.session.add(workflow)

            logger.info(f"Created clinic workflow: {feature_type} (user: {user_id})")

        db.session.commit()
        return workflow

    @staticmethod
    def get_clinic_workflow(user_id, feature_type):
        """
        Get a clinic feature workflow.

        Args:
            user_id (int): User ID
            feature_type (str): Clinic feature type

        Returns:
            Workflow or None: Workflow if exists, None otherwise
        """
        return Workflow.query.filter_by(
            user_id=user_id,
            clinic_feature_type=feature_type
        ).first()

    @staticmethod
    def get_clinic_config(workflow):
        """
        Parse clinic configuration from workflow.

        Args:
            workflow (Workflow): Workflow object

        Returns:
            dict: Parsed configuration, or empty dict if none
        """
        if not workflow or not workflow.clinic_config:
            return {}

        try:
            return json.loads(workflow.clinic_config)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse clinic_config for workflow {workflow.id}")
            return {}

    @staticmethod
    def list_clinic_workflows(user_id):
        """
        List all clinic feature workflows for a user.

        Args:
            user_id (int): User ID

        Returns:
            list: List of Workflow objects with clinic features
        """
        return Workflow.query.filter_by(
            user_id=user_id
        ).filter(
            Workflow.clinic_feature_type.isnot(None)
        ).all()

    @staticmethod
    def delete_clinic_workflow(user_id, feature_type):
        """
        Delete a clinic feature workflow.

        Args:
            user_id (int): User ID
            feature_type (str): Clinic feature type

        Returns:
            bool: True if deleted, False if not found
        """
        workflow = Workflow.query.filter_by(
            user_id=user_id,
            clinic_feature_type=feature_type
        ).first()

        if workflow:
            db.session.delete(workflow)
            db.session.commit()
            logger.info(f"Deleted clinic workflow: {feature_type} (workflow_id: {workflow.id}, user: {user_id})")
            return True

        return False

    @staticmethod
    def get_clinic_feature_status(user_id, feature_type):
        """
        Get configuration status for a clinic feature.

        Args:
            user_id (int): User ID
            feature_type (str): Clinic feature type

        Returns:
            dict: Status info with keys:
                - configured (bool): Whether feature is configured
                - workflow_id (int or None): Workflow ID if configured
                - agent_id (int or None): Assigned agent ID
                - last_updated (str or None): ISO format datetime
        """
        workflow = ClinicService.get_clinic_workflow(user_id, feature_type)

        if not workflow:
            return {
                'configured': False,
                'workflow_id': None,
                'agent_id': None,
                'last_updated': None
            }

        config = ClinicService.get_clinic_config(workflow)

        return {
            'configured': True,
            'workflow_id': workflow.id,
            'agent_id': config.get('agent_id'),
            'last_updated': workflow.updated_at.isoformat() if workflow.updated_at else None
        }

    @staticmethod
    def validate_clinic_config(feature_type, config_data):
        """
        Validate clinic configuration data.

        Args:
            feature_type (str): Clinic feature type
            config_data (dict): Configuration to validate

        Returns:
            tuple: (is_valid, error_message)
        """
        # Common validations
        if not config_data.get('agent_id'):
            return False, 'Agent is required'

        try:
            int(config_data['agent_id'])
        except (ValueError, TypeError):
            return False, 'Agent ID must be a number'

        # Feature-specific validations
        if feature_type == 'appointment_booking':
            if config_data.get('min_advance_hours') and config_data.get('max_advance_days'):
                if int(config_data['min_advance_hours']) < 0:
                    return False, 'Minimum advance hours cannot be negative'
                if int(config_data['max_advance_days']) < 1:
                    return False, 'Maximum advance days must be at least 1'

        elif feature_type == 'vaccination_campaign':
            if not config_data.get('campaign_name'):
                return False, 'Campaign name is required'
            if not config_data.get('campaign_type'):
                return False, 'Campaign type is required'

        return True, None

    @staticmethod
    def create_campaign(user_id, campaign_name, config_data):
        """
        Create a new vaccination campaign (always creates new, never updates).

        Args:
            user_id (int): User ID creating the campaign
            campaign_name (str): Campaign name
            config_data (dict): Campaign configuration

        Returns:
            Workflow: Created campaign workflow object

        Raises:
            ValueError: If agent not found or required fields missing
        """
        # Validate agent exists
        agent_id = config_data.get('agent_id')
        if not agent_id:
            raise ValueError('Agent ID is required')

        agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            raise ValueError('Agent not found or does not belong to this user')

        # Extract webhook URLs
        pre_call_url = config_data.pop('pre_call_webhook_url', None)
        post_call_url = config_data.pop('post_call_webhook_url', None)

        # Always create new campaign (don't check for existing)
        campaign = Workflow(
            user_id=user_id,
            name=campaign_name,
            clinic_feature_type='vaccination_campaign',
            webhook_url=post_call_url or f"https://n8n.yourdomain.com/webhook/vaccination-campaign/post",
            pre_call_webhook_url=pre_call_url,
            pre_call_enabled=bool(pre_call_url),
            post_call_enabled=True,
            api_key=webhook_service.generate_api_key(),
            clinic_config=json.dumps(config_data),
            is_active=True
        )
        db.session.add(campaign)
        db.session.commit()

        logger.info(f"Created vaccination campaign: {campaign_name} (campaign_id: {campaign.id}, user: {user_id})")
        return campaign


# Singleton instance
clinic_service = ClinicService()
