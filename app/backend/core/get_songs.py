import pymysql
import sys
import pandas as pd
import html



def connect():
    db = pymysql.connect(
        user="pe",
        password="bernatpudent",
        host="localhost", 
        port=8080,        
        database="viasona"
    )

    return db



def extract_songs(db):
    query = """
    SELECT 
        g.titol AS nom_grup,
        gl.titol AS titol_canco,
        gd.titol AS titol_album,
        gl.contingut AS lletra,
        gl.id_lletra AS id_lletra
    FROM 
        grups_lletres gl
    LEFT JOIN 
        grups_lletres_rel glr ON gl.id_lletra = glr.id_lletra
    LEFT JOIN 
        grups g ON glr.id_grup = g.id_grup
    LEFT JOIN 
        grups_discos_lletres_rel gdlr ON gl.id_lletra = gdlr.id_lletra
    LEFT JOIN 
        grups_discos gd ON gdlr.id_disc = gd.id_disc
    """
    
    df = pd.read_sql(query, db)
    df = df.applymap(lambda x: html.unescape(x) if isinstance(x, str) else x)
    print(f"Extracció completada: {len(df)} files obtingudes.")

    return df


def cleaning_and_grouping(df):

    # Conservem salts de línia
    df['lletra'] = df['lletra'].str.replace(r'<br\s*/?>', '\n', regex=True)
    df['lletra'] = df['lletra'].str.replace(r'<[^>]+>', '', regex=True)


    #Si una canço apareix en mes d'un album ens quedem amb una fila amb tots els albums
    df.dropna(subset=['lletra'], inplace=True)
    df = df[df['lletra'] != ''] # drop cançons sense lletra

    # PK = ['nom_grup', 'titol_canco', 'lletra']
    df = df.groupby(
        ['nom_grup', 'lletra', 'titol_canco']
    ).agg({
        'titol_album': lambda x: ' | '.join(x.dropna()),
        'id_lletra': 'min'
    }).reset_index()

    titles_with_artist = df[df['nom_grup'].notna()]['titol_canco'].unique()
    to_delete = df['nom_grup'].isna() & df['titol_canco'].isin(titles_with_artist)
    df = df[~to_delete]

    
    df.rename(columns={'nom_grup': 'artista', 'titol_canco': 'titol'}, inplace=True)

    print("Neteja completada")

    return df
        


    

if __name__ == '__main__':
    db = connect()
    df = extract_songs(db)
    df = cleaning_and_grouping(df)
    df.to_csv("cancons.csv", index=False, encoding='utf-8-sig')
    print("Dades guardades")



    