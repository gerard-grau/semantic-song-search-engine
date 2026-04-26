"""
Seed catalog of well-known Catalan songs and artists.

Each entry is a dict with 'title' and 'artist', both in their canonical
display form (original casing + accents). The parser normalises these at
load time, so you don't need to pre-process.

Extend freely — the parser rebuilds its indexes in ~constant time per entry.
"""

SONGS: list[dict[str, str]] = [
    # Lluís Llach
    {'title': "L'estaca",                          'artist': "Lluís Llach"},
    {'title': "Viatge a Ítaca",                    'artist': "Lluís Llach"},
    {'title': "Que tinguem sort",                  'artist': "Lluís Llach"},
    {'title': "Abril 74",                          'artist': "Lluís Llach"},
    {'title': "Companys, no és això",              'artist': "Lluís Llach"},
    {'title': "I si canto trist",                  'artist': "Lluís Llach"},
    {'title': "Un pont de mar blava",              'artist': "Lluís Llach"},
    {'title': "Vinyes verdes vora el mar",         'artist': "Lluís Llach"},

    # Joan Manuel Serrat
    {'title': "Paraules d'amor",                   'artist': "Joan Manuel Serrat"},
    {'title': "Mediterráneo",                      'artist': "Joan Manuel Serrat"},
    {'title': "Ara que tinc vint anys",            'artist': "Joan Manuel Serrat"},
    {'title': "Cançó de matinada",                 'artist': "Joan Manuel Serrat"},
    {'title': "La tieta",                          'artist': "Joan Manuel Serrat"},
    {'title': "Els vells amants",                  'artist': "Joan Manuel Serrat"},
    {'title': "Pare",                              'artist': "Joan Manuel Serrat"},

    # Raimon
    {'title': "Al vent",                           'artist': "Raimon"},
    {'title': "Diguem no",                         'artist': "Raimon"},
    {'title': "Jo vinc d'un silenci",              'artist': "Raimon"},
    {'title': "D'un temps, d'un país",             'artist': "Raimon"},
    {'title': "Indesinenter",                      'artist': "Raimon"},

    # Sau
    {'title': "Boig per tu",                       'artist': "Sau"},
    {'title': "El tren de mitjanit",               'artist': "Sau"},
    {'title': "Amb tu",                            'artist': "Sau"},
    {'title': "Una lluna a l'aigua",               'artist': "Sau"},

    # Sopa de Cabra
    {'title': "L'Empordà",                         'artist': "Sopa de Cabra"},
    {'title': "Camins",                            'artist': "Sopa de Cabra"},
    {'title': "Si et quedessis amb mi",            'artist': "Sopa de Cabra"},
    {'title': "Mai serem soldats",                 'artist': "Sopa de Cabra"},
    {'title': "Cor de foc",                        'artist': "Sopa de Cabra"},
    {'title': "El boig de la ciutat",              'artist': "Sopa de Cabra"},
    {'title': "La hiena",                          'artist': "Sopa de Cabra"},
    {'title': "El carrer dels torrents",           'artist': "Sopa de Cabra"},

    # Manel
    {'title': "Jo vull ser rei",                   'artist': "Manel"},
    {'title': "Aniversari",                        'artist': "Manel"},
    {'title': "Els guapos són els raros",          'artist': "Manel"},
    {'title': "Boomerang",                         'artist': "Manel"},
    {'title': "Teresa Rampell",                    'artist': "Manel"},
    {'title': "La gran il·lusió",                  'artist': "Manel"},
    {'title': "Al mar",                            'artist': "Manel"},
    {'title': "Benvolgut",                         'artist': "Manel"},
    {'title': "Una nit a l'Òpera",                 'artist': "Manel"},
    {'title': "Captatio benevolentiae",            'artist': "Manel"},
    {'title': "Els millors professors europeus",   'artist': "Manel"},

    # Els Pets
    {'title': "Bon dia",                           'artist': "Els Pets"},
    {'title': "Laura",                             'artist': "Els Pets"},
    {'title': "Vespre",                            'artist': "Els Pets"},
    {'title': "Tarragona m'esborrona",             'artist': "Els Pets"},
    {'title': "Una nit com aquesta",               'artist': "Els Pets"},
    {'title': "Fred",                              'artist': "Els Pets"},

    # Els Catarres
    {'title': "Jenifer",                           'artist': "Els Catarres"},
    {'title': "Vull estar amb tu",                 'artist': "Els Catarres"},
    {'title': "Rock'n'roll",                       'artist': "Els Catarres"},
    {'title': "Tots els meus principis",           'artist': "Els Catarres"},
    {'title': "Benvinguts al paradís",             'artist': "Els Catarres"},

    # Txarango
    {'title': "Vola",                              'artist': "Txarango"},
    {'title': "Tanca els ulls",                    'artist': "Txarango"},
    {'title': "Esperança",                         'artist': "Txarango"},
    {'title': "Benvinguts",                        'artist': "Txarango"},
    {'title': "Un pam de nas",                     'artist': "Txarango"},
    {'title': "La gran onada",                     'artist': "Txarango"},
    {'title': "Tots som poble",                    'artist': "Txarango"},

    # La Trinca
    {'title': "El meu avi",                        'artist': "La Trinca"},
    {'title': "Coses de l'idioma",                 'artist': "La Trinca"},
    {'title': "Festa major",                       'artist': "La Trinca"},

    # Antònia Font
    {'title': "Alegria",                           'artist': "Antònia Font"},
    {'title': "Batiscafo Katiuscas",               'artist': "Antònia Font"},
    {'title': "Camí avall",                        'artist': "Antònia Font"},
    {'title': "Coles de Brussel·les",              'artist': "Antònia Font"},
    {'title': "Me sobrepàs",                       'artist': "Antònia Font"},
    {'title': "L'amo del cel",                     'artist': "Antònia Font"},
    {'title': "Cinturó",                           'artist': "Antònia Font"},
    {'title': "Calgary 88",                        'artist': "Antònia Font"},

    # Marina Rossell
    {'title': "La gavina",                         'artist': "Marina Rossell"},
    {'title': "Corrandes d'exili",                 'artist': "Marina Rossell"},
    {'title': "Cap al cel",                        'artist': "Marina Rossell"},

    # Ovidi Montllor
    {'title': "La samarreta",                      'artist': "Ovidi Montllor"},
    {'title': "Homenatge a Teresa",                'artist': "Ovidi Montllor"},
    {'title': "La fera ferotge",                   'artist': "Ovidi Montllor"},
    {'title': "Perquè vull",                       'artist': "Ovidi Montllor"},

    # Lax'n'Busto
    {'title': "La ràdio",                          'artist': "Lax'n'Busto"},
    {'title': "Que no s'apagui la llum",           'artist': "Lax'n'Busto"},
    {'title': "Tants records",                     'artist': "Lax'n'Busto"},
    {'title': "Vas vestida de blanc",              'artist': "Lax'n'Busto"},

    # Obrint Pas
    {'title': "La flama",                          'artist': "Obrint Pas"},
    {'title': "No tenim por",                      'artist': "Obrint Pas"},
    {'title': "La revolta dels genolls",           'artist': "Obrint Pas"},

    # Gossos
    {'title': "Fràgil",                            'artist': "Gossos"},
    {'title': "Un dia diferent",                   'artist': "Gossos"},
    {'title': "Un cop d'ala",                      'artist': "Gossos"},

    # Roger Mas
    {'title': "Uhò",                               'artist': "Roger Mas"},
    {'title': "Mística domèstica",                 'artist': "Roger Mas"},

    # Blaumut
    {'title': "Pa amb oli i sal",                  'artist': "Blaumut"},
    {'title': "El turista",                        'artist': "Blaumut"},
    {'title': "Primer amor",                       'artist': "Blaumut"},

    # The Tyets
    {'title': "Coti x Coti",                       'artist': "The Tyets"},
    {'title': "Olivia",                            'artist': "The Tyets"},
    {'title': "Aiguardent",                        'artist': "The Tyets"},
    {'title': "Sense tu",                          'artist': "The Tyets"},

    # Oques Grasses
    {'title': "Tot el que has donat",              'artist': "Oques Grasses"},
    {'title': "Lliures i salvatges",               'artist': "Oques Grasses"},
    {'title': "Festa Major",                       'artist': "Oques Grasses"},
    {'title': "Ben igual",                         'artist': "Oques Grasses"},
    {'title': "Fran",                              'artist': "Oques Grasses"},

    # Figa Flawas
    {'title': "Suada",                             'artist': "Figa Flawas"},
    {'title': "Traca traca",                       'artist': "Figa Flawas"},

    # Buhos
    {'title': "Besos",                             'artist': "Buhos"},
    {'title': "Coco",                              'artist': "Buhos"},
    {'title': "Volem més",                         'artist': "Buhos"},
    {'title': "Un dia qualsevol",                  'artist': "Buhos"},

    # Doctor Prats
    {'title': "Empordà amor meu",                  'artist': "Doctor Prats"},
    {'title': "Circus",                            'artist': "Doctor Prats"},
    {'title': "Tocats de l'ala",                   'artist': "Doctor Prats"},
    {'title': "Ma vida",                           'artist': "Doctor Prats"},

    # Suu
    {'title': "Corrents d'aire",                   'artist': "Suu"},
    {'title': "El primer dia",                     'artist': "Suu"},

    # Mishima
    {'title': "L'amor feliç",                      'artist': "Mishima"},
    {'title': "Ghost Writer",                      'artist': "Mishima"},
    {'title': "Tots els noms",                     'artist': "Mishima"},
    {'title': "Viure no és tan senzill",           'artist': "Mishima"},

    # Els Amics de les Arts
    {'title': "Jean-Luc",                          'artist': "Els Amics de les Arts"},
    {'title': "Ja no ens passa",                   'artist': "Els Amics de les Arts"},
    {'title': "Louis, Louis",                      'artist': "Els Amics de les Arts"},
    {'title': "Monsieur Cousteau",                 'artist': "Els Amics de les Arts"},

    # Joan Dausà
    {'title': "Ja volem",                          'artist': "Joan Dausà"},
    {'title': "El gran circ del cor",              'artist': "Joan Dausà"},
    {'title': "Es fa llarg esperar",               'artist': "Joan Dausà"},

    # Miki Núñez
    {'title': "Escriurem",                         'artist': "Miki Núñez"},
    {'title': "Celebraré",                         'artist': "Miki Núñez"},
    {'title': "Visca l'amor",                      'artist': "Miki Núñez"},

    # Stay Homas
    {'title': "Spaghetti",                         'artist': "Stay Homas"},
    {'title': "Sobrassada",                        'artist': "Stay Homas"},

    # Beth
    {'title': "Dime",                              'artist': "Beth"},
    {'title': "En prou",                           'artist': "Beth"},

    # Nil Moliner
    {'title': "Soldadito marinero",                'artist': "Nil Moliner"},

    # Pau Vallvé
    {'title': "Sí sí sí",                          'artist': "Pau Vallvé"},
    {'title': "Petit tricicle",                    'artist': "Pau Vallvé"},

    # Sílvia Pérez Cruz
    {'title': "11 de novembre",                    'artist': "Sílvia Pérez Cruz"},
    {'title': "Gallo rojo, gallo negro",           'artist': "Sílvia Pérez Cruz"},

    # Judit Neddermann
    {'title': "Viatge",                            'artist': "Judit Neddermann"},
    {'title': "Nua",                               'artist': "Judit Neddermann"},

    # Ramon Mirabet
    {'title': "Lemonade",                          'artist': "Ramon Mirabet"},
    {'title': "Home is where the heart is",        'artist': "Ramon Mirabet"},

    # ZOO
    {'title': "Estiu",                             'artist': "ZOO"},
    {'title': "Raval",                             'artist': "ZOO"},

    # Quimi Portet
    {'title': "Tots els meus fans",                'artist': "Quimi Portet"},

    # Maria del Mar Bonet
    {'title': "Si tornés a néixer",                'artist': "Maria del Mar Bonet"},

    # Macedònia
    {'title': "Mandonguilles",                     'artist': "Macedònia"},
    {'title': "Super top secret",                  'artist': "Macedònia"},

    # Ginestà
    {'title': "Tots els noms que t'he posat mai",  'artist': "Ginestà"},
    {'title': "Nostalgia",                         'artist': "Ginestà"},
    {'title': "Tu, jo i el baf",                   'artist': "Ginestà"},

    # Mazoni
    {'title': "Les ciutats",                       'artist': "Mazoni"},

    # La Gossa Sorda
    {'title': "Tio Canya",                         'artist': "La Gossa Sorda"},
    {'title': "El carter",                         'artist': "La Gossa Sorda"},

    # Pep Sala
    {'title': "Maria",                             'artist': "Pep Sala"},

    # Sanjosex
    {'title': "La mala reputació",                 'artist': "Sanjosex"},

    # Cesk Freixas
    {'title': "Un dia qualsevol",                  'artist': "Cesk Freixas"},

    # Pau Alabajos
    {'title': "Gràcies a la vida",                 'artist': "Pau Alabajos"},

    # Feliu Ventura
    {'title': "Un diumenge qualsevol",             'artist': "Feliu Ventura"},

    # Lluís Gavaldà
    {'title': "Pocs amics",                        'artist': "Lluís Gavaldà"},

    # Dept
    {'title': "La Taronja",                        'artist': "Dept"},

    # El Petit de Cal Eril
    {'title': "La fi i els terratrèmols",          'artist': "El Petit de Cal Eril"},

    # Anímic
    {'title': "Els nens del fum",                  'artist': "Anímic"},
]


def unique_artists() -> list[str]:
    """Return the sorted list of distinct artist names in the catalog."""
    return sorted({s['artist'] for s in SONGS})


if __name__ == '__main__':
    artists = unique_artists()
    print(f"Catalog: {len(SONGS)} songs, {len(artists)} artists")
    for a in artists:
        n = sum(1 for s in SONGS if s['artist'] == a)
        print(f"  {a:<32} {n} song{'s' if n != 1 else ''}")
