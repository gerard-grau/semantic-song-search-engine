"""Add a manually-assigned `genre` column to top_5000_songs_part01.csv.

Classification of each of the 500 songs into one of:
{folk, cançó autor, pop-rock, rumba, havanera, música urbana}

Decisions are based on artist/song knowledge:
- cançó autor: nova cançó & singer-songwriter tradition (Llach, Serrat, Raimon,
  Ovidi, M. del Mar Bonet, Marina Rossell, Cesk Freixas, Joan Dausà,
  Sílvia Pérez Cruz, theatre-songwriting pieces like Petit Príncep / Mar i cel,
  Adrià Puntí, Roger Mas, Pau Riba, Sisa, Maria Jaume, Judit Neddermann, …).
- pop-rock: Els Pets, Manel, Txarango, Buhos, Catarres, Sopa de Cabra,
  Lax'n'Busto, Sau, Oques Grasses, Fúmiga, Ludwig Band, Antònia Font,
  Amics de les Arts, Ginestà, Aspencat, Doctor Prats, Blaumut, …
- folk: traditional songs, nadales, sardanes cantades, cançó d'autor infantil
  (Xesco Boix, Dàmaris Gelabert, Club Súper 3, Mainasons, Dani Miquel),
  cançó tradicional (Botifarra, Música Nostra, Alosa, S'Albaida, Uc,
  Esquirols on traditional themes, Roba Estesa, …).
- rumba: rumba catalana — Gato Pérez, Sabor de Gràcia, Xitxarel·los, FLAKKA.
- havanera: maritime habanera tradition — Port Bo, Peix Fregit, Ultramar,
  Pescadors de l'Escala, Cris Juanico's "A la ciutat de Nàpols",
  "Vestida de nit", "La gavina".
- música urbana: rap / trap / urban-pop — Figa Flawas, The Tyets, Lildami,
  31 FAM, Flashy Ice Cream, Naina, P.A.W.N. Gang, FLAKKA-like trap, Tacho,
  Carles Caselles, Baya Baye, Malifeta, Sandra Monfort, Kelly Isaiah, …
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "top_5000_songs_part01.csv"
DST = HERE / "top_5000_songs_part01_genre.csv"

GENRES = {
    1: "cançó autor", 2: "pop-rock", 3: "pop-rock", 4: "cançó autor",
    5: "cançó autor", 6: "folk", 7: "cançó autor", 8: "cançó autor",
    9: "pop-rock", 10: "pop-rock", 11: "cançó autor", 12: "pop-rock",
    13: "pop-rock", 14: "folk", 15: "pop-rock", 16: "pop-rock",
    17: "cançó autor", 18: "pop-rock", 19: "folk", 20: "cançó autor",
    21: "cançó autor", 22: "pop-rock", 23: "pop-rock", 24: "cançó autor",
    25: "folk", 26: "cançó autor", 27: "cançó autor", 28: "cançó autor",
    29: "pop-rock", 30: "música urbana", 31: "pop-rock", 32: "pop-rock",
    33: "cançó autor", 34: "música urbana", 35: "folk", 36: "pop-rock",
    37: "cançó autor", 38: "pop-rock", 39: "cançó autor", 40: "pop-rock",
    41: "folk", 42: "cançó autor", 43: "cançó autor", 44: "folk",
    45: "cançó autor", 46: "pop-rock", 47: "folk", 48: "música urbana",
    49: "cançó autor", 50: "pop-rock", 51: "havanera", 52: "cançó autor",
    53: "pop-rock", 54: "folk", 55: "pop-rock", 56: "pop-rock",
    57: "pop-rock", 58: "folk", 59: "folk", 60: "cançó autor",
    61: "pop-rock", 62: "pop-rock", 63: "folk", 64: "pop-rock",
    65: "pop-rock", 66: "cançó autor", 67: "folk", 68: "folk",
    69: "pop-rock", 70: "cançó autor", 71: "cançó autor", 72: "folk",
    73: "havanera", 74: "pop-rock", 75: "cançó autor", 76: "pop-rock",
    77: "pop-rock", 78: "folk", 79: "cançó autor", 80: "pop-rock",
    81: "folk", 82: "folk", 83: "folk", 84: "cançó autor",
    85: "pop-rock", 86: "pop-rock", 87: "cançó autor", 88: "pop-rock",
    89: "folk", 90: "pop-rock", 91: "folk", 92: "pop-rock",
    93: "música urbana", 94: "pop-rock", 95: "folk", 96: "pop-rock",
    97: "cançó autor", 98: "folk", 99: "cançó autor", 100: "pop-rock",
    101: "folk", 102: "cançó autor", 103: "cançó autor", 104: "folk",
    105: "folk", 106: "cançó autor", 107: "cançó autor", 108: "pop-rock",
    109: "cançó autor", 110: "pop-rock", 111: "cançó autor", 112: "pop-rock",
    113: "folk", 114: "música urbana", 115: "folk", 116: "pop-rock",
    117: "cançó autor", 118: "cançó autor", 119: "pop-rock", 120: "folk",
    121: "pop-rock", 122: "pop-rock", 123: "havanera", 124: "pop-rock",
    125: "pop-rock", 126: "pop-rock", 127: "pop-rock", 128: "pop-rock",
    129: "pop-rock", 130: "música urbana", 131: "cançó autor", 132: "pop-rock",
    133: "rumba", 134: "pop-rock", 135: "pop-rock", 136: "pop-rock",
    137: "pop-rock", 138: "folk", 139: "folk", 140: "folk",
    141: "folk", 142: "pop-rock", 143: "cançó autor", 144: "folk",
    145: "pop-rock", 146: "pop-rock", 147: "folk", 148: "folk",
    149: "cançó autor", 150: "folk", 151: "pop-rock", 152: "cançó autor",
    153: "folk", 154: "folk", 155: "folk", 156: "música urbana",
    157: "cançó autor", 158: "folk", 159: "folk", 160: "pop-rock",
    161: "folk", 162: "folk", 163: "folk", 164: "cançó autor",
    165: "folk", 166: "cançó autor", 167: "cançó autor", 168: "cançó autor",
    169: "folk", 170: "folk", 171: "folk", 172: "pop-rock",
    173: "folk", 174: "folk", 175: "cançó autor", 176: "pop-rock",
    177: "folk", 178: "folk", 179: "cançó autor", 180: "cançó autor",
    181: "pop-rock", 182: "folk", 183: "pop-rock", 184: "pop-rock",
    185: "música urbana", 186: "música urbana", 187: "cançó autor",
    188: "pop-rock", 189: "cançó autor", 190: "folk", 191: "folk",
    192: "cançó autor", 193: "folk", 194: "pop-rock", 195: "folk",
    196: "pop-rock", 197: "folk", 198: "cançó autor", 199: "pop-rock",
    200: "música urbana", 201: "folk", 202: "pop-rock", 203: "pop-rock",
    204: "cançó autor", 205: "folk", 206: "rumba", 207: "folk",
    208: "cançó autor", 209: "pop-rock", 210: "cançó autor", 211: "cançó autor",
    212: "cançó autor", 213: "folk", 214: "folk", 215: "folk",
    216: "pop-rock", 217: "folk", 218: "pop-rock", 219: "folk",
    220: "folk", 221: "cançó autor", 222: "cançó autor", 223: "pop-rock",
    224: "pop-rock", 225: "folk", 226: "pop-rock", 227: "pop-rock",
    228: "pop-rock", 229: "folk", 230: "cançó autor", 231: "pop-rock",
    232: "folk", 233: "folk", 234: "pop-rock", 235: "cançó autor",
    236: "pop-rock", 237: "folk", 238: "pop-rock", 239: "folk",
    240: "folk", 241: "havanera", 242: "cançó autor", 243: "folk",
    244: "folk", 245: "música urbana", 246: "pop-rock", 247: "música urbana",
    248: "folk", 249: "rumba", 250: "folk", 251: "pop-rock",
    252: "pop-rock", 253: "cançó autor", 254: "folk", 255: "pop-rock",
    256: "cançó autor", 257: "folk", 258: "folk", 259: "folk",
    260: "folk", 261: "folk", 262: "folk", 263: "pop-rock",
    264: "cançó autor", 265: "pop-rock", 266: "pop-rock", 267: "pop-rock",
    268: "cançó autor", 269: "cançó autor", 270: "folk", 271: "cançó autor",
    272: "folk", 273: "pop-rock", 274: "folk", 275: "música urbana",
    276: "folk", 277: "folk", 278: "pop-rock", 279: "pop-rock",
    280: "cançó autor", 281: "pop-rock", 282: "folk", 283: "pop-rock",
    284: "pop-rock", 285: "música urbana", 286: "cançó autor",
    287: "pop-rock", 288: "folk", 289: "música urbana", 290: "pop-rock",
    291: "cançó autor", 292: "folk", 293: "pop-rock", 294: "pop-rock",
    295: "cançó autor", 296: "cançó autor", 297: "folk",
    298: "pop-rock", 299: "folk", 300: "pop-rock", 301: "pop-rock",
    302: "música urbana", 303: "folk", 304: "pop-rock", 305: "cançó autor",
    306: "folk", 307: "folk", 308: "música urbana", 309: "cançó autor",
    310: "cançó autor", 311: "cançó autor", 312: "música urbana", 313: "folk",
    314: "havanera", 315: "pop-rock", 316: "folk", 317: "cançó autor",
    318: "cançó autor", 319: "folk", 320: "folk", 321: "pop-rock",
    322: "folk", 323: "cançó autor", 324: "pop-rock", 325: "cançó autor",
    326: "pop-rock", 327: "pop-rock", 328: "pop-rock", 329: "pop-rock",
    330: "pop-rock", 331: "cançó autor", 332: "cançó autor", 333: "pop-rock",
    334: "folk", 335: "pop-rock", 336: "havanera", 337: "pop-rock",
    338: "música urbana", 339: "cançó autor", 340: "pop-rock",
    341: "cançó autor", 342: "pop-rock", 343: "pop-rock", 344: "pop-rock",
    345: "pop-rock", 346: "pop-rock", 347: "pop-rock", 348: "pop-rock",
    349: "folk", 350: "pop-rock", 351: "folk", 352: "cançó autor",
    353: "pop-rock", 354: "folk", 355: "pop-rock", 356: "pop-rock",
    357: "folk", 358: "música urbana", 359: "música urbana", 360: "pop-rock",
    361: "folk", 362: "cançó autor", 363: "cançó autor", 364: "cançó autor",
    365: "pop-rock", 366: "pop-rock", 367: "pop-rock", 368: "pop-rock",
    369: "folk", 370: "folk", 371: "cançó autor", 372: "pop-rock",
    373: "pop-rock", 374: "pop-rock", 375: "cançó autor", 376: "cançó autor",
    377: "folk", 378: "música urbana", 379: "pop-rock", 380: "pop-rock",
    381: "folk", 382: "cançó autor", 383: "cançó autor", 384: "pop-rock",
    385: "pop-rock", 386: "folk", 387: "cançó autor", 388: "cançó autor",
    389: "cançó autor", 390: "pop-rock", 391: "folk", 392: "cançó autor",
    393: "rumba", 394: "cançó autor", 395: "pop-rock", 396: "folk",
    397: "folk", 398: "pop-rock", 399: "folk", 400: "pop-rock",
    401: "cançó autor", 402: "pop-rock", 403: "folk", 404: "havanera",
    405: "cançó autor", 406: "folk", 407: "folk", 408: "pop-rock",
    409: "folk", 410: "pop-rock", 411: "folk", 412: "cançó autor",
    413: "música urbana", 414: "folk", 415: "cançó autor", 416: "folk",
    417: "folk", 418: "folk", 419: "cançó autor", 420: "cançó autor",
    421: "pop-rock", 422: "folk", 423: "folk", 424: "pop-rock",
    425: "música urbana", 426: "folk", 427: "cançó autor", 428: "cançó autor",
    429: "pop-rock", 430: "folk", 431: "pop-rock", 432: "pop-rock",
    433: "folk", 434: "cançó autor", 435: "música urbana", 436: "folk",
    437: "folk", 438: "pop-rock", 439: "cançó autor", 440: "cançó autor",
    441: "folk", 442: "música urbana", 443: "folk", 444: "pop-rock",
    445: "folk", 446: "música urbana", 447: "folk", 448: "folk",
    449: "cançó autor", 450: "cançó autor", 451: "pop-rock", 452: "folk",
    453: "pop-rock", 454: "folk", 455: "folk", 456: "pop-rock",
    457: "pop-rock", 458: "cançó autor", 459: "cançó autor", 460: "pop-rock",
    461: "pop-rock", 462: "pop-rock", 463: "pop-rock", 464: "folk",
    465: "folk", 466: "cançó autor", 467: "pop-rock", 468: "havanera",
    469: "música urbana", 470: "folk", 471: "pop-rock", 472: "folk",
    473: "pop-rock", 474: "folk", 475: "folk", 476: "folk",
    477: "pop-rock", 478: "folk", 479: "pop-rock", 480: "pop-rock",
    481: "folk", 482: "folk", 483: "folk", 484: "pop-rock",
    485: "pop-rock", 486: "cançó autor", 487: "folk", 488: "folk",
    489: "cançó autor", 490: "havanera", 491: "pop-rock", 492: "folk",
    493: "folk", 494: "folk", 495: "folk", 496: "pop-rock",
    497: "pop-rock", 498: "folk", 499: "pop-rock", 500: "cançó autor",
}

ALLOWED = {"folk", "cançó autor", "pop-rock", "rumba", "havanera", "música urbana"}
assert len(GENRES) == 500
assert set(GENRES.keys()) == set(range(1, 501))
assert set(GENRES.values()).issubset(ALLOWED), set(GENRES.values()) - ALLOWED

with SRC.open("r", encoding="utf-8-sig", newline="") as f_in, \
     DST.open("w", encoding="utf-8", newline="") as f_out:
    reader = csv.reader(f_in)
    writer = csv.writer(f_out)
    header = next(reader)
    writer.writerow(header + ["genre"])
    for row in reader:
        idx = int(row[0])
        writer.writerow(row + [GENRES[idx]])

print(f"wrote {DST}")
# Quick distribution check
from collections import Counter
print(Counter(GENRES.values()).most_common())
