"""Add a manually-assigned `genre` column to top_5000_songs_part06.csv.

Classification of each of the 500 songs (#2501-3000) into one of:
{folk, cançó autor, pop-rock, rumba, havanera, música urbana}

Same criteria as part01-05.
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "top_5000_songs_part06.csv"
DST = HERE / "top_5000_songs_part06_genre.csv"

GENRES = {
    2501: "pop-rock", 2502: "cançó autor", 2503: "pop-rock", 2504: "pop-rock",
    2505: "pop-rock", 2506: "cançó autor", 2507: "folk", 2508: "cançó autor",
    2509: "pop-rock", 2510: "pop-rock", 2511: "cançó autor", 2512: "pop-rock",
    2513: "cançó autor", 2514: "cançó autor", 2515: "cançó autor", 2516: "pop-rock",
    2517: "pop-rock", 2518: "pop-rock", 2519: "pop-rock", 2520: "pop-rock",
    2521: "música urbana", 2522: "cançó autor", 2523: "música urbana", 2524: "pop-rock",
    2525: "pop-rock", 2526: "pop-rock", 2527: "cançó autor", 2528: "folk",
    2529: "folk", 2530: "folk", 2531: "pop-rock", 2532: "cançó autor",
    2533: "folk", 2534: "cançó autor", 2535: "cançó autor", 2536: "cançó autor",
    2537: "folk", 2538: "cançó autor", 2539: "música urbana", 2540: "pop-rock",
    2541: "pop-rock", 2542: "cançó autor", 2543: "pop-rock", 2544: "folk",
    2545: "cançó autor", 2546: "folk", 2547: "pop-rock", 2548: "música urbana",
    2549: "pop-rock", 2550: "folk", 2551: "folk", 2552: "cançó autor",
    2553: "música urbana", 2554: "cançó autor", 2555: "pop-rock", 2556: "pop-rock",
    2557: "folk", 2558: "pop-rock", 2559: "folk", 2560: "folk",
    2561: "havanera", 2562: "música urbana", 2563: "cançó autor", 2564: "cançó autor",
    2565: "folk", 2566: "pop-rock", 2567: "folk", 2568: "folk",
    2569: "música urbana", 2570: "folk", 2571: "cançó autor", 2572: "cançó autor",
    2573: "pop-rock", 2574: "cançó autor", 2575: "folk", 2576: "folk",
    2577: "cançó autor", 2578: "cançó autor", 2579: "folk", 2580: "pop-rock",
    2581: "folk", 2582: "pop-rock", 2583: "folk", 2584: "cançó autor",
    2585: "folk", 2586: "pop-rock", 2587: "pop-rock", 2588: "pop-rock",
    2589: "pop-rock", 2590: "folk", 2591: "folk", 2592: "pop-rock",
    2593: "cançó autor", 2594: "folk", 2595: "música urbana", 2596: "folk",
    2597: "folk", 2598: "cançó autor", 2599: "pop-rock", 2600: "pop-rock",
    2601: "pop-rock", 2602: "cançó autor", 2603: "pop-rock", 2604: "pop-rock",
    2605: "folk", 2606: "pop-rock", 2607: "folk", 2608: "cançó autor",
    2609: "folk", 2610: "cançó autor", 2611: "pop-rock", 2612: "pop-rock",
    2613: "pop-rock", 2614: "folk", 2615: "pop-rock", 2616: "pop-rock",
    2617: "cançó autor", 2618: "pop-rock", 2619: "cançó autor", 2620: "folk",
    2621: "folk", 2622: "pop-rock", 2623: "pop-rock", 2624: "pop-rock",
    2625: "música urbana", 2626: "pop-rock", 2627: "folk", 2628: "música urbana",
    2629: "pop-rock", 2630: "pop-rock", 2631: "música urbana", 2632: "cançó autor",
    2633: "cançó autor", 2634: "folk", 2635: "pop-rock", 2636: "pop-rock",
    2637: "cançó autor", 2638: "pop-rock", 2639: "folk", 2640: "pop-rock",
    2641: "folk", 2642: "cançó autor", 2643: "pop-rock", 2644: "cançó autor",
    2645: "havanera", 2646: "pop-rock", 2647: "cançó autor", 2648: "pop-rock",
    2649: "folk", 2650: "música urbana", 2651: "cançó autor", 2652: "cançó autor",
    2653: "cançó autor", 2654: "folk", 2655: "folk", 2656: "cançó autor",
    2657: "folk", 2658: "cançó autor", 2659: "pop-rock", 2660: "cançó autor",
    2661: "pop-rock", 2662: "folk", 2663: "cançó autor", 2664: "pop-rock",
    2665: "pop-rock", 2666: "folk", 2667: "música urbana", 2668: "cançó autor",
    2669: "pop-rock", 2670: "pop-rock", 2671: "música urbana", 2672: "cançó autor",
    2673: "pop-rock", 2674: "folk", 2675: "cançó autor", 2676: "pop-rock",
    2677: "folk", 2678: "pop-rock", 2679: "pop-rock", 2680: "pop-rock",
    2681: "folk", 2682: "pop-rock", 2683: "cançó autor", 2684: "pop-rock",
    2685: "pop-rock", 2686: "pop-rock", 2687: "pop-rock", 2688: "cançó autor",
    2689: "folk", 2690: "pop-rock", 2691: "folk", 2692: "pop-rock",
    2693: "cançó autor", 2694: "pop-rock", 2695: "folk", 2696: "pop-rock",
    2697: "pop-rock", 2698: "cançó autor", 2699: "folk", 2700: "pop-rock",
    2701: "pop-rock", 2702: "pop-rock", 2703: "pop-rock", 2704: "cançó autor",
    2705: "pop-rock", 2706: "pop-rock", 2707: "pop-rock", 2708: "folk",
    2709: "pop-rock", 2710: "folk", 2711: "folk", 2712: "pop-rock",
    2713: "cançó autor", 2714: "cançó autor", 2715: "folk", 2716: "pop-rock",
    2717: "folk", 2718: "folk", 2719: "pop-rock", 2720: "cançó autor",
    2721: "pop-rock", 2722: "rumba", 2723: "cançó autor", 2724: "cançó autor",
    2725: "folk", 2726: "cançó autor", 2727: "folk", 2728: "folk",
    2729: "folk", 2730: "pop-rock", 2731: "folk", 2732: "folk",
    2733: "pop-rock", 2734: "pop-rock", 2735: "folk", 2736: "pop-rock",
    2737: "pop-rock", 2738: "pop-rock", 2739: "pop-rock", 2740: "folk",
    2741: "cançó autor", 2742: "música urbana", 2743: "folk", 2744: "folk",
    2745: "pop-rock", 2746: "pop-rock", 2747: "pop-rock", 2748: "cançó autor",
    2749: "folk", 2750: "cançó autor", 2751: "pop-rock", 2752: "pop-rock",
    2753: "pop-rock", 2754: "folk", 2755: "pop-rock", 2756: "música urbana",
    2757: "música urbana", 2758: "cançó autor", 2759: "cançó autor", 2760: "cançó autor",
    2761: "folk", 2762: "pop-rock", 2763: "cançó autor", 2764: "cançó autor",
    2765: "folk", 2766: "folk", 2767: "folk", 2768: "pop-rock",
    2769: "folk", 2770: "música urbana", 2771: "folk", 2772: "folk",
    2773: "cançó autor", 2774: "folk", 2775: "folk", 2776: "pop-rock",
    2777: "folk", 2778: "pop-rock", 2779: "folk", 2780: "cançó autor",
    2781: "folk", 2782: "cançó autor", 2783: "música urbana", 2784: "folk",
    2785: "pop-rock", 2786: "folk", 2787: "folk", 2788: "pop-rock",
    2789: "rumba", 2790: "pop-rock", 2791: "pop-rock", 2792: "pop-rock",
    2793: "cançó autor", 2794: "folk", 2795: "cançó autor", 2796: "folk",
    2797: "cançó autor", 2798: "pop-rock", 2799: "pop-rock", 2800: "pop-rock",
    2801: "cançó autor", 2802: "pop-rock", 2803: "folk", 2804: "pop-rock",
    2805: "folk", 2806: "cançó autor", 2807: "folk", 2808: "pop-rock",
    2809: "cançó autor", 2810: "música urbana", 2811: "pop-rock", 2812: "folk",
    2813: "cançó autor", 2814: "pop-rock", 2815: "folk", 2816: "pop-rock",
    2817: "folk", 2818: "havanera", 2819: "música urbana", 2820: "pop-rock",
    2821: "folk", 2822: "pop-rock", 2823: "cançó autor", 2824: "cançó autor",
    2825: "cançó autor", 2826: "folk", 2827: "cançó autor", 2828: "folk",
    2829: "cançó autor", 2830: "folk", 2831: "cançó autor", 2832: "pop-rock",
    2833: "cançó autor", 2834: "cançó autor", 2835: "pop-rock", 2836: "cançó autor",
    2837: "folk", 2838: "cançó autor", 2839: "pop-rock", 2840: "pop-rock",
    2841: "pop-rock", 2842: "cançó autor", 2843: "cançó autor", 2844: "cançó autor",
    2845: "pop-rock", 2846: "cançó autor", 2847: "pop-rock", 2848: "cançó autor",
    2849: "música urbana", 2850: "pop-rock", 2851: "folk", 2852: "pop-rock",
    2853: "cançó autor", 2854: "cançó autor", 2855: "cançó autor", 2856: "cançó autor",
    2857: "pop-rock", 2858: "pop-rock", 2859: "pop-rock", 2860: "cançó autor",
    2861: "folk", 2862: "pop-rock", 2863: "havanera", 2864: "cançó autor",
    2865: "pop-rock", 2866: "cançó autor", 2867: "folk", 2868: "música urbana",
    2869: "pop-rock", 2870: "folk", 2871: "música urbana", 2872: "cançó autor",
    2873: "música urbana", 2874: "pop-rock", 2875: "pop-rock", 2876: "folk",
    2877: "folk", 2878: "folk", 2879: "rumba", 2880: "cançó autor",
    2881: "folk", 2882: "pop-rock", 2883: "folk", 2884: "folk",
    2885: "pop-rock", 2886: "pop-rock", 2887: "folk", 2888: "pop-rock",
    2889: "cançó autor", 2890: "folk", 2891: "folk", 2892: "pop-rock",
    2893: "cançó autor", 2894: "folk", 2895: "folk", 2896: "cançó autor",
    2897: "cançó autor", 2898: "havanera", 2899: "cançó autor", 2900: "pop-rock",
    2901: "folk", 2902: "folk", 2903: "música urbana", 2904: "pop-rock",
    2905: "cançó autor", 2906: "folk", 2907: "folk", 2908: "pop-rock",
    2909: "cançó autor", 2910: "música urbana", 2911: "pop-rock", 2912: "folk",
    2913: "folk", 2914: "pop-rock", 2915: "pop-rock", 2916: "folk",
    2917: "música urbana", 2918: "pop-rock", 2919: "música urbana", 2920: "folk",
    2921: "cançó autor", 2922: "folk", 2923: "folk", 2924: "folk",
    2925: "cançó autor", 2926: "folk", 2927: "folk", 2928: "folk",
    2929: "música urbana", 2930: "cançó autor", 2931: "cançó autor", 2932: "pop-rock",
    2933: "folk", 2934: "pop-rock", 2935: "cançó autor", 2936: "pop-rock",
    2937: "folk", 2938: "folk", 2939: "música urbana", 2940: "pop-rock",
    2941: "cançó autor", 2942: "folk", 2943: "folk", 2944: "pop-rock",
    2945: "folk", 2946: "cançó autor", 2947: "cançó autor", 2948: "folk",
    2949: "cançó autor", 2950: "folk", 2951: "cançó autor", 2952: "cançó autor",
    2953: "folk", 2954: "pop-rock", 2955: "cançó autor", 2956: "cançó autor",
    2957: "cançó autor", 2958: "música urbana", 2959: "pop-rock", 2960: "cançó autor",
    2961: "cançó autor", 2962: "cançó autor", 2963: "pop-rock", 2964: "cançó autor",
    2965: "folk", 2966: "pop-rock", 2967: "pop-rock", 2968: "folk",
    2969: "pop-rock", 2970: "música urbana", 2971: "cançó autor", 2972: "folk",
    2973: "folk", 2974: "folk", 2975: "cançó autor", 2976: "folk",
    2977: "pop-rock", 2978: "folk", 2979: "pop-rock", 2980: "pop-rock",
    2981: "havanera", 2982: "folk", 2983: "pop-rock", 2984: "folk",
    2985: "pop-rock", 2986: "cançó autor", 2987: "pop-rock", 2988: "pop-rock",
    2989: "folk", 2990: "folk", 2991: "pop-rock", 2992: "folk",
    2993: "cançó autor", 2994: "folk", 2995: "folk", 2996: "folk",
    2997: "cançó autor", 2998: "pop-rock", 2999: "folk", 3000: "pop-rock",
}

ALLOWED = {"folk", "cançó autor", "pop-rock", "rumba", "havanera", "música urbana"}
assert len(GENRES) == 500
assert set(GENRES.keys()) == set(range(2501, 3001))
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
