import psycopg2

conn = psycopg2.connect(
    host="pgm-l4v70dv4z1o481p3oo.pgsql.me-central-1.rds.aliyuncs.com",
    port=5432,
    database="nevox_prod",
    user="nevox_prod",
    password="tdQJ@u57SrVZg4v",
    sslmode="disable"

)

cur = conn.cursor()
cur.execute("SELECT version();")
print(cur.fetchone())
