"""Add a manually-assigned `genre` column to top_5000_songs_part02.csv.

Classification of each of the 500 songs (#501-1000) into one of:
{folk, cançó autor, pop-rock, rumba, havanera, música urbana}

Same criteria as part01.
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "top_5000_songs_part02.csv"
DST = HERE / "top_5000_songs_part02_genre.csv"

GENRES = {
    501: "pop-rock", 502: "pop-rock", 503: "pop-rock", 504: "folk",
    505: "folk", 506: "pop-rock", 507: "folk", 508: "pop-rock",
    509: "cançó autor", 510: "pop-rock", 511: "folk", 512: "folk",
    513: "pop-rock", 514: "folk", 515: "folk", 516: "música urbana",
    517: "cançó autor", 518: "pop-rock", 519: "cançó autor", 520: "folk",
    521: "música urbana", 522: "havanera", 523: "folk", 524: "folk",
    525: "pop-rock", 526: "cançó autor", 527: "cançó autor", 528: "cançó autor",
    529: "música urbana", 530: "cançó autor", 531: "havanera", 532: "música urbana",
    533: "música urbana", 534: "música urbana", 535: "pop-rock", 536: "folk",
    537: "pop-rock", 538: "pop-rock", 539: "folk", 540: "folk",
    541: "pop-rock", 542: "folk", 543: "pop-rock", 544: "folk",
    545: "pop-rock", 546: "cançó autor", 547: "rumba", 548: "havanera",
    549: "folk", 550: "pop-rock", 551: "folk", 552: "folk",
    553: "pop-rock", 554: "pop-rock", 555: "cançó autor", 556: "pop-rock",
    557: "música urbana", 558: "pop-rock", 559: "pop-rock", 560: "folk",
    561: "pop-rock", 562: "música urbana", 563: "música urbana", 564: "pop-rock",
    565: "folk", 566: "cançó autor", 567: "folk", 568: "folk",
    569: "pop-rock", 570: "pop-rock", 571: "cançó autor", 572: "folk",
    573: "pop-rock", 574: "folk", 575: "cançó autor", 576: "cançó autor",
    577: "havanera", 578: "pop-rock", 579: "cançó autor", 580: "pop-rock",
    581: "folk", 582: "pop-rock", 583: "pop-rock", 584: "folk",
    585: "cançó autor", 586: "pop-rock", 587: "pop-rock", 588: "folk",
    589: "folk", 590: "cançó autor", 591: "cançó autor", 592: "folk",
    593: "havanera", 594: "pop-rock", 595: "folk", 596: "música urbana",
    597: "pop-rock", 598: "pop-rock", 599: "folk", 600: "pop-rock",
    601: "pop-rock", 602: "cançó autor", 603: "folk", 604: "música urbana",
    605: "cançó autor", 606: "folk", 607: "folk", 608: "cançó autor",
    609: "folk", 610: "folk", 611: "cançó autor", 612: "havanera",
    613: "pop-rock", 614: "pop-rock", 615: "cançó autor", 616: "pop-rock",
    617: "música urbana", 618: "pop-rock", 619: "pop-rock", 620: "cançó autor",
    621: "cançó autor", 622: "pop-rock", 623: "folk", 624: "pop-rock",
    625: "música urbana", 626: "folk", 627: "pop-rock", 628: "pop-rock",
    629: "cançó autor", 630: "pop-rock", 631: "folk", 632: "cançó autor",
    633: "pop-rock", 634: "cançó autor", 635: "folk", 636: "pop-rock",
    637: "folk", 638: "cançó autor", 639: "folk", 640: "pop-rock",
    641: "folk", 642: "música urbana", 643: "pop-rock", 644: "folk",
    645: "folk", 646: "folk", 647: "pop-rock", 648: "folk",
    649: "folk", 650: "folk", 651: "folk", 652: "pop-rock",
    653: "havanera", 654: "pop-rock", 655: "cançó autor", 656: "pop-rock",
    657: "folk", 658: "cançó autor", 659: "folk", 660: "folk",
    661: "pop-rock", 662: "pop-rock", 663: "folk", 664: "música urbana",
    665: "pop-rock", 666: "pop-rock", 667: "cançó autor", 668: "folk",
    669: "pop-rock", 670: "havanera", 671: "pop-rock", 672: "pop-rock",
    673: "pop-rock", 674: "folk", 675: "folk", 676: "cançó autor",
    677: "pop-rock", 678: "folk", 679: "folk", 680: "cançó autor",
    681: "folk", 682: "cançó autor", 683: "cançó autor", 684: "cançó autor",
    685: "pop-rock", 686: "cançó autor", 687: "pop-rock", 688: "folk",
    689: "cançó autor", 690: "pop-rock", 691: "pop-rock", 692: "pop-rock",
    693: "cançó autor", 694: "folk", 695: "pop-rock", 696: "pop-rock",
    697: "pop-rock", 698: "havanera", 699: "folk", 700: "folk",
    701: "folk", 702: "cançó autor", 703: "folk", 704: "rumba",
    705: "música urbana", 706: "pop-rock", 707: "música urbana", 708: "folk",
    709: "folk", 710: "música urbana", 711: "pop-rock", 712: "folk",
    713: "cançó autor", 714: "folk", 715: "folk", 716: "pop-rock",
    717: "cançó autor", 718: "folk", 719: "cançó autor", 720: "cançó autor",
    721: "cançó autor", 722: "pop-rock", 723: "cançó autor", 724: "cançó autor",
    725: "cançó autor", 726: "música urbana", 727: "pop-rock", 728: "música urbana",
    729: "pop-rock", 730: "cançó autor", 731: "cançó autor", 732: "cançó autor",
    733: "folk", 734: "folk", 735: "folk", 736: "folk",
    737: "folk", 738: "música urbana", 739: "cançó autor", 740: "pop-rock",
    741: "pop-rock", 742: "música urbana", 743: "folk", 744: "folk",
    745: "folk", 746: "pop-rock", 747: "folk", 748: "folk",
    749: "pop-rock", 750: "folk", 751: "folk", 752: "cançó autor",
    753: "cançó autor", 754: "pop-rock", 755: "pop-rock", 756: "pop-rock",
    757: "folk", 758: "folk", 759: "música urbana", 760: "pop-rock",
    761: "folk", 762: "música urbana", 763: "cançó autor", 764: "pop-rock",
    765: "pop-rock", 766: "música urbana", 767: "pop-rock", 768: "folk",
    769: "pop-rock", 770: "folk", 771: "cançó autor", 772: "folk",
    773: "pop-rock", 774: "música urbana", 775: "folk", 776: "cançó autor",
    777: "pop-rock", 778: "folk", 779: "pop-rock", 780: "pop-rock",
    781: "folk", 782: "folk", 783: "pop-rock", 784: "pop-rock",
    785: "folk", 786: "música urbana", 787: "pop-rock", 788: "cançó autor",
    789: "pop-rock", 790: "rumba", 791: "pop-rock", 792: "cançó autor",
    793: "cançó autor", 794: "folk", 795: "cançó autor", 796: "folk",
    797: "cançó autor", 798: "pop-rock", 799: "cançó autor", 800: "música urbana",
    801: "folk", 802: "pop-rock", 803: "pop-rock", 804: "folk",
    805: "pop-rock", 806: "música urbana", 807: "pop-rock", 808: "pop-rock",
    809: "cançó autor", 810: "folk", 811: "pop-rock", 812: "pop-rock",
    813: "rumba", 814: "folk", 815: "pop-rock", 816: "pop-rock",
    817: "folk", 818: "pop-rock", 819: "pop-rock", 820: "cançó autor",
    821: "folk", 822: "folk", 823: "folk", 824: "pop-rock",
    825: "pop-rock", 826: "cançó autor", 827: "pop-rock", 828: "cançó autor",
    829: "música urbana", 830: "folk", 831: "pop-rock", 832: "pop-rock",
    833: "pop-rock", 834: "cançó autor", 835: "pop-rock", 836: "música urbana",
    837: "pop-rock", 838: "folk", 839: "folk", 840: "folk",
    841: "cançó autor", 842: "folk", 843: "música urbana", 844: "pop-rock",
    845: "pop-rock", 846: "cançó autor", 847: "folk", 848: "música urbana",
    849: "folk", 850: "música urbana", 851: "cançó autor", 852: "pop-rock",
    853: "havanera", 854: "música urbana", 855: "folk", 856: "folk",
    857: "música urbana", 858: "cançó autor", 859: "pop-rock", 860: "cançó autor",
    861: "cançó autor", 862: "cançó autor", 863: "folk", 864: "pop-rock",
    865: "cançó autor", 866: "folk", 867: "cançó autor", 868: "folk",
    869: "pop-rock", 870: "folk", 871: "folk", 872: "folk",
    873: "pop-rock", 874: "pop-rock", 875: "folk", 876: "folk",
    877: "folk", 878: "havanera", 879: "folk", 880: "pop-rock",
    881: "folk", 882: "folk", 883: "folk", 884: "cançó autor",
    885: "pop-rock", 886: "cançó autor", 887: "folk", 888: "pop-rock",
    889: "pop-rock", 890: "pop-rock", 891: "pop-rock", 892: "pop-rock",
    893: "pop-rock", 894: "folk", 895: "cançó autor", 896: "folk",
    897: "pop-rock", 898: "pop-rock", 899: "cançó autor", 900: "cançó autor",
    901: "pop-rock", 902: "cançó autor", 903: "cançó autor", 904: "pop-rock",
    905: "pop-rock", 906: "folk", 907: "havanera", 908: "cançó autor",
    909: "música urbana", 910: "cançó autor", 911: "folk", 912: "pop-rock",
    913: "folk", 914: "folk", 915: "pop-rock", 916: "folk",
    917: "pop-rock", 918: "folk", 919: "folk", 920: "cançó autor",
    921: "cançó autor", 922: "folk", 923: "cançó autor", 924: "folk",
    925: "folk", 926: "folk", 927: "folk", 928: "folk",
    929: "cançó autor", 930: "rumba", 931: "folk", 932: "música urbana",
    933: "pop-rock", 934: "cançó autor", 935: "pop-rock", 936: "havanera",
    937: "cançó autor", 938: "cançó autor", 939: "música urbana", 940: "pop-rock",
    941: "folk", 942: "folk", 943: "pop-rock", 944: "cançó autor",
    945: "folk", 946: "folk", 947: "folk", 948: "música urbana",
    949: "pop-rock", 950: "cançó autor", 951: "folk", 952: "folk",
    953: "folk", 954: "folk", 955: "cançó autor", 956: "cançó autor",
    957: "música urbana", 958: "folk", 959: "pop-rock", 960: "pop-rock",
    961: "folk", 962: "cançó autor", 963: "folk", 964: "pop-rock",
    965: "cançó autor", 966: "folk", 967: "pop-rock", 968: "folk",
    969: "folk", 970: "música urbana", 971: "pop-rock", 972: "cançó autor",
    973: "música urbana", 974: "pop-rock", 975: "cançó autor", 976: "música urbana",
    977: "cançó autor", 978: "cançó autor", 979: "cançó autor", 980: "folk",
    981: "folk", 982: "pop-rock", 983: "cançó autor", 984: "folk",
    985: "música urbana", 986: "música urbana", 987: "pop-rock", 988: "pop-rock",
    989: "folk", 990: "pop-rock", 991: "folk", 992: "música urbana",
    993: "cançó autor", 994: "pop-rock", 995: "rumba", 996: "folk",
    997: "pop-rock", 998: "pop-rock", 999: "cançó autor", 1000: "pop-rock",
}

ALLOWED = {"folk", "cançó autor", "pop-rock", "rumba", "havanera", "música urbana"}
assert len(GENRES) == 500
assert set(GENRES.keys()) == set(range(501, 1001))
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
