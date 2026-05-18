"""Add a manually-assigned `genre` column to top_5000_songs_part07.csv.

Classification of each of the 500 songs (#3001-3500) into one of:
{folk, cançó autor, pop-rock, rumba, havanera, música urbana}

Same criteria as part01-06.
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "top_5000_songs_part07.csv"
DST = HERE / "top_5000_songs_part07_genre.csv"

GENRES = {
    3001: "pop-rock", 3002: "folk", 3003: "folk", 3004: "música urbana",
    3005: "folk", 3006: "cançó autor", 3007: "folk", 3008: "rumba",
    3009: "pop-rock", 3010: "folk", 3011: "pop-rock", 3012: "pop-rock",
    3013: "cançó autor", 3014: "folk", 3015: "folk", 3016: "pop-rock",
    3017: "folk", 3018: "folk", 3019: "cançó autor", 3020: "pop-rock",
    3021: "pop-rock", 3022: "folk", 3023: "rumba", 3024: "folk",
    3025: "folk", 3026: "música urbana", 3027: "folk", 3028: "cançó autor",
    3029: "pop-rock", 3030: "cançó autor", 3031: "pop-rock", 3032: "folk",
    3033: "pop-rock", 3034: "cançó autor", 3035: "pop-rock", 3036: "pop-rock",
    3037: "pop-rock", 3038: "cançó autor", 3039: "folk", 3040: "pop-rock",
    3041: "cançó autor", 3042: "pop-rock", 3043: "cançó autor", 3044: "música urbana",
    3045: "cançó autor", 3046: "pop-rock", 3047: "música urbana", 3048: "pop-rock",
    3049: "pop-rock", 3050: "folk", 3051: "pop-rock", 3052: "cançó autor",
    3053: "pop-rock", 3054: "pop-rock", 3055: "cançó autor", 3056: "pop-rock",
    3057: "folk", 3058: "folk", 3059: "folk", 3060: "pop-rock",
    3061: "rumba", 3062: "cançó autor", 3063: "pop-rock", 3064: "cançó autor",
    3065: "folk", 3066: "folk", 3067: "pop-rock", 3068: "cançó autor",
    3069: "pop-rock", 3070: "música urbana", 3071: "pop-rock", 3072: "pop-rock",
    3073: "cançó autor", 3074: "pop-rock", 3075: "folk", 3076: "cançó autor",
    3077: "cançó autor", 3078: "cançó autor", 3079: "folk", 3080: "cançó autor",
    3081: "música urbana", 3082: "cançó autor", 3083: "pop-rock", 3084: "pop-rock",
    3085: "cançó autor", 3086: "cançó autor", 3087: "folk", 3088: "folk",
    3089: "cançó autor", 3090: "pop-rock", 3091: "cançó autor", 3092: "cançó autor",
    3093: "pop-rock", 3094: "música urbana", 3095: "pop-rock", 3096: "cançó autor",
    3097: "cançó autor", 3098: "cançó autor", 3099: "cançó autor", 3100: "cançó autor",
    3101: "folk", 3102: "folk", 3103: "folk", 3104: "pop-rock",
    3105: "pop-rock", 3106: "pop-rock", 3107: "pop-rock", 3108: "cançó autor",
    3109: "pop-rock", 3110: "pop-rock", 3111: "pop-rock", 3112: "música urbana",
    3113: "música urbana", 3114: "folk", 3115: "folk", 3116: "pop-rock",
    3117: "pop-rock", 3118: "pop-rock", 3119: "folk", 3120: "cançó autor",
    3121: "cançó autor", 3122: "cançó autor", 3123: "folk", 3124: "cançó autor",
    3125: "pop-rock", 3126: "folk", 3127: "folk", 3128: "pop-rock",
    3129: "pop-rock", 3130: "folk", 3131: "cançó autor", 3132: "cançó autor",
    3133: "cançó autor", 3134: "pop-rock", 3135: "pop-rock", 3136: "cançó autor",
    3137: "pop-rock", 3138: "pop-rock", 3139: "pop-rock", 3140: "folk",
    3141: "folk", 3142: "cançó autor", 3143: "música urbana", 3144: "cançó autor",
    3145: "havanera", 3146: "música urbana", 3147: "pop-rock", 3148: "cançó autor",
    3149: "folk", 3150: "pop-rock", 3151: "cançó autor", 3152: "folk",
    3153: "pop-rock", 3154: "cançó autor", 3155: "folk", 3156: "pop-rock",
    3157: "música urbana", 3158: "pop-rock", 3159: "havanera", 3160: "cançó autor",
    3161: "folk", 3162: "cançó autor", 3163: "folk", 3164: "pop-rock",
    3165: "folk", 3166: "cançó autor", 3167: "pop-rock", 3168: "havanera",
    3169: "cançó autor", 3170: "pop-rock", 3171: "música urbana", 3172: "cançó autor",
    3173: "pop-rock", 3174: "folk", 3175: "cançó autor", 3176: "folk",
    3177: "folk", 3178: "cançó autor", 3179: "cançó autor", 3180: "folk",
    3181: "havanera", 3182: "pop-rock", 3183: "pop-rock", 3184: "cançó autor",
    3185: "música urbana", 3186: "havanera", 3187: "folk", 3188: "cançó autor",
    3189: "cançó autor", 3190: "folk", 3191: "folk", 3192: "folk",
    3193: "pop-rock", 3194: "folk", 3195: "música urbana", 3196: "pop-rock",
    3197: "folk", 3198: "pop-rock", 3199: "pop-rock", 3200: "folk",
    3201: "cançó autor", 3202: "cançó autor", 3203: "cançó autor", 3204: "cançó autor",
    3205: "folk", 3206: "pop-rock", 3207: "folk", 3208: "cançó autor",
    3209: "pop-rock", 3210: "folk", 3211: "cançó autor", 3212: "folk",
    3213: "folk", 3214: "cançó autor", 3215: "pop-rock", 3216: "folk",
    3217: "folk", 3218: "folk", 3219: "havanera", 3220: "folk",
    3221: "cançó autor", 3222: "cançó autor", 3223: "folk", 3224: "cançó autor",
    3225: "cançó autor", 3226: "cançó autor", 3227: "pop-rock", 3228: "pop-rock",
    3229: "pop-rock", 3230: "pop-rock", 3231: "folk", 3232: "folk",
    3233: "pop-rock", 3234: "música urbana", 3235: "folk", 3236: "folk",
    3237: "folk", 3238: "pop-rock", 3239: "cançó autor", 3240: "pop-rock",
    3241: "pop-rock", 3242: "cançó autor", 3243: "música urbana", 3244: "pop-rock",
    3245: "havanera", 3246: "folk", 3247: "cançó autor", 3248: "folk",
    3249: "pop-rock", 3250: "cançó autor", 3251: "folk", 3252: "folk",
    3253: "pop-rock", 3254: "pop-rock", 3255: "pop-rock", 3256: "folk",
    3257: "pop-rock", 3258: "pop-rock", 3259: "folk", 3260: "cançó autor",
    3261: "cançó autor", 3262: "música urbana", 3263: "folk", 3264: "folk",
    3265: "folk", 3266: "pop-rock", 3267: "folk", 3268: "cançó autor",
    3269: "folk", 3270: "folk", 3271: "pop-rock", 3272: "cançó autor",
    3273: "cançó autor", 3274: "folk", 3275: "folk", 3276: "cançó autor",
    3277: "folk", 3278: "música urbana", 3279: "pop-rock", 3280: "cançó autor",
    3281: "cançó autor", 3282: "pop-rock", 3283: "cançó autor", 3284: "cançó autor",
    3285: "cançó autor", 3286: "folk", 3287: "pop-rock", 3288: "folk",
    3289: "cançó autor", 3290: "havanera", 3291: "folk", 3292: "pop-rock",
    3293: "folk", 3294: "folk", 3295: "folk", 3296: "cançó autor",
    3297: "pop-rock", 3298: "folk", 3299: "cançó autor", 3300: "folk",
    3301: "música urbana", 3302: "pop-rock", 3303: "pop-rock", 3304: "pop-rock",
    3305: "folk", 3306: "cançó autor", 3307: "pop-rock", 3308: "pop-rock",
    3309: "cançó autor", 3310: "pop-rock", 3311: "cançó autor", 3312: "pop-rock",
    3313: "cançó autor", 3314: "cançó autor", 3315: "folk", 3316: "pop-rock",
    3317: "folk", 3318: "cançó autor", 3319: "folk", 3320: "cançó autor",
    3321: "cançó autor", 3322: "cançó autor", 3323: "folk", 3324: "folk",
    3325: "folk", 3326: "folk", 3327: "pop-rock", 3328: "pop-rock",
    3329: "cançó autor", 3330: "cançó autor", 3331: "cançó autor", 3332: "música urbana",
    3333: "cançó autor", 3334: "folk", 3335: "cançó autor", 3336: "folk",
    3337: "folk", 3338: "havanera", 3339: "pop-rock", 3340: "pop-rock",
    3341: "pop-rock", 3342: "folk", 3343: "cançó autor", 3344: "folk",
    3345: "cançó autor", 3346: "música urbana", 3347: "cançó autor", 3348: "folk",
    3349: "pop-rock", 3350: "pop-rock", 3351: "folk", 3352: "pop-rock",
    3353: "pop-rock", 3354: "cançó autor", 3355: "folk", 3356: "cançó autor",
    3357: "folk", 3358: "pop-rock", 3359: "folk", 3360: "folk",
    3361: "cançó autor", 3362: "folk", 3363: "pop-rock", 3364: "folk",
    3365: "folk", 3366: "música urbana", 3367: "cançó autor", 3368: "pop-rock",
    3369: "folk", 3370: "música urbana", 3371: "folk", 3372: "folk",
    3373: "pop-rock", 3374: "pop-rock", 3375: "folk", 3376: "pop-rock",
    3377: "cançó autor", 3378: "pop-rock", 3379: "pop-rock", 3380: "cançó autor",
    3381: "folk", 3382: "pop-rock", 3383: "folk", 3384: "cançó autor",
    3385: "folk", 3386: "cançó autor", 3387: "folk", 3388: "folk",
    3389: "pop-rock", 3390: "folk", 3391: "cançó autor", 3392: "cançó autor",
    3393: "pop-rock", 3394: "folk", 3395: "folk", 3396: "pop-rock",
    3397: "cançó autor", 3398: "pop-rock", 3399: "folk", 3400: "cançó autor",
    3401: "folk", 3402: "cançó autor", 3403: "cançó autor", 3404: "cançó autor",
    3405: "pop-rock", 3406: "cançó autor", 3407: "pop-rock", 3408: "pop-rock",
    3409: "pop-rock", 3410: "cançó autor", 3411: "pop-rock", 3412: "pop-rock",
    3413: "pop-rock", 3414: "cançó autor", 3415: "cançó autor", 3416: "música urbana",
    3417: "pop-rock", 3418: "cançó autor", 3419: "cançó autor", 3420: "pop-rock",
    3421: "música urbana", 3422: "cançó autor", 3423: "folk", 3424: "folk",
    3425: "pop-rock", 3426: "pop-rock", 3427: "cançó autor", 3428: "cançó autor",
    3429: "havanera", 3430: "pop-rock", 3431: "música urbana", 3432: "pop-rock",
    3433: "cançó autor", 3434: "cançó autor", 3435: "folk", 3436: "cançó autor",
    3437: "cançó autor", 3438: "pop-rock", 3439: "pop-rock", 3440: "cançó autor",
    3441: "música urbana", 3442: "cançó autor", 3443: "folk", 3444: "cançó autor",
    3445: "folk", 3446: "música urbana", 3447: "cançó autor", 3448: "cançó autor",
    3449: "cançó autor", 3450: "pop-rock", 3451: "pop-rock", 3452: "folk",
    3453: "cançó autor", 3454: "folk", 3455: "cançó autor", 3456: "cançó autor",
    3457: "música urbana", 3458: "folk", 3459: "pop-rock", 3460: "cançó autor",
    3461: "música urbana", 3462: "pop-rock", 3463: "cançó autor", 3464: "pop-rock",
    3465: "folk", 3466: "música urbana", 3467: "folk", 3468: "havanera",
    3469: "música urbana", 3470: "cançó autor", 3471: "cançó autor", 3472: "folk",
    3473: "cançó autor", 3474: "havanera", 3475: "folk", 3476: "pop-rock",
    3477: "cançó autor", 3478: "música urbana", 3479: "pop-rock", 3480: "folk",
    3481: "folk", 3482: "pop-rock", 3483: "folk", 3484: "havanera",
    3485: "folk", 3486: "folk", 3487: "pop-rock", 3488: "cançó autor",
    3489: "cançó autor", 3490: "pop-rock", 3491: "cançó autor", 3492: "pop-rock",
    3493: "pop-rock", 3494: "folk", 3495: "cançó autor", 3496: "pop-rock",
    3497: "folk", 3498: "música urbana", 3499: "música urbana", 3500: "cançó autor",
}

ALLOWED = {"folk", "cançó autor", "pop-rock", "rumba", "havanera", "música urbana"}
assert len(GENRES) == 500
assert set(GENRES.keys()) == set(range(3001, 3501))
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
