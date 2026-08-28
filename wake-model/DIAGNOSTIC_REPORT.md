# Wake-word acoustic diagnostics

Dataset: 36 records; split counts: {'train': 25, 'validation': 11}

## Inventory
{
  "by_device": {
    "macbook_builtin": 36
  },
  "by_environment": {
    "renovation_noise_001": 11,
    "room_001": 25
  },
  "by_label": {
    "background": 10,
    "hard_negative_speech": 11,
    "target": 15
  },
  "by_phrase": {
    "(empty)": 10,
    "Cauco": 2,
    "Hola": 4,
    "Hola Carlos": 2,
    "Hola Cauco": 15,
    "Hola Claudio": 1,
    "Hola buenos dias": 1,
    "Hola como estas": 1
  },
  "by_speaker": {
    "speaker_001": 36
  },
  "by_split": {
    "train": 25,
    "validation": 11
  },
  "by_split_label": {
    "test": {},
    "train": {
      "background": 5,
      "hard_negative_speech": 8,
      "target": 12
    },
    "validation": {
      "background": 5,
      "hard_negative_speech": 3,
      "target": 3
    }
  },
  "channels": [
    1
  ],
  "durations_s": [
    1.7866875,
    1.7546875,
    1.7653125,
    1.7653125,
    1.801625,
    1.7866875,
    1.7653125,
    1.7333125,
    1.776,
    1.7653125,
    1.7866875,
    1.7333125,
    1.7653125,
    1.7653125,
    1.7866875,
    1.776,
    1.7866875,
    1.7653125,
    1.759,
    1.744,
    1.7653125,
    1.7546875,
    1.7653125,
    1.7653125,
    1.7653125,
    1.7333125,
    1.7653125,
    1.7653125,
    1.769625,
    1.737625,
    1.769625,
    1.737625,
    1.7866875,
    1.744,
    1.7653125,
    1.7653125
  ],
  "sample_rates_hz": [
    16000
  ],
  "total": 36
}

