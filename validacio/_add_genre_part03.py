"""Add a manually-assigned `genre` column to top_5000_songs_part03.csv.

Classification of each of the 500 songs (#1001-1500) into one of:
{folk, cançó autor, pop-rock, rumba, havanera, música urbana}

Same criteria as part01/part02:
- cançó autor: nova cançó & singer-songwriter tradition + musical-theatre songwriting
- pop-rock: Catalan/Valencian/Balearic pop & rock bands; modern indie-pop
- folk: traditional songs, nadales, sardanes cantades, cançons infantils-folk,
  cançó tradicional (Botifarra, Música Nostra, Al Tall, Uc, Esquirols-trad…)
- rumba: rumba catalana (Peret, Los Manolos, Xitxarel·los, La Troba Kung-Fú,
  La Pegatina "Gat rumberu"…)
- havanera: maritime habanera tradition (Port Bo, Pescadors, Sons de mar, Clara,
  Humus, Musicants, *La gavina*, *El meu avi*…)
- música urbana: rap / trap / reggaetón / urban-pop / dancehall / reggae
  (Naina, The Tyets, Figa Flawas, Mama Dousha, Carles Caselles, Orxata, Adala,
  Bad Gyal, Yung Rajola, Mak & Sak, Mushkaa, Baya Baye, Lágrimas de Sangre,
  Romàntic Dimoni, Zoo, enMatu, FADES, La Clika, Vinnie Kairos, Groggy Rude,
  Ven'nus, Socunbohemio…)
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "top_5000_songs_part03.csv"
DST = HERE / "top_5000_songs_part03_genre.csv"

GENRES = {
    1001: "havanera", 1002: "folk", 1003: "cançó autor", 1004: "folk",
    1005: "música urbana", 1006: "cançó autor", 1007: "pop-rock", 1008: "pop-rock",
    1009: "cançó autor", 1010: "folk", 1011: "cançó autor", 1012: "cançó autor",
    1013: "folk", 1014: "cançó autor", 1015: "pop-rock", 1016: "folk",
    1017: "pop-rock", 1018: "folk", 1019: "pop-rock", 1020: "folk",
    1021: "pop-rock", 1022: "folk", 1023: "folk", 1024: "pop-rock",
    1025: "música urbana", 1026: "folk", 1027: "cançó autor", 1028: "pop-rock",
    1029: "pop-rock", 1030: "pop-rock", 1031: "cançó autor", 1032: "havanera",
    1033: "folk", 1034: "folk", 1035: "folk", 1036: "pop-rock",
    1037: "folk", 1038: "folk", 1039: "folk", 1040: "pop-rock",
    1041: "folk", 1042: "pop-rock", 1043: "cançó autor", 1044: "cançó autor",
    1045: "folk", 1046: "pop-rock", 1047: "folk", 1048: "pop-rock",
    1049: "música urbana", 1050: "folk", 1051: "pop-rock", 1052: "havanera",
    1053: "música urbana", 1054: "música urbana", 1055: "música urbana",
    1056: "cançó autor", 1057: "cançó autor", 1058: "folk", 1059: "pop-rock",
    1060: "pop-rock", 1061: "pop-rock", 1062: "pop-rock", 1063: "cançó autor",
    1064: "pop-rock", 1065: "pop-rock", 1066: "música urbana", 1067: "cançó autor",
    1068: "música urbana", 1069: "folk", 1070: "folk", 1071: "cançó autor",
    1072: "havanera", 1073: "pop-rock", 1074: "pop-rock", 1075: "folk",
    1076: "folk", 1077: "folk", 1078: "folk", 1079: "pop-rock",
    1080: "cançó autor", 1081: "cançó autor", 1082: "pop-rock", 1083: "folk",
    1084: "música urbana", 1085: "folk", 1086: "música urbana", 1087: "folk",
    1088: "música urbana", 1089: "folk", 1090: "cançó autor", 1091: "folk",
    1092: "música urbana", 1093: "cançó autor", 1094: "folk", 1095: "cançó autor",
    1096: "folk", 1097: "cançó autor", 1098: "folk", 1099: "folk",
    1100: "cançó autor", 1101: "pop-rock", 1102: "pop-rock", 1103: "pop-rock",
    1104: "folk", 1105: "folk", 1106: "rumba", 1107: "pop-rock",
    1108: "cançó autor", 1109: "música urbana", 1110: "pop-rock", 1111: "folk",
    1112: "pop-rock", 1113: "música urbana", 1114: "rumba", 1115: "cançó autor",
    1116: "folk", 1117: "pop-rock", 1118: "cançó autor", 1119: "pop-rock",
    1120: "pop-rock", 1121: "cançó autor", 1122: "cançó autor", 1123: "folk",
    1124: "folk", 1125: "folk", 1126: "música urbana", 1127: "pop-rock",
    1128: "música urbana", 1129: "folk", 1130: "folk", 1131: "cançó autor",
    1132: "pop-rock", 1133: "cançó autor", 1134: "cançó autor", 1135: "pop-rock",
    1136: "cançó autor", 1137: "folk", 1138: "cançó autor", 1139: "pop-rock",
    1140: "música urbana", 1141: "cançó autor", 1142: "cançó autor", 1143: "cançó autor",
    1144: "folk", 1145: "folk", 1146: "folk", 1147: "folk",
    1148: "cançó autor", 1149: "música urbana", 1150: "cançó autor", 1151: "folk",
    1152: "pop-rock", 1153: "folk", 1154: "pop-rock", 1155: "pop-rock",
    1156: "folk", 1157: "pop-rock", 1158: "folk", 1159: "pop-rock",
    1160: "folk", 1161: "música urbana", 1162: "cançó autor", 1163: "música urbana",
    1164: "cançó autor", 1165: "cançó autor", 1166: "folk", 1167: "pop-rock",
    1168: "folk", 1169: "cançó autor", 1170: "pop-rock", 1171: "folk",
    1172: "folk", 1173: "pop-rock", 1174: "folk", 1175: "folk",
    1176: "cançó autor", 1177: "cançó autor", 1178: "folk", 1179: "música urbana",
    1180: "folk", 1181: "folk", 1182: "folk", 1183: "folk",
    1184: "cançó autor", 1185: "cançó autor", 1186: "pop-rock", 1187: "pop-rock",
    1188: "pop-rock", 1189: "pop-rock", 1190: "folk", 1191: "cançó autor",
    1192: "música urbana", 1193: "pop-rock", 1194: "pop-rock", 1195: "folk",
    1196: "pop-rock", 1197: "folk", 1198: "pop-rock", 1199: "folk",
    1200: "música urbana", 1201: "pop-rock", 1202: "folk", 1203: "folk",
    1204: "folk", 1205: "pop-rock", 1206: "folk", 1207: "música urbana",
    1208: "rumba", 1209: "folk", 1210: "cançó autor", 1211: "pop-rock",
    1212: "folk", 1213: "folk", 1214: "cançó autor", 1215: "folk",
    1216: "cançó autor", 1217: "folk", 1218: "cançó autor", 1219: "pop-rock",
    1220: "folk", 1221: "folk", 1222: "cançó autor", 1223: "havanera",
    1224: "pop-rock", 1225: "cançó autor", 1226: "pop-rock", 1227: "cançó autor",
    1228: "folk", 1229: "pop-rock", 1230: "pop-rock", 1231: "pop-rock",
    1232: "música urbana", 1233: "pop-rock", 1234: "pop-rock", 1235: "pop-rock",
    1236: "pop-rock", 1237: "folk", 1238: "cançó autor", 1239: "folk",
    1240: "pop-rock", 1241: "cançó autor", 1242: "música urbana", 1243: "música urbana",
    1244: "folk", 1245: "cançó autor", 1246: "cançó autor", 1247: "música urbana",
    1248: "folk", 1249: "cançó autor", 1250: "pop-rock", 1251: "cançó autor",
    1252: "música urbana", 1253: "música urbana", 1254: "pop-rock", 1255: "folk",
    1256: "folk", 1257: "pop-rock", 1258: "folk", 1259: "pop-rock",
    1260: "pop-rock", 1261: "pop-rock", 1262: "folk", 1263: "folk",
    1264: "folk", 1265: "folk", 1266: "havanera", 1267: "cançó autor",
    1268: "cançó autor", 1269: "pop-rock", 1270: "pop-rock", 1271: "pop-rock",
    1272: "folk", 1273: "folk", 1274: "pop-rock", 1275: "música urbana",
    1276: "pop-rock", 1277: "folk", 1278: "música urbana", 1279: "música urbana",
    1280: "folk", 1281: "música urbana", 1282: "folk", 1283: "pop-rock",
    1284: "cançó autor", 1285: "folk", 1286: "folk", 1287: "música urbana",
    1288: "folk", 1289: "pop-rock", 1290: "folk", 1291: "folk",
    1292: "cançó autor", 1293: "cançó autor", 1294: "música urbana", 1295: "folk",
    1296: "folk", 1297: "pop-rock", 1298: "pop-rock", 1299: "folk",
    1300: "folk", 1301: "pop-rock", 1302: "cançó autor", 1303: "cançó autor",
    1304: "pop-rock", 1305: "cançó autor", 1306: "folk", 1307: "cançó autor",
    1308: "pop-rock", 1309: "pop-rock", 1310: "cançó autor", 1311: "pop-rock",
    1312: "folk", 1313: "folk", 1314: "pop-rock", 1315: "pop-rock",
    1316: "pop-rock", 1317: "pop-rock", 1318: "pop-rock", 1319: "folk",
    1320: "folk", 1321: "cançó autor", 1322: "cançó autor", 1323: "folk",
    1324: "pop-rock", 1325: "pop-rock", 1326: "folk", 1327: "folk",
    1328: "folk", 1329: "pop-rock", 1330: "pop-rock", 1331: "cançó autor",
    1332: "pop-rock", 1333: "folk", 1334: "cançó autor", 1335: "pop-rock",
    1336: "cançó autor", 1337: "pop-rock", 1338: "cançó autor", 1339: "folk",
    1340: "cançó autor", 1341: "cançó autor", 1342: "música urbana", 1343: "cançó autor",
    1344: "folk", 1345: "folk", 1346: "cançó autor", 1347: "pop-rock",
    1348: "folk", 1349: "pop-rock", 1350: "pop-rock", 1351: "folk",
    1352: "folk", 1353: "pop-rock", 1354: "pop-rock", 1355: "folk",
    1356: "cançó autor", 1357: "cançó autor", 1358: "pop-rock", 1359: "cançó autor",
    1360: "folk", 1361: "folk", 1362: "pop-rock", 1363: "música urbana",
    1364: "folk", 1365: "pop-rock", 1366: "folk", 1367: "cançó autor",
    1368: "cançó autor", 1369: "pop-rock", 1370: "pop-rock", 1371: "cançó autor",
    1372: "pop-rock", 1373: "cançó autor", 1374: "pop-rock", 1375: "cançó autor",
    1376: "pop-rock", 1377: "música urbana", 1378: "pop-rock", 1379: "cançó autor",
    1380: "cançó autor", 1381: "folk", 1382: "pop-rock", 1383: "havanera",
    1384: "folk", 1385: "folk", 1386: "música urbana", 1387: "cançó autor",
    1388: "folk", 1389: "música urbana", 1390: "folk", 1391: "cançó autor",
    1392: "folk", 1393: "pop-rock", 1394: "música urbana", 1395: "cançó autor",
    1396: "folk", 1397: "cançó autor", 1398: "cançó autor", 1399: "folk",
    1400: "cançó autor", 1401: "música urbana", 1402: "folk", 1403: "cançó autor",
    1404: "folk", 1405: "pop-rock", 1406: "folk", 1407: "cançó autor",
    1408: "pop-rock", 1409: "cançó autor", 1410: "cançó autor", 1411: "folk",
    1412: "folk", 1413: "cançó autor", 1414: "pop-rock", 1415: "folk",
    1416: "cançó autor", 1417: "folk", 1418: "folk", 1419: "folk",
    1420: "folk", 1421: "cançó autor", 1422: "pop-rock", 1423: "música urbana",
    1424: "música urbana", 1425: "música urbana", 1426: "pop-rock", 1427: "pop-rock",
    1428: "música urbana", 1429: "cançó autor", 1430: "música urbana", 1431: "folk",
    1432: "pop-rock", 1433: "pop-rock", 1434: "pop-rock", 1435: "cançó autor",
    1436: "pop-rock", 1437: "pop-rock", 1438: "cançó autor", 1439: "pop-rock",
    1440: "folk", 1441: "pop-rock", 1442: "folk", 1443: "folk",
    1444: "pop-rock", 1445: "pop-rock", 1446: "folk", 1447: "pop-rock",
    1448: "pop-rock", 1449: "folk", 1450: "folk", 1451: "folk",
    1452: "cançó autor", 1453: "pop-rock", 1454: "cançó autor", 1455: "música urbana",
    1456: "folk", 1457: "pop-rock", 1458: "cançó autor", 1459: "pop-rock",
    1460: "música urbana", 1461: "folk", 1462: "rumba", 1463: "cançó autor",
    1464: "pop-rock", 1465: "cançó autor", 1466: "cançó autor", 1467: "folk",
    1468: "folk", 1469: "música urbana", 1470: "pop-rock", 1471: "pop-rock",
    1472: "pop-rock", 1473: "folk", 1474: "pop-rock", 1475: "pop-rock",
    1476: "folk", 1477: "folk", 1478: "folk", 1479: "folk",
    1480: "cançó autor", 1481: "cançó autor", 1482: "cançó autor", 1483: "cançó autor",
    1484: "cançó autor", 1485: "folk", 1486: "cançó autor", 1487: "rumba",
    1488: "folk", 1489: "pop-rock", 1490: "cançó autor", 1491: "pop-rock",
    1492: "cançó autor", 1493: "música urbana", 1494: "folk", 1495: "cançó autor",
    1496: "música urbana", 1497: "folk", 1498: "folk", 1499: "cançó autor",
    1500: "música urbana",
}

ALLOWED = {"folk", "cançó autor", "pop-rock", "rumba", "havanera", "música urbana"}
assert len(GENRES) == 500
assert set(GENRES.keys()) == set(range(1001, 1501))
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
from collections import Counter
print(Counter(GENRES.values()).most_common())
