"""
Migration script to create InboundConfiguration table and migrate existing inbound agents
This prevents agent duplication by linking phone numbers to existing agents
"""
from app import app, db, Agent, InboundConfiguration
from sqlalchemy import text

def migrate_inbound_configuration():
    with app.app_context():
        print("=" * 60)
        print("INBOUND CONFIGURATION MIGRATION")
        print("=" * 60)

        # Step 1: Create the inbound_configuration table
        print("\n[STEP 1] Creating inbound_configuration table...")
        try:
            db.create_all()
            print("[OK] inbound_configuration table created")
        except Exception as e:
            print(f"[INFO] Table may already exist: {e}")

        # Step 2: Find all inbound agents
        print("\n[STEP 2] Finding existing inbound agents...")
        inbound_agents = Agent.query.filter_by(call_type='inbound').all()
        print(f"[OK] Found {len(inbound_agents)} inbound agents to migrate")

        if not inbound_agents:
            print("\n[SUCCESS] No inbound agents to migrate. Migration complete!")
            return

        # Step 3: For each inbound agent, try to find matching outbound agent
        print("\n[STEP 3] Migrating inbound agents to InboundConfiguration...")
        migrated = 0
        skipped = 0

        for inbound_agent in inbound_agents:
            print(f"\n  Processing: {inbound_agent.name} (ID: {inbound_agent.id})")
            print(f"    Phone: {inbound_agent.phone_number or 'N/A'}")
            print(f"    Voice: {inbound_agent.voice_name}")

            # Try to find matching outbound agent with same configuration
            matching_agent = Agent.query.filter_by(
                user_id=inbound_agent.user_id,
                call_type='outbound',
                voice_id=inbound_agent.voice_id,
                voice_name=inbound_agent.voice_name
            ).first()

            if matching_agent:
                print(f"    [OK] Found matching outbound agent: {matching_agent.name} (ID: {matching_agent.id})")

                # Check if phone number is set
                if not inbound_agent.phone_number:
                    print(f"    [SKIP] No phone number set - keeping as-is for manual configuration")
                    skipped += 1
                    continue

                # Check if this phone number already exists in InboundConfiguration
                existing_config = InboundConfiguration.query.filter_by(
                    phone_number=inbound_agent.phone_number
                ).first()

                if existing_config:
                    print(f"    [SKIP] Phone number already configured - deleting duplicate inbound agent")
                    db.session.delete(inbound_agent)
                    skipped += 1
                    continue

                # Create InboundConfiguration
                config = InboundConfiguration(
                    user_id=inbound_agent.user_id,
                    name=inbound_agent.name,
                    agent_id=matching_agent.id,
                    phone_number=inbound_agent.phone_number,
                    dispatch_rule_id=inbound_agent.dispatch_rule_id,
                    trunk_id=inbound_agent.inbound_trunk_id,
                    created_at=inbound_agent.created_at
                )

                db.session.add(config)

                # Delete the duplicate inbound agent
                db.session.delete(inbound_agent)

                print(f"    [OK] Created InboundConfiguration and deleted duplicate agent")
                migrated += 1

            else:
                print(f"    [WARNING] No matching outbound agent found")
                print(f"    [ACTION] Converting inbound agent to outbound for reuse")

                # Convert inbound agent to outbound so it can be used
                inbound_agent.call_type = 'outbound'
                inbound_agent.dispatch_rule_id = None
                inbound_agent.phone_number = None
                inbound_agent.inbound_trunk_id = None

                print(f"    [OK] Converted to outbound agent - can be linked to InboundConfiguration later")
                migrated += 1

        # Commit all changes
        try:
            db.session.commit()
            print("\n" + "=" * 60)
            print("[SUCCESS] Migration completed successfully!")
            print("=" * 60)
            print(f"\nSummary:")
            print(f"  Migrated: {migrated}")
            print(f"  Skipped: {skipped}")
            print(f"\nNext steps:")
            print("  1. Review your inbound configurations in the Inbound Agents page")
            print("  2. Reconfigure any that weren't automatically migrated")
            print("  3. Test inbound calls to ensure they work correctly")

        except Exception as e:
            db.session.rollback()
            print(f"\n[ERROR] Migration failed: {e}")
            print("Rolling back changes...")
            raise

if __name__ == '__main__':
    migrate_inbound_configuration()