## Audio findings
{
  "flags": {
    "clipped": [
      "rec_20260828_044846_0215db"
    ],
    "duration_outliers": [],
    "silence_or_low_energy": [
      "rec_20260828_044525_ef9edc",
      "rec_20260828_045358_15a643",
      "rec_20260828_045409_c14beb",
      "rec_20260828_045431_211104",
      "rec_20260828_045443_c8b138",
      "rec_20260828_045457_476bed",
      "rec_20260828_051458_8c053f"
    ]
  },
  "records": [
    {
      "clipped": false,
      "duration_s": 1.7866875,
      "peak": 0.00311279296875,
      "recording_id": "rec_20260828_044525_ef9edc",
      "rms": 0.0005501166809550776,
      "silence_ratio": 0.0847457627118644,
      "spectral_bandwidth_hz": 844.0430296503687,
      "spectral_centroid_hz": 255.6153447938728,
      "spectral_rolloff_hz": 250.0,
      "zero_crossing_rate": 0.08294269922339607
    },
    {
      "clipped": false,
      "duration_s": 1.7546875,
      "peak": 0.162750244140625,
      "recording_id": "rec_20260828_044644_f5db4e",
      "rms": 0.03160480513383737,
      "silence_ratio": 0.3815028901734104,
      "spectral_bandwidth_hz": 285.79347318440995,
      "spectral_centroid_hz": 371.4210131180173,
      "spectral_rolloff_hz": 562.5,
      "zero_crossing_rate": 0.05172045308826673
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.154266357421875,
      "recording_id": "rec_20260828_044702_a053b6",
      "rms": 0.023039505601873095,
      "silence_ratio": 0.2857142857142857,
      "spectral_bandwidth_hz": 334.0543167522542,
      "spectral_centroid_hz": 457.0739062558708,
      "spectral_rolloff_hz": 625.0,
      "zero_crossing_rate": 0.07619317377142047
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.176116943359375,
      "recording_id": "rec_20260828_044710_a01f01",
      "rms": 0.025671769247750827,
      "silence_ratio": 0.21714285714285714,
      "spectral_bandwidth_hz": 274.59382591709226,
      "spectral_centroid_hz": 498.5614471156853,
      "spectral_rolloff_hz": 656.25,
      "zero_crossing_rate": 0.06096870131709389
    },
    {
      "clipped": false,
      "duration_s": 1.801625,
      "peak": 0.127838134765625,
      "recording_id": "rec_20260828_044719_7cee65",
      "rms": 0.022734088797168255,
      "silence_ratio": 0.16292134831460675,
      "spectral_bandwidth_hz": 309.32835251978224,
      "spectral_centroid_hz": 446.2256811207124,
      "spectral_rolloff_hz": 593.75,
      "zero_crossing_rate": 0.06834345186470078
    },
    {
      "clipped": false,
      "duration_s": 1.7866875,
      "peak": 0.090179443359375,
      "recording_id": "rec_20260828_044728_8365bb",
      "rms": 0.014269190700663148,
      "silence_ratio": 0.096045197740113,
      "spectral_bandwidth_hz": 410.67523681471187,
      "spectral_centroid_hz": 391.54473651867625,
      "spectral_rolloff_hz": 562.5,
      "zero_crossing_rate": 0.06058909955922479
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.287078857421875,
      "recording_id": "rec_20260828_044758_d44f25",
      "rms": 0.03611854431288765,
      "silence_ratio": 0.4857142857142857,
      "spectral_bandwidth_hz": 353.1599690635811,
      "spectral_centroid_hz": 456.3046510953038,
      "spectral_rolloff_hz": 531.25,
      "zero_crossing_rate": 0.12887692961336922
    },
    {
      "clipped": false,
      "duration_s": 1.7333125,
      "peak": 0.11376953125,
      "recording_id": "rec_20260828_044805_a6123a",
      "rms": 0.016061557750699944,
      "silence_ratio": 0.15204678362573099,
      "spectral_bandwidth_hz": 374.0521661081575,
      "spectral_centroid_hz": 455.9600137292744,
      "spectral_rolloff_hz": 625.0,
      "zero_crossing_rate": 0.11492139045146402
    },
    {
      "clipped": false,
      "duration_s": 1.776,
      "peak": 0.126617431640625,
      "recording_id": "rec_20260828_044814_dcab31",
      "rms": 0.01937798577491109,
      "silence_ratio": 0.1534090909090909,
      "spectral_bandwidth_hz": 280.1123952236943,
      "spectral_centroid_hz": 400.99294861405326,
      "spectral_rolloff_hz": 531.25,
      "zero_crossing_rate": 0.09213443603730424
    },
    {
      "clipped": true,
      "duration_s": 1.7653125,
      "peak": 0.999969482421875,
      "recording_id": "rec_20260828_044846_0215db",
      "rms": 0.05772924443097175,
      "silence_ratio": 0.12,
      "spectral_bandwidth_hz": 269.3740711689484,
      "spectral_centroid_hz": 544.6752461096086,
      "spectral_rolloff_hz": 718.75,
      "zero_crossing_rate": 0.04337204361988387
    },
    {
      "clipped": false,
      "duration_s": 1.7866875,
      "peak": 0.393157958984375,
      "recording_id": "rec_20260828_044853_c457b9",
      "rms": 0.02924076049187864,
      "silence_ratio": 0.0847457627118644,
      "spectral_bandwidth_hz": 1340.4002071006664,
      "spectral_centroid_hz": 470.2459634914165,
      "spectral_rolloff_hz": 343.75,
      "zero_crossing_rate": 0.09039389911145315
    },
    {
      "clipped": false,
      "duration_s": 1.7333125,
      "peak": 0.281158447265625,
      "recording_id": "rec_20260828_044902_ecd5c8",
      "rms": 0.024608005695430125,
      "silence_ratio": 0.05847953216374269,
      "spectral_bandwidth_hz": 1491.9013837164468,
      "spectral_centroid_hz": 563.7343489759819,
      "spectral_rolloff_hz": 250.0,
      "zero_crossing_rate": 0.11185633924707919
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.208251953125,
      "recording_id": "rec_20260828_044910_f71edc",
      "rms": 0.01926247017711522,
      "silence_ratio": 0.07428571428571429,
      "spectral_bandwidth_hz": 1753.8490280774236,
      "spectral_centroid_hz": 767.5275049234954,
      "spectral_rolloff_hz": 656.25,
      "zero_crossing_rate": 0.09630363971108909
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.66839599609375,
      "recording_id": "rec_20260828_044917_20764b",
      "rms": 0.026625536486576066,
      "silence_ratio": 0.08571428571428572,
      "spectral_bandwidth_hz": 965.9589494341598,
      "spectral_centroid_hz": 688.023892158686,
      "spectral_rolloff_hz": 1343.75,
      "zero_crossing_rate": 0.12307038663078884
    },
    {
      "clipped": false,
      "duration_s": 1.7866875,
      "peak": 0.305999755859375,
      "recording_id": "rec_20260828_045231_17dd0f",
      "rms": 0.03925523217158409,
      "silence_ratio": 0.5706214689265536,
      "spectral_bandwidth_hz": 199.59646487155237,
      "spectral_centroid_hz": 423.94099568033,
      "spectral_rolloff_hz": 500.0,
      "zero_crossing_rate": 0.07612117819911846
    },
    {
      "clipped": false,
      "duration_s": 1.776,
      "peak": 0.171844482421875,
      "recording_id": "rec_20260828_045249_22ff6d",
      "rms": 0.030409072589745602,
      "silence_ratio": 0.3522727272727273,
      "spectral_bandwidth_hz": 263.911125484306,
      "spectral_centroid_hz": 332.87229240491826,
      "spectral_rolloff_hz": 500.0,
      "zero_crossing_rate": 0.042618335386239665
    },
    {
      "clipped": false,
      "duration_s": 1.7866875,
      "peak": 0.165191650390625,
      "recording_id": "rec_20260828_045302_688fb9",
      "rms": 0.028055977216220454,
      "silence_ratio": 0.096045197740113,
      "spectral_bandwidth_hz": 596.3486256998823,
      "spectral_centroid_hz": 385.1168000516945,
      "spectral_rolloff_hz": 593.75,
      "zero_crossing_rate": 0.11628069684460925
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.206817626953125,
      "recording_id": "rec_20260828_045318_a7ae96",
      "rms": 0.03080028156811621,
      "silence_ratio": 0.35428571428571426,
      "spectral_bandwidth_hz": 824.0694639394413,
      "spectral_centroid_hz": 508.2456815473495,
      "spectral_rolloff_hz": 562.5,
      "zero_crossing_rate": 0.16573431525279705
    },
    {
      "clipped": false,
      "duration_s": 1.759,
      "peak": 0.219696044921875,
      "recording_id": "rec_20260828_045330_f113f8",
      "rms": 0.030589253025580288,
      "silence_ratio": 0.39655172413793105,
      "spectral_bandwidth_hz": 488.4304138800972,
      "spectral_centroid_hz": 393.24706790089533,
      "spectral_rolloff_hz": 531.25,
      "zero_crossing_rate": 0.14195359414419217
    },
    {
      "clipped": false,
      "duration_s": 1.744,
      "peak": 0.016357421875,
      "recording_id": "rec_20260828_045358_15a643",
      "rms": 0.001582246499853595,
      "silence_ratio": 0.06976744186046512,
      "spectral_bandwidth_hz": 1418.905188844675,
      "spectral_centroid_hz": 630.2955182479453,
      "spectral_rolloff_hz": 843.75,
      "zero_crossing_rate": 0.11109916496434075
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.072967529296875,
      "recording_id": "rec_20260828_045409_c14beb",
      "rms": 0.005117374096590168,
      "silence_ratio": 0.10857142857142857,
      "spectral_bandwidth_hz": 730.0063942071588,
      "spectral_centroid_hz": 260.4150492198284,
      "spectral_rolloff_hz": 343.75,
      "zero_crossing_rate": 0.14010055232969834
    },
    {
      "clipped": false,
      "duration_s": 1.7546875,
      "peak": 0.11846923828125,
      "recording_id": "rec_20260828_045420_37b756",
      "rms": 0.013394222961909757,
      "silence_ratio": 0.6127167630057804,
      "spectral_bandwidth_hz": 258.0784698854597,
      "spectral_centroid_hz": 334.84507297540614,
      "spectral_rolloff_hz": 500.0,
      "zero_crossing_rate": 0.05741967656906746
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.02801513671875,
      "recording_id": "rec_20260828_045431_211104",
      "rms": 0.002421878634077003,
      "silence_ratio": 0.06285714285714286,
      "spectral_bandwidth_hz": 445.8102723024035,
      "spectral_centroid_hz": 167.85406626458368,
      "spectral_rolloff_hz": 156.25,
      "zero_crossing_rate": 0.056472171080583486
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.070159912109375,
      "recording_id": "rec_20260828_045443_c8b138",
      "rms": 0.0036725493708685756,
      "silence_ratio": 0.14857142857142858,
      "spectral_bandwidth_hz": 1197.5665255471083,
      "spectral_centroid_hz": 503.5690461552807,
      "spectral_rolloff_hz": 375.0,
      "zero_crossing_rate": 0.17412547797762357
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.0604248046875,
      "recording_id": "rec_20260828_045457_476bed",
      "rms": 0.004537931907236007,
      "silence_ratio": 0.21714285714285714,
      "spectral_bandwidth_hz": 727.1890431018647,
      "spectral_centroid_hz": 544.2782803253288,
      "spectral_rolloff_hz": 750.0,
      "zero_crossing_rate": 0.12834584336496246
    },
    {
      "clipped": false,
      "duration_s": 1.7333125,
      "peak": 0.08660888671875,
      "recording_id": "rec_20260828_051458_8c053f",
      "rms": 0.008548306527181703,
      "silence_ratio": 0.07602339181286549,
      "spectral_bandwidth_hz": 1190.8999641705916,
      "spectral_centroid_hz": 1340.9928141376415,
      "spectral_rolloff_hz": 2250.0,
      "zero_crossing_rate": 0.20543054954565124
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.38690185546875,
      "recording_id": "rec_20260828_051505_e29372",
      "rms": 0.02356772316735463,
      "silence_ratio": 0.06857142857142857,
      "spectral_bandwidth_hz": 1298.7702658861103,
      "spectral_centroid_hz": 1122.553480866274,
      "spectral_rolloff_hz": 2156.25,
      "zero_crossing_rate": 0.20124628239626116
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.447235107421875,
      "recording_id": "rec_20260828_052248_8ad611",
      "rms": 0.022836004647056592,
      "silence_ratio": 0.08,
      "spectral_bandwidth_hz": 1005.2090153945173,
      "spectral_centroid_hz": 681.551323796142,
      "spectral_rolloff_hz": 1812.5,
      "zero_crossing_rate": 0.18644667894065997
    },
    {
      "clipped": false,
      "duration_s": 1.769625,
      "peak": 0.624420166015625,
      "recording_id": "rec_20260828_053113_559726",
      "rms": 0.03793499061797861,
      "silence_ratio": 0.06857142857142857,
      "spectral_bandwidth_hz": 689.1791533593674,
      "spectral_centroid_hz": 479.1433961792614,
      "spectral_rolloff_hz": 1000.0,
      "zero_crossing_rate": 0.14752940345424365
    },
    {
      "clipped": false,
      "duration_s": 1.737625,
      "peak": 0.552825927734375,
      "recording_id": "rec_20260828_053125_482797",
      "rms": 0.051798807025100535,
      "silence_ratio": 0.0872093023255814,
      "spectral_bandwidth_hz": 620.8474432914495,
      "spectral_centroid_hz": 381.40696711269464,
      "spectral_rolloff_hz": 531.25,
      "zero_crossing_rate": 0.14316031797417358
    },
    {
      "clipped": false,
      "duration_s": 1.769625,
      "peak": 0.15216064453125,
      "recording_id": "rec_20260828_053259_f86133",
      "rms": 0.028889857707116166,
      "silence_ratio": 0.3028571428571429,
      "spectral_bandwidth_hz": 647.426121008104,
      "spectral_centroid_hz": 545.4170759919463,
      "spectral_rolloff_hz": 1125.0,
      "zero_crossing_rate": 0.12139299968212482
    },
    {
      "clipped": false,
      "duration_s": 1.737625,
      "peak": 0.32806396484375,
      "recording_id": "rec_20260828_053306_a08fd8",
      "rms": 0.04914664838120729,
      "silence_ratio": 0.0755813953488372,
      "spectral_bandwidth_hz": 441.6754365291124,
      "spectral_centroid_hz": 477.9986403990249,
      "spectral_rolloff_hz": 562.5,
      "zero_crossing_rate": 0.08776662709974462
    },
    {
      "clipped": false,
      "duration_s": 1.7866875,
      "peak": 0.243927001953125,
      "recording_id": "rec_20260828_053314_951f73",
      "rms": 0.03508306081122308,
      "silence_ratio": 0.0847457627118644,
      "spectral_bandwidth_hz": 457.794987323052,
      "spectral_centroid_hz": 523.2679943760555,
      "spectral_rolloff_hz": 687.5,
      "zero_crossing_rate": 0.10512138809207304
    },
    {
      "clipped": false,
      "duration_s": 1.744,
      "peak": 0.3377685546875,
      "recording_id": "rec_20260828_053427_3b3ebc",
      "rms": 0.03015500008571029,
      "silence_ratio": 0.0755813953488372,
      "spectral_bandwidth_hz": 1410.6482417011957,
      "spectral_centroid_hz": 497.3074939812538,
      "spectral_rolloff_hz": 218.75,
      "zero_crossing_rate": 0.048238540658710534
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.4036865234375,
      "recording_id": "rec_20260828_053431_a11baf",
      "rms": 0.053093817871851016,
      "silence_ratio": 0.12571428571428572,
      "spectral_bandwidth_hz": 252.4794642528753,
      "spectral_centroid_hz": 447.744971182539,
      "spectral_rolloff_hz": 531.25,
      "zero_crossing_rate": 0.08646084124061748
    },
    {
      "clipped": false,
      "duration_s": 1.7653125,
      "peak": 0.8046875,
      "recording_id": "rec_20260828_053434_c66717",
      "rms": 0.06619203689408622,
      "silence_ratio": 0.2342857142857143,
      "spectral_bandwidth_hz": 473.65012385025676,
      "spectral_centroid_hz": 599.1760943597623,
      "spectral_rolloff_hz": 687.5,
      "zero_crossing_rate": 0.10950998442147004
    }
  ]
}

