"""Add a manually-assigned `genre` column to top_5000_songs_part05.csv.

Classification of each of the 500 songs (#2001-2500) into one of:
{folk, cançó autor, pop-rock, rumba, havanera, música urbana}

Same criteria as part01-04. Notably: JULS treated as música urbana
(per user feedback) except the title-explicit havaneres.
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "top_5000_songs_part05.csv"
DST = HERE / "top_5000_songs_part05_genre.csv"

GENRES = {
    2001: "folk", 2002: "cançó autor", 2003: "folk", 2004: "folk",
    2005: "havanera", 2006: "pop-rock", 2007: "cançó autor", 2008: "cançó autor",
    2009: "cançó autor", 2010: "folk", 2011: "folk", 2012: "música urbana",
    2013: "folk", 2014: "cançó autor", 2015: "rumba", 2016: "pop-rock",
    2017: "cançó autor", 2018: "cançó autor", 2019: "folk", 2020: "folk",
    2021: "folk", 2022: "folk", 2023: "cançó autor", 2024: "cançó autor",
    2025: "cançó autor", 2026: "música urbana", 2027: "cançó autor", 2028: "folk",
    2029: "rumba", 2030: "folk", 2031: "folk", 2032: "folk",
    2033: "pop-rock", 2034: "pop-rock", 2035: "folk", 2036: "cançó autor",
    2037: "folk", 2038: "pop-rock", 2039: "pop-rock", 2040: "música urbana",
    2041: "cançó autor", 2042: "folk", 2043: "cançó autor", 2044: "cançó autor",
    2045: "folk", 2046: "havanera", 2047: "pop-rock", 2048: "cançó autor",
    2049: "pop-rock", 2050: "pop-rock", 2051: "pop-rock", 2052: "cançó autor",
    2053: "pop-rock", 2054: "pop-rock", 2055: "cançó autor", 2056: "pop-rock",
    2057: "folk", 2058: "música urbana", 2059: "folk", 2060: "folk",
    2061: "cançó autor", 2062: "pop-rock", 2063: "pop-rock", 2064: "pop-rock",
    2065: "cançó autor", 2066: "música urbana", 2067: "folk", 2068: "pop-rock",
    2069: "pop-rock", 2070: "pop-rock", 2071: "pop-rock", 2072: "cançó autor",
    2073: "pop-rock", 2074: "folk", 2075: "pop-rock", 2076: "cançó autor",
    2077: "cançó autor", 2078: "folk", 2079: "folk", 2080: "cançó autor",
    2081: "cançó autor", 2082: "pop-rock", 2083: "folk", 2084: "folk",
    2085: "folk", 2086: "folk", 2087: "pop-rock", 2088: "folk",
    2089: "folk", 2090: "folk", 2091: "pop-rock", 2092: "música urbana",
    2093: "pop-rock", 2094: "pop-rock", 2095: "pop-rock", 2096: "cançó autor",
    2097: "folk", 2098: "cançó autor", 2099: "cançó autor", 2100: "folk",
    2101: "música urbana", 2102: "pop-rock", 2103: "cançó autor", 2104: "pop-rock",
    2105: "pop-rock", 2106: "folk", 2107: "folk", 2108: "rumba",
    2109: "pop-rock", 2110: "pop-rock", 2111: "rumba", 2112: "pop-rock",
    2113: "pop-rock", 2114: "pop-rock", 2115: "folk", 2116: "cançó autor",
    2117: "pop-rock", 2118: "folk", 2119: "cançó autor", 2120: "cançó autor",
    2121: "cançó autor", 2122: "música urbana", 2123: "cançó autor", 2124: "folk",
    2125: "folk", 2126: "folk", 2127: "pop-rock", 2128: "cançó autor",
    2129: "folk", 2130: "folk", 2131: "pop-rock", 2132: "havanera",
    2133: "pop-rock", 2134: "cançó autor", 2135: "folk", 2136: "cançó autor",
    2137: "música urbana", 2138: "folk", 2139: "folk", 2140: "pop-rock",
    2141: "pop-rock", 2142: "pop-rock", 2143: "havanera", 2144: "pop-rock",
    2145: "pop-rock", 2146: "cançó autor", 2147: "pop-rock", 2148: "pop-rock",
    2149: "cançó autor", 2150: "folk", 2151: "pop-rock", 2152: "música urbana",
    2153: "havanera", 2154: "pop-rock", 2155: "folk", 2156: "folk",
    2157: "folk", 2158: "cançó autor", 2159: "cançó autor", 2160: "música urbana",
    2161: "rumba", 2162: "pop-rock", 2163: "folk", 2164: "pop-rock",
    2165: "folk", 2166: "pop-rock", 2167: "pop-rock", 2168: "folk",
    2169: "pop-rock", 2170: "pop-rock", 2171: "folk", 2172: "folk",
    2173: "folk", 2174: "pop-rock", 2175: "cançó autor", 2176: "cançó autor",
    2177: "pop-rock", 2178: "cançó autor", 2179: "havanera", 2180: "folk",
    2181: "cançó autor", 2182: "pop-rock", 2183: "pop-rock", 2184: "pop-rock",
    2185: "pop-rock", 2186: "pop-rock", 2187: "pop-rock", 2188: "música urbana",
    2189: "folk", 2190: "folk", 2191: "cançó autor", 2192: "cançó autor",
    2193: "folk", 2194: "folk", 2195: "folk", 2196: "cançó autor",
    2197: "folk", 2198: "cançó autor", 2199: "música urbana", 2200: "cançó autor",
    2201: "música urbana", 2202: "música urbana", 2203: "pop-rock", 2204: "cançó autor",
    2205: "pop-rock", 2206: "havanera", 2207: "folk", 2208: "pop-rock",
    2209: "pop-rock", 2210: "pop-rock", 2211: "folk", 2212: "cançó autor",
    2213: "folk", 2214: "folk", 2215: "cançó autor", 2216: "folk",
    2217: "pop-rock", 2218: "cançó autor", 2219: "folk", 2220: "pop-rock",
    2221: "cançó autor", 2222: "cançó autor", 2223: "folk", 2224: "folk",
    2225: "folk", 2226: "cançó autor", 2227: "pop-rock", 2228: "folk",
    2229: "pop-rock", 2230: "pop-rock", 2231: "folk", 2232: "folk",
    2233: "cançó autor", 2234: "folk", 2235: "cançó autor", 2236: "pop-rock",
    2237: "folk", 2238: "folk", 2239: "pop-rock", 2240: "pop-rock",
    2241: "folk", 2242: "pop-rock", 2243: "música urbana", 2244: "pop-rock",
    2245: "pop-rock", 2246: "pop-rock", 2247: "pop-rock", 2248: "folk",
    2249: "pop-rock", 2250: "pop-rock", 2251: "pop-rock", 2252: "cançó autor",
    2253: "pop-rock", 2254: "pop-rock", 2255: "cançó autor", 2256: "cançó autor",
    2257: "folk", 2258: "pop-rock", 2259: "pop-rock", 2260: "cançó autor",
    2261: "folk", 2262: "pop-rock", 2263: "pop-rock", 2264: "pop-rock",
    2265: "pop-rock", 2266: "folk", 2267: "folk", 2268: "cançó autor",
    2269: "pop-rock", 2270: "cançó autor", 2271: "folk", 2272: "folk",
    2273: "pop-rock", 2274: "pop-rock", 2275: "cançó autor", 2276: "folk",
    2277: "pop-rock", 2278: "folk", 2279: "cançó autor", 2280: "folk",
    2281: "pop-rock", 2282: "folk", 2283: "cançó autor", 2284: "cançó autor",
    2285: "folk", 2286: "folk", 2287: "música urbana", 2288: "pop-rock",
    2289: "música urbana", 2290: "cançó autor", 2291: "cançó autor", 2292: "rumba",
    2293: "pop-rock", 2294: "pop-rock", 2295: "folk", 2296: "pop-rock",
    2297: "música urbana", 2298: "pop-rock", 2299: "pop-rock", 2300: "folk",
    2301: "música urbana", 2302: "pop-rock", 2303: "pop-rock", 2304: "cançó autor",
    2305: "cançó autor", 2306: "cançó autor", 2307: "pop-rock", 2308: "pop-rock",
    2309: "folk", 2310: "folk", 2311: "folk", 2312: "cançó autor",
    2313: "música urbana", 2314: "folk", 2315: "folk", 2316: "cançó autor",
    2317: "cançó autor", 2318: "pop-rock", 2319: "música urbana", 2320: "música urbana",
    2321: "folk", 2322: "cançó autor", 2323: "folk", 2324: "folk",
    2325: "folk", 2326: "pop-rock", 2327: "cançó autor", 2328: "pop-rock",
    2329: "cançó autor", 2330: "folk", 2331: "cançó autor", 2332: "folk",
    2333: "cançó autor", 2334: "pop-rock", 2335: "pop-rock", 2336: "folk",
    2337: "folk", 2338: "pop-rock", 2339: "folk", 2340: "pop-rock",
    2341: "cançó autor", 2342: "cançó autor", 2343: "cançó autor", 2344: "pop-rock",
    2345: "cançó autor", 2346: "cançó autor", 2347: "rumba", 2348: "pop-rock",
    2349: "cançó autor", 2350: "folk", 2351: "pop-rock", 2352: "folk",
    2353: "folk", 2354: "folk", 2355: "pop-rock", 2356: "cançó autor",
    2357: "cançó autor", 2358: "cançó autor", 2359: "pop-rock", 2360: "cançó autor",
    2361: "pop-rock", 2362: "pop-rock", 2363: "cançó autor", 2364: "folk",
    2365: "rumba", 2366: "pop-rock", 2367: "cançó autor", 2368: "folk",
    2369: "música urbana", 2370: "pop-rock", 2371: "folk", 2372: "pop-rock",
    2373: "pop-rock", 2374: "pop-rock", 2375: "folk", 2376: "folk",
    2377: "folk", 2378: "havanera", 2379: "pop-rock", 2380: "folk",
    2381: "havanera", 2382: "música urbana", 2383: "folk", 2384: "folk",
    2385: "folk", 2386: "folk", 2387: "cançó autor", 2388: "pop-rock",
    2389: "pop-rock", 2390: "folk", 2391: "pop-rock", 2392: "cançó autor",
    2393: "pop-rock", 2394: "folk", 2395: "cançó autor", 2396: "pop-rock",
    2397: "pop-rock", 2398: "folk", 2399: "havanera", 2400: "pop-rock",
    2401: "pop-rock", 2402: "cançó autor", 2403: "pop-rock", 2404: "folk",
    2405: "folk", 2406: "pop-rock", 2407: "cançó autor", 2408: "folk",
    2409: "folk", 2410: "folk", 2411: "folk", 2412: "havanera",
    2413: "cançó autor", 2414: "folk", 2415: "cançó autor", 2416: "pop-rock",
    2417: "folk", 2418: "folk", 2419: "cançó autor", 2420: "cançó autor",
    2421: "pop-rock", 2422: "cançó autor", 2423: "música urbana", 2424: "folk",
    2425: "cançó autor", 2426: "pop-rock", 2427: "cançó autor", 2428: "folk",
    2429: "pop-rock", 2430: "música urbana", 2431: "folk", 2432: "rumba",
    2433: "folk", 2434: "folk", 2435: "pop-rock", 2436: "pop-rock",
    2437: "folk", 2438: "pop-rock", 2439: "folk", 2440: "música urbana",
    2441: "cançó autor", 2442: "música urbana", 2443: "pop-rock", 2444: "pop-rock",
    2445: "pop-rock", 2446: "pop-rock", 2447: "música urbana", 2448: "pop-rock",
    2449: "música urbana", 2450: "pop-rock", 2451: "folk", 2452: "pop-rock",
    2453: "cançó autor", 2454: "pop-rock", 2455: "cançó autor", 2456: "folk",
    2457: "folk", 2458: "folk", 2459: "cançó autor", 2460: "cançó autor",
    2461: "havanera", 2462: "cançó autor", 2463: "cançó autor", 2464: "cançó autor",
    2465: "cançó autor", 2466: "pop-rock", 2467: "cançó autor", 2468: "pop-rock",
    2469: "cançó autor", 2470: "pop-rock", 2471: "pop-rock", 2472: "cançó autor",
    2473: "pop-rock", 2474: "cançó autor", 2475: "folk", 2476: "pop-rock",
    2477: "folk", 2478: "folk", 2479: "cançó autor", 2480: "folk",
    2481: "folk", 2482: "pop-rock", 2483: "folk", 2484: "cançó autor",
    2485: "pop-rock", 2486: "pop-rock", 2487: "música urbana", 2488: "pop-rock",
    2489: "pop-rock", 2490: "folk", 2491: "pop-rock", 2492: "pop-rock",
    2493: "pop-rock", 2494: "folk", 2495: "pop-rock", 2496: "rumba",
    2497: "folk", 2498: "pop-rock", 2499: "pop-rock", 2500: "pop-rock",
}

ALLOWED = {"folk", "cançó autor", "pop-rock", "rumba", "havanera", "música urbana"}
assert len(GENRES) == 500
assert set(GENRES.keys()) == set(range(2001, 2501))
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
