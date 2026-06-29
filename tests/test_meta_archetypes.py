from ptcg.meta_archetypes import classify_deck


def test_classify_deck_detects_dragapult_lucario_and_spread():
    assert classify_deck([119, 120, 121] + [1] * 57).primary == "dragapult_spread"
    assert classify_deck([673, 674, 677, 678] + [1] * 56).primary == "lucario"
    assert classify_deck([112, 235, 306, 305] + [1] * 56).primary in {"starmie_spread", "spread_unknown"}


def test_classify_deck_detects_current_top_six_meta_gates():
    assert classify_deck([878, 879, 1171, 11, 19] + [1] * 55).primary == "hop_trevenant"
    assert classify_deck([741, 742, 743, 1081, 1086] + [1] * 55).primary == "alakazam"
    assert classify_deck([1219, 1122, 1182, 11] + [1] * 56).primary == "team_rocket_petrel"
    assert classify_deck([1030, 1031, 17, 1229] + [1] * 56).primary == "mega_starmie"


def test_classify_deck_detects_archaludon_current_meta_gate():
    assert classify_deck([169, 190, 8, 1227, 1182] + [1] * 55).primary == "archaludon"
