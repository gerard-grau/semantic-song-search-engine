import pymysql
from datetime import datetime

# =========================
# CONFIG
# =========================

HOST = "aulagpus.fib.upc.edu"
PORT = 60059
USER = "pe"
PASSWORD = "bernatpudent"   # posa-la aquí
DATABASE = "viasona"

OUTPUT_FILE = "database_report.md"
SAMPLE_ROWS = 5


# =========================
# HELPERS
# =========================

def md_escape(value):
    """Escape values for Markdown tables."""
    if value is None:
        return "NULL"
    text = str(value)
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("|", "\\|")
    if len(text) > 300:
        text = text[:300] + "..."
    return text


def write_table(md, headers, rows):
    md.write("| " + " | ".join(headers) + " |\n")
    md.write("| " + " | ".join(["---"] * len(headers)) + " |\n")

    for row in rows:
        md.write("| " + " | ".join(md_escape(x) for x in row) + " |\n")

    md.write("\n")


# =========================
# MAIN
# =========================

try:
    conn = pymysql.connect(
        host=HOST,
        port=PORT,
        user=USER,
        password=PASSWORD,
        database=DATABASE,
        connect_timeout=10,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )

    print("✅ Connected successfully")

    with conn.cursor() as cur, open(OUTPUT_FILE, "w", encoding="utf-8") as md:

        md.write(f"# Database report: `{DATABASE}`\n\n")
        md.write(f"Generated at: {datetime.now()}\n\n")
        md.write("---\n\n")

        # =========================
        # DATABASE INFO
        # =========================

        cur.execute("SELECT DATABASE() AS db, VERSION() AS version;")
        info = cur.fetchone()

        md.write("## General info\n\n")
        write_table(
            md,
            ["Database", "MariaDB/MySQL version"],
            [[info["db"], info["version"]]]
        )

        # =========================
        # TABLE LIST
        # =========================

        cur.execute("""
            SELECT 
                table_name,
                table_type,
                engine,
                table_rows,
                create_time,
                update_time,
                table_comment
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name;
        """, (DATABASE,))

        tables = cur.fetchall()

        md.write("## Tables overview\n\n")
        write_table(
            md,
            [
                "Table",
                "Type",
                "Engine",
                "Estimated rows",
                "Created",
                "Updated",
                "Comment"
            ],
            [
                [
                    t["table_name"],
                    t["table_type"],
                    t["engine"],
                    t["table_rows"],
                    t["create_time"],
                    t["update_time"],
                    t["table_comment"]
                ]
                for t in tables
            ]
        )

        # =========================
        # FOREIGN KEYS SUMMARY
        # =========================

        cur.execute("""
            SELECT
                kcu.table_name,
                kcu.column_name,
                kcu.referenced_table_name,
                kcu.referenced_column_name,
                rc.constraint_name,
                rc.update_rule,
                rc.delete_rule
            FROM information_schema.key_column_usage kcu
            LEFT JOIN information_schema.referential_constraints rc
                ON kcu.constraint_schema = rc.constraint_schema
                AND kcu.constraint_name = rc.constraint_name
            WHERE kcu.table_schema = %s
              AND kcu.referenced_table_name IS NOT NULL
            ORDER BY kcu.table_name, kcu.column_name;
        """, (DATABASE,))

        foreign_keys = cur.fetchall()

        md.write("## Foreign keys / relationships\n\n")

        if foreign_keys:
            write_table(
                md,
                [
                    "Table",
                    "Column",
                    "References table",
                    "References column",
                    "Constraint",
                    "ON UPDATE",
                    "ON DELETE"
                ],
                [
                    [
                        fk["table_name"],
                        fk["column_name"],
                        fk["referenced_table_name"],
                        fk["referenced_column_name"],
                        fk["constraint_name"],
                        fk["update_rule"],
                        fk["delete_rule"]
                    ]
                    for fk in foreign_keys
                ]
            )
        else:
            md.write("No explicit foreign keys found in `information_schema`.\n\n")
            md.write(
                "This does not necessarily mean there are no logical relationships; "
                "some databases use relation tables without declaring foreign key constraints.\n\n"
            )

        # =========================
        # DETAIL PER TABLE
        # =========================

        md.write("---\n\n")
        md.write("# Detailed tables\n\n")

        for table in tables:
            table_name = table["table_name"]

            print(f"Inspecting table: {table_name}")

            md.write(f"## `{table_name}`\n\n")

            # Exact row count
            try:
                cur.execute(f"SELECT COUNT(*) AS n FROM `{table_name}`;")
                row_count = cur.fetchone()["n"]
            except Exception as e:
                row_count = f"Error: {e}"

            md.write(f"**Rows:** `{row_count}`\n\n")

            # Columns
            cur.execute("""
                SELECT
                    column_name,
                    column_type,
                    is_nullable,
                    column_key,
                    column_default,
                    extra,
                    column_comment
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                ORDER BY ordinal_position;
            """, (DATABASE, table_name))

            columns = cur.fetchall()

            md.write("### Columns\n\n")
            write_table(
                md,
                [
                    "Column",
                    "Type",
                    "Nullable",
                    "Key",
                    "Default",
                    "Extra",
                    "Comment"
                ],
                [
                    [
                        c["column_name"],
                        c["column_type"],
                        c["is_nullable"],
                        c["column_key"],
                        c["column_default"],
                        c["extra"],
                        c["column_comment"]
                    ]
                    for c in columns
                ]
            )

            # Indexes
            cur.execute("""
                SELECT
                    index_name,
                    non_unique,
                    seq_in_index,
                    column_name,
                    index_type
                FROM information_schema.statistics
                WHERE table_schema = %s
                  AND table_name = %s
                ORDER BY index_name, seq_in_index;
            """, (DATABASE, table_name))

            indexes = cur.fetchall()

            md.write("### Indexes\n\n")

            if indexes:
                write_table(
                    md,
                    [
                        "Index",
                        "Non unique",
                        "Position",
                        "Column",
                        "Type"
                    ],
                    [
                        [
                            i["index_name"],
                            i["non_unique"],
                            i["seq_in_index"],
                            i["column_name"],
                            i["index_type"]
                        ]
                        for i in indexes
                    ]
                )
            else:
                md.write("No indexes found.\n\n")

            # Foreign keys for this table
            table_fks = [fk for fk in foreign_keys if fk["table_name"] == table_name]

            md.write("### Relationships from this table\n\n")

            if table_fks:
                write_table(
                    md,
                    [
                        "Column",
                        "References table",
                        "References column",
                        "ON UPDATE",
                        "ON DELETE"
                    ],
                    [
                        [
                            fk["column_name"],
                            fk["referenced_table_name"],
                            fk["referenced_column_name"],
                            fk["update_rule"],
                            fk["delete_rule"]
                        ]
                        for fk in table_fks
                    ]
                )
            else:
                md.write("No explicit foreign keys from this table.\n\n")

            # Show create table
            md.write("### CREATE TABLE\n\n")

            try:
                cur.execute(f"SHOW CREATE TABLE `{table_name}`;")
                create_result = cur.fetchone()
                create_sql = create_result["Create Table"]

                md.write("```sql\n")
                md.write(create_sql)
                md.write("\n```\n\n")

            except Exception as e:
                md.write(f"Could not get CREATE TABLE: `{e}`\n\n")

            # Sample rows
            md.write(f"### Sample rows `{SAMPLE_ROWS}`\n\n")

            try:
                cur.execute(f"SELECT * FROM `{table_name}` LIMIT {SAMPLE_ROWS};")
                sample = cur.fetchall()

                if sample:
                    sample_headers = list(sample[0].keys())
                    sample_rows = [
                        [row[h] for h in sample_headers]
                        for row in sample
                    ]

                    write_table(md, sample_headers, sample_rows)
                else:
                    md.write("Table is empty.\n\n")

            except Exception as e:
                md.write(f"Could not fetch sample rows: `{e}`\n\n")

            md.write("---\n\n")

    conn.close()

    print(f"✅ Report created: {OUTPUT_FILE}")

except Exception as e:
    print("❌ Error:", e)