# Database Scripts - PostgreSQL Migration

This folder contains all scripts for PostgreSQL database setup and migration.

---

## 📁 File Structure

```
scripts/db/
├── README.md                      # This file
├── check_db_connection.py         # Test PostgreSQL connection
├── create_tables_server.py        # Create tables using server schema
├── grant_permissions.py           # Grant PostgreSQL permissions
├── migrate_sqlite_to_postgres.py  # Main migration script
├── migrate_kb_only.py             # Migrate knowledge_base entries
├── check_sqlite_kb.py             # Check SQLite knowledge_base
└── verify_migration.py            # Verify migration results
```

---

## 🚀 Quick Start (Fresh Setup)

If setting up PostgreSQL from scratch:

```bash
cd scripts/db

# 1. Grant permissions (if needed)
python grant_permissions.py

# 2. Create tables
python create_tables_server.py

# 3. Migrate all data from SQLite
python migrate_sqlite_to_postgres.py

# 4. Migrate knowledge_base (if failed in step 3)
python migrate_kb_only.py

# 5. Verify everything
python verify_migration.py
```

---

## 📜 Script Descriptions

### 1. **check_db_connection.py**
Test PostgreSQL connection and display version.

```bash
python check_db_connection.py
```

**Output:**
```
('PostgreSQL 16.11',)
```

---

### 2. **create_tables_server.py**
Creates PostgreSQL tables using `server-code/model.py` schema.

```bash
python create_tables_server.py
```

**Creates:**
- user, agent, workflow, call_log, campaign, etc.
- 11 tables total

---

### 3. **grant_permissions.py**
Grants schema permissions to nevox_prod user.

```bash
python grant_permissions.py
```

**Use when:**
- Getting "permission denied for schema public" errors
- Setting up a new PostgreSQL database

---

### 4. **migrate_sqlite_to_postgres.py**
Main migration script - migrates all data from SQLite to PostgreSQL.

```bash
python migrate_sqlite_to_postgres.py
```

**Migrates:**
- 26 users
- 111 agents
- 1,743 call logs
- 75 campaigns
- And more... (2,554 total rows)

**Handles:**
- Schema differences between SQLite and PostgreSQL
- Foreign key constraints
- Reserved keywords (like 'user')

---

### 5. **migrate_kb_only.py**
Migrates only valid knowledge_base entries (skips orphaned ones).

```bash
python migrate_kb_only.py
```

**Use when:**
- knowledge_base table has 0 rows after main migration
- You have orphaned entries (references to deleted agents)

**Migrates:**
- Only entries with existing agents
- Skips orphaned data automatically

---

### 6. **check_sqlite_kb.py**
Checks knowledge_base table in SQLite database.

```bash
python check_sqlite_kb.py
```

**Shows:**
- Total entries
- Valid vs orphaned entries
- Details of each entry

**Example output:**
```
Total knowledge_base entries in SQLite: 11
Valid entries (can be migrated): 10
Orphaned entries (agent deleted): 1
```

---

### 7. **verify_migration.py**
Verifies migration results and shows row counts.

```bash
python verify_migration.py
```

**Shows:**
- Row count for each table
- Total rows migrated
- Sample users (first 5)

**Example output:**
```
✅ agent: 111 rows
✅ user: 26 rows
✅ call_log: 1743 rows
Total rows: 2554
```

---

## 🔧 Common Use Cases

### Check if Migration is Complete

```bash
python verify_migration.py
```

Look for any tables with 0 rows (except knowledge_base if you have orphaned data).

---

### Re-migrate Only knowledge_base

```bash
python check_sqlite_kb.py    # Check what's in SQLite
python migrate_kb_only.py    # Migrate valid entries
python verify_migration.py   # Verify results
```

---

### Test PostgreSQL Connection

```bash
python check_db_connection.py
```

---

### Troubleshoot Permission Issues

```bash
python grant_permissions.py
```

---

## 📊 Migration Results (Reference)

After successful migration, you should have:

| Table                  | Rows  |
|------------------------|-------|
| user                   | 26    |
| agent                  | 111   |
| call_log               | 1,743 |
| campaign               | 75    |
| campaign_contact       | 162   |
| workflow               | 15    |
| tool                   | 20    |
| agent_tool             | 31    |
| webhook_log            | 359   |
| inbound_configuration  | 2     |
| knowledge_base         | 10    |
| **Total**              | **2,554** |

---

## ⚠️ Important Notes

1. **DATABASE_URL must be set** in `.env` file:
   ```env
   DATABASE_URL=postgresql://nevox_prod:tdQJ%40u57SrVZg4v@pgm-l4v70dv4z1o481p3oo.pgsql.me-central-1.rds.aliyuncs.com:5432/nevox_prod
   ```

2. **Backup SQLite database** before migration:
   ```bash
   cp instance/voice_agent.db instance/voice_agent.db.backup
   ```

3. **Don't run migration twice** - it will create duplicates!
   - To re-migrate: truncate PostgreSQL tables first

4. **Schema source**: Uses `server-code/model.py` (simplified schema)
   - No ApiKey table
   - Simplified Workflow model

---

## 🆘 Troubleshooting

### Error: "permission denied for schema public"
```bash
python grant_permissions.py
```

### Error: "DATABASE_URL not set"
Add to `.env`:
```env
DATABASE_URL=postgresql://user:password@host:port/database
```

### knowledge_base has 0 rows
```bash
python check_sqlite_kb.py     # Check if SQLite has data
python migrate_kb_only.py     # Migrate valid entries
```

### Migration creates duplicates
Don't run migration scripts multiple times. To start fresh:
```sql
-- Connect to PostgreSQL and truncate tables (in reverse order)
TRUNCATE webhook_log CASCADE;
TRUNCATE agent_tool CASCADE;
TRUNCATE tool CASCADE;
TRUNCATE knowledge_base CASCADE;
-- ... truncate all tables
```

---

## ✅ Success Criteria

Migration is successful when:

1. ✅ All tables have expected row counts
2. ✅ `verify_migration.py` shows total ~2,554 rows
3. ✅ Flask app works with PostgreSQL
4. ✅ No errors in application logs
5. ✅ Can create new agents, call logs, etc.

---

## 📝 Next Steps After Migration

1. **Test your application**
   - Login, create agents, view call logs

2. **Monitor for issues**
   - Check logs for database errors

3. **Keep SQLite backup**
   - Don't delete for 1-2 weeks

4. **Update production**
   - Deploy with DATABASE_URL configured

---

**Database successfully migrated! 🎉**
