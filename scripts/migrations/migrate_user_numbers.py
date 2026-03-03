"""
Migration script to add user-specific sequential numbering to Agents and Campaigns
"""
from app import app, db, Agent, Campaign
from sqlalchemy import text

def migrate_user_numbers():
    with app.app_context():
        print("Starting migration to add user-specific sequential numbers...")

        # Add columns if they don't exist
        try:
            with db.engine.connect() as conn:
                # Check if columns exist, if not add them
                print("Adding user_agent_number column to Agent table...")
                try:
                    conn.execute(text('ALTER TABLE agent ADD COLUMN user_agent_number INTEGER'))
                    conn.commit()
                    print("[OK] Added user_agent_number column")
                except Exception as e:
                    if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                        print("[OK] user_agent_number column already exists")
                    else:
                        raise e

                print("Adding user_campaign_number column to Campaign table...")
                try:
                    conn.execute(text('ALTER TABLE campaign ADD COLUMN user_campaign_number INTEGER'))
                    conn.commit()
                    print("[OK] Added user_campaign_number column")
                except Exception as e:
                    if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                        print("[OK] user_campaign_number column already exists")
                    else:
                        raise e

        except Exception as e:
            print(f"Error adding columns: {e}")
            return

        # Populate user_agent_number for existing agents
        print("\nPopulating user_agent_number for existing agents...")
        agents = Agent.query.order_by(Agent.user_id, Agent.created_at).all()
        user_agent_counts = {}

        for agent in agents:
            if agent.user_id not in user_agent_counts:
                user_agent_counts[agent.user_id] = 0
            user_agent_counts[agent.user_id] += 1
            agent.user_agent_number = user_agent_counts[agent.user_id]

        db.session.commit()
        print(f"[OK] Updated {len(agents)} agents with user-specific numbers")

        # Populate user_campaign_number for existing campaigns
        print("\nPopulating user_campaign_number for existing campaigns...")
        campaigns = Campaign.query.order_by(Campaign.user_id, Campaign.created_at).all()
        user_campaign_counts = {}

        for campaign in campaigns:
            if campaign.user_id not in user_campaign_counts:
                user_campaign_counts[campaign.user_id] = 0
            user_campaign_counts[campaign.user_id] += 1
            campaign.user_campaign_number = user_campaign_counts[campaign.user_id]

        db.session.commit()
        print(f"[OK] Updated {len(campaigns)} campaigns with user-specific numbers")

        print("\n[SUCCESS] Migration completed successfully!")
        print("\nSummary:")
        for user_id, count in user_agent_counts.items():
            print(f"  User {user_id}: {count} agents")
        for user_id, count in user_campaign_counts.items():
            print(f"  User {user_id}: {count} campaigns")

if __name__ == '__main__':
    migrate_user_numbers()
