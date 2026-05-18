"""Add a manually-assigned `genre` column to top_5000_songs_part04.csv.

Classification of each of the 500 songs (#1501-2000) into one of:
{folk, cançó autor, pop-rock, rumba, havanera, música urbana}

Same criteria as part01-03.
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "top_5000_songs_part04.csv"
DST = HERE / "top_5000_songs_part04_genre.csv"

GENRES = {
    1501: "música urbana", 1502: "folk", 1503: "havanera", 1504: "cançó autor",
    1505: "folk", 1506: "folk", 1507: "pop-rock", 1508: "pop-rock",
    1509: "pop-rock", 1510: "folk", 1511: "música urbana", 1512: "folk",
    1513: "cançó autor", 1514: "cançó autor", 1515: "folk", 1516: "pop-rock",
    1517: "folk", 1518: "folk", 1519: "cançó autor", 1520: "música urbana",
    1521: "cançó autor", 1522: "pop-rock", 1523: "folk", 1524: "folk",
    1525: "pop-rock", 1526: "pop-rock", 1527: "cançó autor", 1528: "música urbana",
    1529: "música urbana", 1530: "folk", 1531: "folk", 1532: "folk",
    1533: "folk", 1534: "folk", 1535: "pop-rock", 1536: "pop-rock",
    1537: "folk", 1538: "pop-rock", 1539: "pop-rock", 1540: "pop-rock",
    1541: "folk", 1542: "cançó autor", 1543: "folk", 1544: "pop-rock",
    1545: "pop-rock", 1546: "pop-rock", 1547: "pop-rock", 1548: "pop-rock",
    1549: "cançó autor", 1550: "pop-rock", 1551: "folk", 1552: "havanera",
    1553: "folk", 1554: "pop-rock", 1555: "folk", 1556: "folk",
    1557: "cançó autor", 1558: "folk", 1559: "folk", 1560: "pop-rock",
    1561: "pop-rock", 1562: "pop-rock", 1563: "pop-rock", 1564: "havanera",
    1565: "pop-rock", 1566: "cançó autor", 1567: "havanera", 1568: "cançó autor",
    1569: "pop-rock", 1570: "cançó autor", 1571: "cançó autor", 1572: "pop-rock",
    1573: "pop-rock", 1574: "cançó autor", 1575: "pop-rock", 1576: "folk",
    1577: "música urbana", 1578: "pop-rock", 1579: "folk", 1580: "pop-rock",
    1581: "folk", 1582: "pop-rock", 1583: "pop-rock", 1584: "pop-rock",
    1585: "pop-rock", 1586: "música urbana", 1587: "música urbana", 1588: "música urbana",
    1589: "pop-rock", 1590: "folk", 1591: "cançó autor", 1592: "folk",
    1593: "cançó autor", 1594: "folk", 1595: "folk", 1596: "cançó autor",
    1597: "cançó autor", 1598: "pop-rock", 1599: "pop-rock", 1600: "música urbana",
    1601: "folk", 1602: "folk", 1603: "folk", 1604: "folk",
    1605: "pop-rock", 1606: "folk", 1607: "cançó autor", 1608: "pop-rock",
    1609: "folk", 1610: "pop-rock", 1611: "pop-rock", 1612: "folk",
    1613: "folk", 1614: "pop-rock", 1615: "folk", 1616: "música urbana",
    1617: "cançó autor", 1618: "cançó autor", 1619: "cançó autor", 1620: "folk",
    1621: "música urbana", 1622: "folk", 1623: "pop-rock", 1624: "cançó autor",
    1625: "cançó autor", 1626: "havanera", 1627: "pop-rock", 1628: "folk",
    1629: "folk", 1630: "pop-rock", 1631: "pop-rock", 1632: "pop-rock",
    1633: "folk", 1634: "música urbana", 1635: "cançó autor", 1636: "rumba",
    1637: "cançó autor", 1638: "música urbana", 1639: "pop-rock", 1640: "pop-rock",
    1641: "folk", 1642: "cançó autor", 1643: "cançó autor", 1644: "pop-rock",
    1645: "cançó autor", 1646: "pop-rock", 1647: "cançó autor", 1648: "folk",
    1649: "pop-rock", 1650: "música urbana", 1651: "folk", 1652: "pop-rock",
    1653: "folk", 1654: "folk", 1655: "folk", 1656: "pop-rock",
    1657: "pop-rock", 1658: "pop-rock", 1659: "folk", 1660: "folk",
    1661: "música urbana", 1662: "pop-rock", 1663: "cançó autor", 1664: "folk",
    1665: "folk", 1666: "pop-rock", 1667: "pop-rock", 1668: "folk",
    1669: "pop-rock", 1670: "pop-rock", 1671: "música urbana", 1672: "havanera",
    1673: "música urbana", 1674: "cançó autor", 1675: "folk", 1676: "pop-rock",
    1677: "folk", 1678: "folk", 1679: "pop-rock", 1680: "folk",
    1681: "folk", 1682: "pop-rock", 1683: "pop-rock", 1684: "pop-rock",
    1685: "pop-rock", 1686: "folk", 1687: "folk", 1688: "folk",
    1689: "pop-rock", 1690: "folk", 1691: "folk", 1692: "pop-rock",
    1693: "pop-rock", 1694: "folk", 1695: "folk", 1696: "pop-rock",
    1697: "pop-rock", 1698: "folk", 1699: "folk", 1700: "pop-rock",
    1701: "pop-rock", 1702: "música urbana", 1703: "pop-rock", 1704: "folk",
    1705: "folk", 1706: "cançó autor", 1707: "pop-rock", 1708: "pop-rock",
    1709: "folk", 1710: "folk", 1711: "pop-rock", 1712: "cançó autor",
    1713: "rumba", 1714: "cançó autor", 1715: "folk", 1716: "cançó autor",
    1717: "música urbana", 1718: "música urbana", 1719: "pop-rock", 1720: "cançó autor",
    1721: "cançó autor", 1722: "pop-rock", 1723: "cançó autor", 1724: "pop-rock",
    1725: "folk", 1726: "pop-rock", 1727: "música urbana", 1728: "pop-rock",
    1729: "folk", 1730: "pop-rock", 1731: "folk", 1732: "folk",
    1733: "pop-rock", 1734: "cançó autor", 1735: "cançó autor", 1736: "música urbana",
    1737: "folk", 1738: "pop-rock", 1739: "folk", 1740: "cançó autor",
    1741: "folk", 1742: "pop-rock", 1743: "pop-rock", 1744: "pop-rock",
    1745: "pop-rock", 1746: "folk", 1747: "pop-rock", 1748: "folk",
    1749: "música urbana", 1750: "pop-rock", 1751: "cançó autor", 1752: "pop-rock",
    1753: "música urbana", 1754: "pop-rock", 1755: "pop-rock", 1756: "pop-rock",
    1757: "folk", 1758: "pop-rock", 1759: "pop-rock", 1760: "pop-rock",
    1761: "cançó autor", 1762: "cançó autor", 1763: "pop-rock", 1764: "pop-rock",
    1765: "música urbana", 1766: "pop-rock", 1767: "cançó autor", 1768: "cançó autor",
    1769: "pop-rock", 1770: "folk", 1771: "pop-rock", 1772: "cançó autor",
    1773: "cançó autor", 1774: "folk", 1775: "folk", 1776: "pop-rock",
    1777: "pop-rock", 1778: "pop-rock", 1779: "cançó autor", 1780: "folk",
    1781: "pop-rock", 1782: "música urbana", 1783: "pop-rock", 1784: "folk",
    1785: "cançó autor", 1786: "pop-rock", 1787: "cançó autor", 1788: "pop-rock",
    1789: "cançó autor", 1790: "pop-rock", 1791: "pop-rock", 1792: "pop-rock",
    1793: "música urbana", 1794: "folk", 1795: "pop-rock", 1796: "folk",
    1797: "folk", 1798: "pop-rock", 1799: "pop-rock", 1800: "música urbana",
    1801: "música urbana", 1802: "folk", 1803: "pop-rock", 1804: "pop-rock",
    1805: "cançó autor", 1806: "folk", 1807: "música urbana", 1808: "folk",
    1809: "folk", 1810: "folk", 1811: "cançó autor", 1812: "música urbana",
    1813: "folk", 1814: "cançó autor", 1815: "folk", 1816: "rumba",
    1817: "folk", 1818: "folk", 1819: "folk", 1820: "cançó autor",
    1821: "folk", 1822: "cançó autor", 1823: "música urbana", 1824: "cançó autor",
    1825: "pop-rock", 1826: "folk", 1827: "cançó autor", 1828: "folk",
    1829: "pop-rock", 1830: "cançó autor", 1831: "cançó autor", 1832: "folk",
    1833: "música urbana", 1834: "pop-rock", 1835: "cançó autor", 1836: "folk",
    1837: "pop-rock", 1838: "folk", 1839: "folk", 1840: "pop-rock",
    1841: "pop-rock", 1842: "folk", 1843: "havanera", 1844: "cançó autor",
    1845: "folk", 1846: "pop-rock", 1847: "pop-rock", 1848: "cançó autor",
    1849: "cançó autor", 1850: "cançó autor", 1851: "pop-rock", 1852: "folk",
    1853: "música urbana", 1854: "folk", 1855: "folk", 1856: "música urbana",
    1857: "pop-rock", 1858: "folk", 1859: "pop-rock", 1860: "cançó autor",
    1861: "pop-rock", 1862: "pop-rock", 1863: "folk", 1864: "folk",
    1865: "pop-rock", 1866: "pop-rock", 1867: "rumba", 1868: "pop-rock",
    1869: "pop-rock", 1870: "folk", 1871: "cançó autor", 1872: "folk",
    1873: "cançó autor", 1874: "pop-rock", 1875: "folk", 1876: "cançó autor",
    1877: "cançó autor", 1878: "folk", 1879: "pop-rock", 1880: "pop-rock",
    1881: "folk", 1882: "cançó autor", 1883: "cançó autor", 1884: "pop-rock",
    1885: "pop-rock", 1886: "folk", 1887: "pop-rock", 1888: "música urbana",
    1889: "cançó autor", 1890: "cançó autor", 1891: "folk", 1892: "música urbana",
    1893: "cançó autor", 1894: "folk", 1895: "cançó autor", 1896: "cançó autor",
    1897: "folk", 1898: "música urbana", 1899: "pop-rock", 1900: "pop-rock",
    1901: "música urbana", 1902: "música urbana", 1903: "pop-rock", 1904: "folk",
    1905: "folk", 1906: "folk", 1907: "folk", 1908: "folk",
    1909: "rumba", 1910: "pop-rock", 1911: "cançó autor", 1912: "pop-rock",
    1913: "pop-rock", 1914: "cançó autor", 1915: "cançó autor", 1916: "folk",
    1917: "folk", 1918: "folk", 1919: "cançó autor", 1920: "folk",
    1921: "folk", 1922: "pop-rock", 1923: "cançó autor", 1924: "pop-rock",
    1925: "cançó autor", 1926: "cançó autor", 1927: "pop-rock", 1928: "cançó autor",
    1929: "cançó autor", 1930: "música urbana", 1931: "cançó autor", 1932: "pop-rock",
    1933: "cançó autor", 1934: "pop-rock", 1935: "pop-rock", 1936: "pop-rock",
    1937: "cançó autor", 1938: "pop-rock", 1939: "pop-rock", 1940: "cançó autor",
    1941: "cançó autor", 1942: "pop-rock", 1943: "música urbana", 1944: "pop-rock",
    1945: "música urbana", 1946: "música urbana", 1947: "pop-rock", 1948: "folk",
    1949: "cançó autor", 1950: "música urbana", 1951: "cançó autor", 1952: "cançó autor",
    1953: "folk", 1954: "folk", 1955: "havanera", 1956: "cançó autor",
    1957: "pop-rock", 1958: "folk", 1959: "pop-rock", 1960: "pop-rock",
    1961: "havanera", 1962: "folk", 1963: "folk", 1964: "folk",
    1965: "pop-rock", 1966: "cançó autor", 1967: "cançó autor", 1968: "pop-rock",
    1969: "folk", 1970: "rumba", 1971: "pop-rock", 1972: "folk",
    1973: "cançó autor", 1974: "folk", 1975: "folk", 1976: "folk",
    1977: "cançó autor", 1978: "folk", 1979: "pop-rock", 1980: "cançó autor",
    1981: "pop-rock", 1982: "cançó autor", 1983: "folk", 1984: "folk",
    1985: "pop-rock", 1986: "folk", 1987: "pop-rock", 1988: "folk",
    1989: "pop-rock", 1990: "música urbana", 1991: "pop-rock", 1992: "folk",
    1993: "rumba", 1994: "cançó autor", 1995: "folk", 1996: "cançó autor",
    1997: "música urbana", 1998: "cançó autor", 1999: "folk", 2000: "folk",
}

ALLOWED = {"folk", "cançó autor", "pop-rock", "rumba", "havanera", "música urbana"}
assert len(GENRES) == 500
assert set(GENRES.keys()) == set(range(1501, 2001))
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