## Feature/model findings
{
  "feature": {
    "between_class_distances": {
      "background__background": 0.0,
      "background__hard_negative_speech": 6.669258557259517,
      "background__target": 11.18251530754194,
      "hard_negative_speech__background": 6.669258557259517,
      "hard_negative_speech__hard_negative_speech": 0.0,
      "hard_negative_speech__target": 7.425325742936368,
      "target__background": 11.18251530754194,
      "target__hard_negative_speech": 7.425325742936368,
      "target__target": 0.0
    },
    "class_centroids": {
      "background": [
        1.0435454732619704,
        1.1186633188550668,
        1.2225107453164314,
        0.8032409149452004,
        0.5880545033447628,
        0.5702216696323357,
        0.7664807200781398,
        0.7869801973648911,
        0.8056157018958086,
        0.9471249535234012,
        0.9983984542910116,
        1.2243120214903163,
        1.3804648634772345,
        1.3137877586257154,
        1.3108377002859153,
        1.4290098537086613,
        1.3199626406393012,
        1.3391989459732256,
        1.5569591490076364,
        1.5897306877155235,
        1.486632242125506,
        1.2828902024045952,
        1.2530377524364398,
        1.4317954799681794,
        -0.12362254378516664,
        -0.15894973704964904,
        0.15768239838174578,
        -0.20203195857538442,
        -0.32647472996685567,
        -0.3137529260701596,
        -0.03399059467301006,
        0.09538724902173149,
        0.10365813137967017,
        0.241080973863812,
        0.2438465715405113,
        0.4838308696644528,
        0.7661287827577056,
        0.5546483860295147,
        0.5857394070702755,
        0.8911677822694857,
        0.7479074830720785,
        0.6944697924945289,
        0.9256759948932608,
        0.9303314342577964,
        0.9024905061590621,
        0.7338591743690944,
        0.733953033413028,
        0.9412376829919129,
        1.1876603480806853,
        -0.37056527010316137,
        -0.03730223811372522,
        0.7566363975350894,
        0.565751376556029,
        -0.09405719598607394,
        -0.268264350784212,
        -0.1867736478837428,
        -0.5366901936530776,
        -1.3217941396281627,
        -1.3844381820204887,
        -1.4987947163936493,
        -0.4102657656114264
      ],
      "hard_negative_speech": [
        0.2401804087894842,
        0.2793935221343914,
        0.24347352202480937,
        0.3743591194761034,
        0.42658437752483885,
        0.4395648038905446,
        0.3561337070161269,
        0.30546488205428796,
        0.29652658610092697,
        0.35477799490250606,
        0.4225936588374985,
        0.3334311430102773,
        0.16924404030793455,
        0.2658280676554819,
        0.29903916605765263,
        0.2128524296820386,
        0.28430329910538366,
        0.22556627234020682,
        0.03168719533270526,
        -0.031162377447596923,
        0.07521776908148133,
        0.2358992781416802,
        0.21203580911604944,
        0.16027869022908653,
        0.6413953150861497,
        0.7975342774000275,
        0.7355864506314878,
        0.7964430803600249,
        0.788704800435536,
        0.7425964509636275,
        0.6573115801154383,
        0.5292491540074098,
        0.44448638165778315,
        0.4733721473992093,
        0.6110185219977643,
        0.5949218412393049,
        0.4164001163057853,
        0.5795038246163791,
        0.5864983139237124,
        0.5147132398462264,
        0.6000747537446366,
        0.5402533818098862,
        0.3735631727493809,
        0.31606696073530083,
        0.28982822198479774,
        0.3709155773056383,
        0.3157579895723214,
        0.2935372677043595,
        0.2906516422342599,
        0.3665439710027035,
        -0.23916333766668277,
        -0.4172494386154184,
        -0.1531372161369857,
        -0.6316720455619785,
        -0.028289313699479623,
        -0.6926736932562477,
        -0.14535338789980926,
        0.8191598806638364,
        -0.024266847768393995,
        0.20800135142315795,
        -0.585944069663637
      ],
      "target": [
        -0.5949308863854791,
        -0.652372064279207,
        -0.6716951585650511,
        -0.5842564608779028,
        -0.5294122947435457,
        -0.5306355649405039,
        -0.5567894380433103,
        -0.531551670271564,
        -0.5333575998572045,
        -0.6311540605697514,
        -0.6977284618462541,
        -0.7324174376278147,
        -0.6880230533208036,
        -0.7246302778643678,
        -0.7455418191575621,
        -0.7373223921666315,
        -0.7395199663366331,
        -0.7083770757156501,
        -0.6698577756416523,
        -0.6416128682497338,
        -0.6695752802732805,
        -0.6918037697630335,
        -0.6634562695925498,
        -0.7034339101394642,
        -0.3760874834802784,
        -0.4654604611626631,
        -0.556091966413382,
        -0.44678207083360516,
        -0.38977206280416415,
        -0.3643339147798527,
        -0.42404497229653687,
        -0.3925774564306615,
        -0.3395151425133847,
        -0.4160318373760617,
        -0.5089484194737258,
        -0.5982107565197218,
        -0.5968204036862336,
        -0.6174393772565506,
        -0.6350569622284227,
        -0.7144620691764364,
        -0.7116779537764567,
        -0.6495313347459791,
        -0.6347404463717785,
        -0.5983494047642812,
        -0.5692565255561429,
        -0.55305170752422,
        -0.516319090303642,
        -0.5878738797162039,
        -0.6886262398564598,
        -0.0899604514588177,
        0.17498482432517515,
        -0.037098873229341724,
        -0.13363826280702162,
        0.4603051953688499,
        0.13063635529307488,
        0.5396048154557262,
        0.32052317262198854,
        0.004640971069176565,
        0.5930271410207996,
        0.4858302308819151,
        0.5615734487805191
      ]
    },
    "dimension": 61,
    "pca_2d": [
      {
        "recording_id": "rec_20260828_044525_ef9edc",
        "x": -13.727302285693671,
        "y": 0.14917736438984455
      },
      {
        "recording_id": "rec_20260828_044644_f5db4e",
        "x": 3.3090129386984217,
        "y": 5.608200484672454
      },
      {
        "recording_id": "rec_20260828_044702_a053b6",
        "x": 3.548501321324577,
        "y": 2.6998631910389848
      },
      {
        "recording_id": "rec_20260828_044710_a01f01",
        "x": 0.8636760219340603,
        "y": 1.1616787135595665
      },
      {
        "recording_id": "rec_20260828_044719_7cee65",
        "x": 3.5729950774549235,
        "y": 2.9178446430864082
      },
      {
        "recording_id": "rec_20260828_044728_8365bb",
        "x": 2.700632956220462,
        "y": 3.33975968336362
      },
      {
        "recording_id": "rec_20260828_044758_d44f25",
        "x": 5.30653790453472,
        "y": 2.057350138416581
      },
      {
        "recording_id": "rec_20260828_044805_a6123a",
        "x": 2.350572923501556,
        "y": -0.12589292699945206
      },
      {
        "recording_id": "rec_20260828_044814_dcab31",
        "x": 1.8677673442714795,
        "y": 0.8026007999198995
      },
      {
        "recording_id": "rec_20260828_044846_0215db",
        "x": 6.87847863719951,
        "y": 0.10517563806802759
      },
      {
        "recording_id": "rec_20260828_044853_c457b9",
        "x": 5.622566768897227,
        "y": -4.626031016511762
      },
      {
        "recording_id": "rec_20260828_044902_ecd5c8",
        "x": 3.50637474270485,
        "y": -6.6565067022604
      },
      {
        "recording_id": "rec_20260828_044910_f71edc",
        "x": 3.784881927679255,
        "y": -5.208386659740505
      },
      {
        "recording_id": "rec_20260828_044917_20764b",
        "x": 7.8406526261378255,
        "y": -4.856366261195022
      },
      {
        "recording_id": "rec_20260828_045231_17dd0f",
        "x": -1.28362973981876,
        "y": 5.135799988718362
      },
      {
        "recording_id": "rec_20260828_045249_22ff6d",
        "x": 2.400241564553526,
        "y": 3.6592960046482315
      },
      {
        "recording_id": "rec_20260828_045302_688fb9",
        "x": 4.7000315483991875,
        "y": 0.6466598480071034
      },
      {
        "recording_id": "rec_20260828_045318_a7ae96",
        "x": 4.874149776409843,
        "y": -0.07573725541883157
      },
      {
        "recording_id": "rec_20260828_045330_f113f8",
        "x": 3.5376097700596736,
        "y": -0.6366451572562478
      },
      {
        "recording_id": "rec_20260828_045358_15a643",
        "x": -9.10950142662683,
        "y": -1.2317494362626287
      },
      {
        "recording_id": "rec_20260828_045409_c14beb",
        "x": -6.252094003567131,
        "y": -3.0282487502381175
      },
      {
        "recording_id": "rec_20260828_045420_37b756",
        "x": -7.703992733035457,
        "y": 2.0678154884300786
      },
      {
        "recording_id": "rec_20260828_045431_211104",
        "x": -13.884373113819718,
        "y": -0.4625172342445547
      },
      {
        "recording_id": "rec_20260828_045443_c8b138",
        "x": -6.496412284063034,
        "y": -2.1944413431586907
      },
      {
        "recording_id": "rec_20260828_045457_476bed",
        "x": -8.207378263356485,
        "y": -1.2486992430329518
      },
      {
        "recording_id": "rec_20260828_051458_8c053f",
        "x": 2.85299282110995,
        "y": -4.233739988217312
      },
      {
        "recording_id": "rec_20260828_051505_e29372",
        "x": 9.418793663982218,
        "y": -4.39483402840006
      },
      {
        "recording_id": "rec_20260828_052248_8ad611",
        "x": 7.109071474209896,
        "y": -4.889081008719342
      },
      {
        "recording_id": "rec_20260828_053113_559726",
        "x": 6.236742499267995,
        "y": -4.745692974408937
      },
      {
        "recording_id": "rec_20260828_053125_482797",
        "x": 9.60133549041517,
        "y": -3.998178702512893
      },
      {
        "recording_id": "rec_20260828_053259_f86133",
        "x": 3.6213147830348515,
        "y": -1.6437214500754036
      },
      {
        "recording_id": "rec_20260828_053306_a08fd8",
        "x": 8.21680522044158,
        "y": -3.185050754040492
      },
      {
        "recording_id": "rec_20260828_053314_951f73",
        "x": 6.363710328559114,
        "y": -2.1570892592653155
      },
      {
        "recording_id": "rec_20260828_053427_3b3ebc",
        "x": 2.927423839854701,
        "y": -4.526522700053129
      },
      {
        "recording_id": "rec_20260828_053431_a11baf",
        "x": 4.418728108245885,
        "y": -0.8473770160595635
      },
      {
        "recording_id": "rec_20260828_053434_c66717",
        "x": 8.03876394777169,
        "y": -2.3665096300682076
      }
    ],
    "within_class_mean_distance": {
      "background": 4.03879843028007,
      "hard_negative_speech": 4.510846564501266,
      "target": 7.3054096315561425
    }
  },
  "models": {
    "binary_linear_svm_balanced": {
      "confusion_matrix": {
        "non_target": {
          "non_target": 8,
          "target": 0
        },
        "target": {
          "non_target": 3,
          "target": 0
        }
      },
      "pr_auc": 0.45833333333333326,
      "roc_auc": 0.6666666666666667,
      "score_distribution": {
        "non_target": [
          -3.508731247430079,
          -3.6033748627839044,
          -4.725768115265,
          -3.386972587338657,
          -3.9570216071707596,
          -1.9466756985133038,
          -1.276544957751173,
          -4.615082892748311
        ],
        "target": [
          -3.9384800121091694,
          -1.9974028870931764,
          -1.8430155492546954
        ]
      },
      "target_false_negative_rate": 1.0,
      "target_false_positive_rate": 0.0,
      "target_precision": 0.0,
      "target_recall": 0.0
    },
    "binary_linear_svm_unweighted": {
      "confusion_matrix": {
        "non_target": {
          "non_target": 8,
          "target": 0
        },
        "target": {
          "non_target": 3,
          "target": 0
        }
      },
      "pr_auc": 0.45833333333333326,
      "roc_auc": 0.6666666666666667,
      "score_distribution": {
        "non_target": [
          -3.508731247430079,
          -3.6033748627839044,
          -4.725768115265,
          -3.386972587338657,
          -3.9570216071707596,
          -1.9466756985133038,
          -1.276544957751173,
          -4.615082892748311
        ],
        "target": [
          -3.9384800121091694,
          -1.9974028870931764,
          -1.8430155492546954
        ]
      },
      "target_false_negative_rate": 1.0,
      "target_false_positive_rate": 0.0,
      "target_precision": 0.0,
      "target_recall": 0.0
    },
    "binary_logistic_balanced": {
      "confusion_matrix": {
        "non_target": {
          "non_target": 8,
          "target": 0
        },
        "target": {
          "non_target": 3,
          "target": 0
        }
      },
      "pr_auc": 0.4444444444444445,
      "roc_auc": 0.7083333333333334,
      "score_distribution": {
        "non_target": [
          -5.640459662932867,
          -7.462260394104697,
          -8.447280140680645,
          -6.462702291464109,
          -8.487890501131735,
          -2.9684688292643067,
          -2.3765350296111554,
          -7.9011021712955385
        ],
        "target": [
          -6.437132911835493,
          -4.149462149641176,
          -3.4035334968136923
        ]
      },
      "target_false_negative_rate": 1.0,
      "target_false_positive_rate": 0.0,
      "target_precision": 0.0,
      "target_recall": 0.0
    },
    "binary_logistic_unweighted": {
      "confusion_matrix": {
        "non_target": {
          "non_target": 8,
          "target": 0
        },
        "target": {
          "non_target": 3,
          "target": 0
        }
      },
      "pr_auc": 0.4444444444444445,
      "roc_auc": 0.7083333333333334,
      "score_distribution": {
        "non_target": [
          -5.67234355091041,
          -7.499236784970857,
          -8.479723669912792,
          -6.497489272941238,
          -8.523568880595333,
          -2.998886960278149,
          -2.4205836390247013,
          -7.938156606495888
        ],
        "target": [
          -6.471691799644582,
          -4.192706622173338,
          -3.44382373489269
        ]
      },
      "target_false_negative_rate": 1.0,
      "target_false_positive_rate": 0.0,
      "target_precision": 0.0,
      "target_recall": 0.0
    },
    "multiclass_linear_svm_balanced": {
      "validation": {
        "accuracy": 0.45454545454545453,
        "confusion_matrix": {
          "background": {
            "background": 5,
            "hard_negative_speech": 0,
            "target": 0
          },
          "hard_negative_speech": {
            "background": 3,
            "hard_negative_speech": 0,
            "target": 0
          },
          "target": {
            "background": 3,
            "hard_negative_speech": 0,
            "target": 0
          }
        },
        "target_recall": 0.0
      },
      "validation_samples": [
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_051458_8c053f",
          "target_score": -0.2706407532664334,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_051505_e29372",
          "target_score": -0.27848638723733804,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_052248_8ad611",
          "target_score": -0.28675320178607455,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053113_559726",
          "target_score": -0.2723445876318379,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053125_482797",
          "target_score": -0.28339944831300484,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053259_f86133",
          "target_score": -0.27518703290095775,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053306_a08fd8",
          "target_score": -0.2542744237677697,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053314_951f73",
          "target_score": -0.24394533321362197,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053427_3b3ebc",
          "target_score": -0.25207775095966284,
          "true_label": "hard_negative_speech"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053431_a11baf",
          "target_score": -0.21781783767221943,
          "true_label": "hard_negative_speech"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053434_c66717",
          "target_score": -0.28551947038560044,
          "true_label": "hard_negative_speech"
        }
      ]
    },
    "multiclass_linear_svm_unweighted": {
      "validation": {
        "accuracy": 0.45454545454545453,
        "confusion_matrix": {
          "background": {
            "background": 5,
            "hard_negative_speech": 0,
            "target": 0
          },
          "hard_negative_speech": {
            "background": 3,
            "hard_negative_speech": 0,
            "target": 0
          },
          "target": {
            "background": 3,
            "hard_negative_speech": 0,
            "target": 0
          }
        },
        "target_recall": 0.0
      },
      "validation_samples": [
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_051458_8c053f",
          "target_score": -0.2706407532664334,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_051505_e29372",
          "target_score": -0.27848638723733804,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_052248_8ad611",
          "target_score": -0.28675320178607455,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053113_559726",
          "target_score": -0.2723445876318379,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053125_482797",
          "target_score": -0.28339944831300484,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053259_f86133",
          "target_score": -0.27518703290095775,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053306_a08fd8",
          "target_score": -0.2542744237677697,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053314_951f73",
          "target_score": -0.24394533321362197,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053427_3b3ebc",
          "target_score": -0.25207775095966284,
          "true_label": "hard_negative_speech"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053431_a11baf",
          "target_score": -0.21781783767221943,
          "true_label": "hard_negative_speech"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053434_c66717",
          "target_score": -0.28551947038560044,
          "true_label": "hard_negative_speech"
        }
      ]
    },
    "multiclass_logistic_balanced": {
      "validation": {
        "accuracy": 0.45454545454545453,
        "confusion_matrix": {
          "background": {
            "background": 5,
            "hard_negative_speech": 0,
            "target": 0
          },
          "hard_negative_speech": {
            "background": 3,
            "hard_negative_speech": 0,
            "target": 0
          },
          "target": {
            "background": 3,
            "hard_negative_speech": 0,
            "target": 0
          }
        },
        "target_recall": 0.0
      },
      "validation_samples": [
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_051458_8c053f",
          "target_score": -3.660552907691592,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_051505_e29372",
          "target_score": -5.356556085712262,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_052248_8ad611",
          "target_score": -5.902756795616931,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053113_559726",
          "target_score": -4.669711624796499,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053125_482797",
          "target_score": -5.981915283298396,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053259_f86133",
          "target_score": -3.3777938714627522,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053306_a08fd8",
          "target_score": -3.302104243891149,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053314_951f73",
          "target_score": -2.4155523274784416,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053427_3b3ebc",
          "target_score": -1.3775845818682153,
          "true_label": "hard_negative_speech"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053431_a11baf",
          "target_score": -1.2486754779395917,
          "true_label": "hard_negative_speech"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053434_c66717",
          "target_score": -5.304508759572718,
          "true_label": "hard_negative_speech"
        }
      ]
    },
    "multiclass_logistic_unweighted": {
      "validation": {
        "accuracy": 0.36363636363636365,
        "confusion_matrix": {
          "background": {
            "background": 4,
            "hard_negative_speech": 1,
            "target": 0
          },
          "hard_negative_speech": {
            "background": 3,
            "hard_negative_speech": 0,
            "target": 0
          },
          "target": {
            "background": 2,
            "hard_negative_speech": 1,
            "target": 0
          }
        },
        "target_recall": 0.0
      },
      "validation_samples": [
        {
          "predicted_label": "hard_negative_speech",
          "recording_id": "rec_20260828_051458_8c053f",
          "target_score": -3.704033441139727,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_051505_e29372",
          "target_score": -5.3282736775104755,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_052248_8ad611",
          "target_score": -5.961226742581273,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053113_559726",
          "target_score": -4.674167268763959,
          "true_label": "background"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053125_482797",
          "target_score": -5.994934436610075,
          "true_label": "background"
        },
        {
          "predicted_label": "hard_negative_speech",
          "recording_id": "rec_20260828_053259_f86133",
          "target_score": -3.3994577647693762,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053306_a08fd8",
          "target_score": -3.172527567791952,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053314_951f73",
          "target_score": -2.296254971804593,
          "true_label": "target"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053427_3b3ebc",
          "target_score": -1.2669098404540193,
          "true_label": "hard_negative_speech"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053431_a11baf",
          "target_score": -1.1090101232480052,
          "true_label": "hard_negative_speech"
        },
        {
          "predicted_label": "background",
          "recording_id": "rec_20260828_053434_c66717",
          "target_score": -5.333484902591582,
          "true_label": "hard_negative_speech"
        }
      ]
    }
  },
  "stability": {
    "method": "leave_one_out train-only logistic binary unweighted",
    "target_correct": 9,
    "target_total": 12
  }
}

## Diagnosis
Primary bottleneck: mixed / inconclusive, with strong train/validation domain shift or sample-quality effects indicated by validation target failure. The acoustic representation improves aggregate accuracy but does not recover target recall.

## Decision and next step
Classification: G (mixed / inconclusive). Recommended next technical step: inspect and improve temporal feature aggregation on the existing audio, then rerun the fixed binary target-vs-rest diagnostic with the same validation set. This is not a readiness claim.
