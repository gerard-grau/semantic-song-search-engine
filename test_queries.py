import pymysql

HOST = "aulagpus.fib.upc.edu"
PORT = 60059
USER = "pe"
PASSWORD = "bernatpudent"
DATABASE = "viasona"

try:
    conn = pymysql.connect(
        host=HOST,
        port=PORT,
        user=USER,
        password=PASSWORD,
        database=DATABASE,
        connect_timeout=5
    )

    print("✅ Connected successfully")

    with conn.cursor() as cur:
        cur.execute("SELECT DATABASE();")
        result = cur.fetchone()
        print("Current DB:", result)

        cur.execute("SHOW TABLES;")
        tables = cur.fetchall()
        print("Tables:", tables)

        query = """
            SELECT 
                g.titol AS nom_grup,
                gl.titol AS titol_canco,
                gl.contingut AS lletra,
                gl.id_lletra AS id_lletra
            FROM 
                grups_lletres gl
            LEFT JOIN 
                grups_lletres_rel glr ON gl.id_lletra = glr.id_lletra
            LEFT JOIN 
                grups g ON glr.id_grup = g.id_grup
        """

        # Example query
        cur.execute(query)
        rows = cur.fetchall()

        print("\nSample rows:")
        for row in rows:
            print(row)
            break

    conn.close()

except Exception as e:
    print("❌ Error:", e)