# PostgreSQL Database Setup & Migration Guide

## ✅ Completed Setup

Your local environment is now configured to use PostgreSQL:

1. ✅ **psycopg2-binary** added to requirements.txt and installed
2. ✅ **DATABASE_URL** configured in .env
3. ✅ **Database connection** tested successfully (PostgreSQL 16.11)
4. ✅ **Migration scripts** created

---

## 📋 Next Steps

### Step 1: Create Tables on Staging (Already Done)

You mentioned you already ran `create_tables.py` on staging. If not:

```bash
python create_tables.py
```

This creates all tables with the correct schema (no data).

---

### Step 2: Import Data from Staging to Local

1. **Add staging database URL to .env**:

```env
STAGING_DATABASE_URL=postgresql://username:password@staging-host:5432/database_name
```

2. **Run the import script**:

```bash
python import_from_staging.py
```

This will:
- ✅ Connect to both staging and local databases
- ✅ Copy all data in the correct order (respecting foreign keys)
- ✅ Show progress for each table
- ✅ Display final statistics

---

## 📁 Database Scripts

### `check_db_connection.py`
Simple connection test - prints PostgreSQL version.

```bash
python check_db_connection.py
```

### `create_tables.py`
Creates all database tables (schema only, no data).

```bash
python create_tables.py
```

### `import_from_staging.py`
Imports all data from staging database to local database.

```bash
python import_from_staging.py
```

**Import Order** (respects foreign key constraints):
1. user
2. workflow
3. agent
4. inbound_configuration
5. call_log
6. campaign
7. campaign_contact
8. knowledge_base
9. tool
10. agent_tool
11. webhook_log
12. api_key

---

## 🔧 Current Configuration

**Local Database**:
```
Host: pgm-l4v70dv4z1o481p3oo.pgsql.me-central-1.rds.aliyuncs.com
Port: 5432
Database: nevox_prod
User: nevox_prod
```

**Connection String** (in .env):
```
DATABASE_URL=postgresql://nevox_prod:tdQJ%40u57SrVZg4v@pgm-l4v70dv4z1o481p3oo.pgsql.me-central-1.rds.aliyuncs.com:5432/nevox_prod
```

---

## 🛠️ Troubleshooting

### Connection Issues

```bash
python check_db_connection.py
```

Should output: `('PostgreSQL 16.11',)`

### View All Tables

```python
from database import get_table_names
print(get_table_names())
```

### Verify Data Import

After running `import_from_staging.py`, the script will show row counts for all tables.

---

## 🔒 Security Notes

- ⚠️ Never commit `.env` file to version control
- ⚠️ Database credentials are in `.env` - keep it secure
- ⚠️ Consider using environment-specific .env files (.env.local, .env.staging, .env.production)

---

## 📊 Database Schema

The database includes these tables:
- **user** - User accounts and authentication
- **agent** - Voice agents configuration
- **inbound_configuration** - Inbound phone numbers
- **call_log** - Call history and transcriptions
- **campaign** - Outbound call campaigns
- **campaign_contact** - Campaign contacts
- **knowledge_base** - Agent knowledge base files
- **tool** - Custom tools for agents
- **agent_tool** - Agent-tool relationships
- **workflow** - n8n workflow integrations
- **webhook_log** - Webhook execution logs
- **api_key** - API keys for external integrations
