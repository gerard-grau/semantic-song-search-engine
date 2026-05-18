"""Add a manually-assigned `genre` column to top_5000_songs_part08.csv.

Classification of each of the 500 songs (#3501-4000) into one of:
{folk, cançó autor, pop-rock, rumba, havanera, música urbana}

Same criteria as part01-07.
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "top_5000_songs_part08.csv"
DST = HERE / "top_5000_songs_part08_genre.csv"

GENRES = {
    3501: "cançó autor", 3502: "cançó autor", 3503: "pop-rock", 3504: "pop-rock",
    3505: "cançó autor", 3506: "cançó autor", 3507: "folk", 3508: "cançó autor",
    3509: "pop-rock", 3510: "folk", 3511: "folk", 3512: "música urbana",
    3513: "cançó autor", 3514: "cançó autor", 3515: "cançó autor", 3516: "cançó autor",
    3517: "pop-rock", 3518: "cançó autor", 3519: "pop-rock", 3520: "folk",
    3521: "pop-rock", 3522: "folk", 3523: "folk", 3524: "cançó autor",
    3525: "música urbana", 3526: "cançó autor", 3527: "rumba", 3528: "cançó autor",
    3529: "cançó autor", 3530: "pop-rock", 3531: "pop-rock", 3532: "cançó autor",
    3533: "folk", 3534: "folk", 3535: "cançó autor", 3536: "pop-rock",
    3537: "folk", 3538: "rumba", 3539: "folk", 3540: "pop-rock",
    3541: "folk", 3542: "folk", 3543: "cançó autor", 3544: "folk",
    3545: "cançó autor", 3546: "música urbana", 3547: "cançó autor", 3548: "folk",
    3549: "folk", 3550: "cançó autor", 3551: "música urbana", 3552: "música urbana",
    3553: "folk", 3554: "pop-rock", 3555: "pop-rock", 3556: "pop-rock",
    3557: "pop-rock", 3558: "pop-rock", 3559: "rumba", 3560: "pop-rock",
    3561: "folk", 3562: "pop-rock", 3563: "pop-rock", 3564: "cançó autor",
    3565: "pop-rock", 3566: "cançó autor", 3567: "música urbana", 3568: "folk",
    3569: "pop-rock", 3570: "cançó autor", 3571: "pop-rock", 3572: "folk",
    3573: "cançó autor", 3574: "folk", 3575: "pop-rock", 3576: "pop-rock",
    3577: "pop-rock", 3578: "cançó autor", 3579: "folk", 3580: "cançó autor",
    3581: "folk", 3582: "pop-rock", 3583: "cançó autor", 3584: "cançó autor",
    3585: "pop-rock", 3586: "música urbana", 3587: "música urbana", 3588: "folk",
    3589: "cançó autor", 3590: "folk", 3591: "cançó autor", 3592: "folk",
    3593: "pop-rock", 3594: "folk", 3595: "cançó autor", 3596: "música urbana",
    3597: "cançó autor", 3598: "cançó autor", 3599: "folk", 3600: "pop-rock",
    3601: "folk", 3602: "pop-rock", 3603: "folk", 3604: "folk",
    3605: "folk", 3606: "pop-rock", 3607: "folk", 3608: "folk",
    3609: "folk", 3610: "cançó autor", 3611: "pop-rock", 3612: "pop-rock",
    3613: "cançó autor", 3614: "pop-rock", 3615: "cançó autor", 3616: "folk",
    3617: "pop-rock", 3618: "folk", 3619: "folk", 3620: "cançó autor",
    3621: "cançó autor", 3622: "folk", 3623: "folk", 3624: "cançó autor",
    3625: "pop-rock", 3626: "pop-rock", 3627: "folk", 3628: "pop-rock",
    3629: "folk", 3630: "pop-rock", 3631: "cançó autor", 3632: "música urbana",
    3633: "pop-rock", 3634: "pop-rock", 3635: "rumba", 3636: "folk",
    3637: "cançó autor", 3638: "folk", 3639: "música urbana", 3640: "pop-rock",
    3641: "música urbana", 3642: "folk", 3643: "pop-rock", 3644: "pop-rock",
    3645: "pop-rock", 3646: "pop-rock", 3647: "folk", 3648: "folk",
    3649: "cançó autor", 3650: "pop-rock", 3651: "folk", 3652: "pop-rock",
    3653: "folk", 3654: "cançó autor", 3655: "folk", 3656: "folk",
    3657: "pop-rock", 3658: "cançó autor", 3659: "folk", 3660: "cançó autor",
    3661: "pop-rock", 3662: "pop-rock", 3663: "cançó autor", 3664: "pop-rock",
    3665: "cançó autor", 3666: "pop-rock", 3667: "pop-rock", 3668: "cançó autor",
    3669: "folk", 3670: "pop-rock", 3671: "pop-rock", 3672: "pop-rock",
    3673: "pop-rock", 3674: "folk", 3675: "folk", 3676: "cançó autor",
    3677: "cançó autor", 3678: "cançó autor", 3679: "cançó autor", 3680: "folk",
    3681: "música urbana", 3682: "folk", 3683: "cançó autor", 3684: "cançó autor",
    3685: "pop-rock", 3686: "pop-rock", 3687: "cançó autor", 3688: "cançó autor",
    3689: "pop-rock", 3690: "folk", 3691: "cançó autor", 3692: "pop-rock",
    3693: "cançó autor", 3694: "pop-rock", 3695: "pop-rock", 3696: "pop-rock",
    3697: "cançó autor", 3698: "cançó autor", 3699: "pop-rock", 3700: "pop-rock",
    3701: "folk", 3702: "música urbana", 3703: "pop-rock", 3704: "folk",
    3705: "pop-rock", 3706: "pop-rock", 3707: "música urbana", 3708: "pop-rock",
    3709: "pop-rock", 3710: "cançó autor", 3711: "cançó autor", 3712: "folk",
    3713: "pop-rock", 3714: "pop-rock", 3715: "cançó autor", 3716: "cançó autor",
    3717: "cançó autor", 3718: "folk", 3719: "folk", 3720: "folk",
    3721: "cançó autor", 3722: "pop-rock", 3723: "pop-rock", 3724: "cançó autor",
    3725: "folk", 3726: "cançó autor", 3727: "pop-rock", 3728: "pop-rock",
    3729: "pop-rock", 3730: "folk", 3731: "folk", 3732: "cançó autor",
    3733: "cançó autor", 3734: "folk", 3735: "folk", 3736: "folk",
    3737: "pop-rock", 3738: "folk", 3739: "cançó autor", 3740: "havanera",
    3741: "pop-rock", 3742: "pop-rock", 3743: "folk", 3744: "pop-rock",
    3745: "pop-rock", 3746: "cançó autor", 3747: "rumba", 3748: "cançó autor",
    3749: "pop-rock", 3750: "folk", 3751: "cançó autor", 3752: "pop-rock",
    3753: "pop-rock", 3754: "havanera", 3755: "folk", 3756: "pop-rock",
    3757: "pop-rock", 3758: "música urbana", 3759: "folk", 3760: "folk",
    3761: "folk", 3762: "pop-rock", 3763: "pop-rock", 3764: "pop-rock",
    3765: "havanera", 3766: "pop-rock", 3767: "folk", 3768: "pop-rock",
    3769: "cançó autor", 3770: "cançó autor", 3771: "folk", 3772: "folk",
    3773: "folk", 3774: "pop-rock", 3775: "pop-rock", 3776: "cançó autor",
    3777: "cançó autor", 3778: "havanera", 3779: "folk", 3780: "folk",
    3781: "pop-rock", 3782: "folk", 3783: "pop-rock", 3784: "cançó autor",
    3785: "pop-rock", 3786: "pop-rock", 3787: "pop-rock", 3788: "folk",
    3789: "folk", 3790: "pop-rock", 3791: "cançó autor", 3792: "pop-rock",
    3793: "folk", 3794: "folk", 3795: "folk", 3796: "folk",
    3797: "pop-rock", 3798: "cançó autor", 3799: "folk", 3800: "folk",
    3801: "folk", 3802: "pop-rock", 3803: "cançó autor", 3804: "cançó autor",
    3805: "folk", 3806: "música urbana", 3807: "folk", 3808: "pop-rock",
    3809: "pop-rock", 3810: "folk", 3811: "folk", 3812: "música urbana",
    3813: "cançó autor", 3814: "pop-rock", 3815: "música urbana", 3816: "folk",
    3817: "pop-rock", 3818: "pop-rock", 3819: "folk", 3820: "folk",
    3821: "cançó autor", 3822: "folk", 3823: "pop-rock", 3824: "cançó autor",
    3825: "folk", 3826: "cançó autor", 3827: "pop-rock", 3828: "pop-rock",
    3829: "cançó autor", 3830: "folk", 3831: "cançó autor", 3832: "cançó autor",
    3833: "folk", 3834: "pop-rock", 3835: "cançó autor", 3836: "cançó autor",
    3837: "pop-rock", 3838: "folk", 3839: "cançó autor", 3840: "cançó autor",
    3841: "cançó autor", 3842: "pop-rock", 3843: "cançó autor", 3844: "cançó autor",
    3845: "pop-rock", 3846: "rumba", 3847: "cançó autor", 3848: "cançó autor",
    3849: "cançó autor", 3850: "havanera", 3851: "folk", 3852: "folk",
    3853: "folk", 3854: "cançó autor", 3855: "cançó autor", 3856: "cançó autor",
    3857: "pop-rock", 3858: "cançó autor", 3859: "cançó autor", 3860: "folk",
    3861: "cançó autor", 3862: "havanera", 3863: "música urbana", 3864: "cançó autor",
    3865: "cançó autor", 3866: "pop-rock", 3867: "pop-rock", 3868: "pop-rock",
    3869: "pop-rock", 3870: "cançó autor", 3871: "pop-rock", 3872: "folk",
    3873: "folk", 3874: "pop-rock", 3875: "cançó autor", 3876: "folk",
    3877: "pop-rock", 3878: "pop-rock", 3879: "cançó autor", 3880: "folk",
    3881: "cançó autor", 3882: "cançó autor", 3883: "folk", 3884: "cançó autor",
    3885: "pop-rock", 3886: "pop-rock", 3887: "cançó autor", 3888: "pop-rock",
    3889: "rumba", 3890: "folk", 3891: "cançó autor", 3892: "pop-rock",
    3893: "cançó autor", 3894: "folk", 3895: "cançó autor", 3896: "pop-rock",
    3897: "pop-rock", 3898: "cançó autor", 3899: "pop-rock", 3900: "folk",
    3901: "cançó autor", 3902: "pop-rock", 3903: "música urbana", 3904: "folk",
    3905: "folk", 3906: "pop-rock", 3907: "pop-rock", 3908: "música urbana",
    3909: "pop-rock", 3910: "folk", 3911: "pop-rock", 3912: "folk",
    3913: "cançó autor", 3914: "pop-rock", 3915: "folk", 3916: "música urbana",
    3917: "pop-rock", 3918: "cançó autor", 3919: "música urbana", 3920: "pop-rock",
    3921: "folk", 3922: "folk", 3923: "cançó autor", 3924: "folk",
    3925: "cançó autor", 3926: "folk", 3927: "folk", 3928: "cançó autor",
    3929: "pop-rock", 3930: "cançó autor", 3931: "cançó autor", 3932: "pop-rock",
    3933: "cançó autor", 3934: "cançó autor", 3935: "cançó autor", 3936: "folk",
    3937: "pop-rock", 3938: "pop-rock", 3939: "folk", 3940: "pop-rock",
    3941: "pop-rock", 3942: "pop-rock", 3943: "folk", 3944: "cançó autor",
    3945: "folk", 3946: "cançó autor", 3947: "cançó autor", 3948: "cançó autor",
    3949: "pop-rock", 3950: "cançó autor", 3951: "cançó autor", 3952: "pop-rock",
    3953: "cançó autor", 3954: "cançó autor", 3955: "cançó autor", 3956: "folk",
    3957: "cançó autor", 3958: "pop-rock", 3959: "pop-rock", 3960: "cançó autor",
    3961: "cançó autor", 3962: "pop-rock", 3963: "música urbana", 3964: "folk",
    3965: "cançó autor", 3966: "folk", 3967: "pop-rock", 3968: "pop-rock",
    3969: "cançó autor", 3970: "pop-rock", 3971: "havanera", 3972: "folk",
    3973: "pop-rock", 3974: "música urbana", 3975: "pop-rock", 3976: "música urbana",
    3977: "pop-rock", 3978: "cançó autor", 3979: "pop-rock", 3980: "folk",
    3981: "folk", 3982: "pop-rock", 3983: "folk", 3984: "música urbana",
    3985: "cançó autor", 3986: "música urbana", 3987: "pop-rock", 3988: "pop-rock",
    3989: "folk", 3990: "cançó autor", 3991: "cançó autor", 3992: "cançó autor",
    3993: "cançó autor", 3994: "pop-rock", 3995: "pop-rock", 3996: "pop-rock",
    3997: "pop-rock", 3998: "cançó autor", 3999: "folk", 4000: "pop-rock",
}

ALLOWED = {"folk", "cançó autor", "pop-rock", "rumba", "havanera", "música urbana"}
assert len(GENRES) == 500
assert set(GENRES.keys()) == set(range(3501, 4001))
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
