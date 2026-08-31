from pathlib import Path

import profiles as P

BUNDLED = Path(P.__file__).parent


def test_bundled_profiles_load_and_validate():
    loaded = P.load_profiles()
    assert "generic_switch" in loaded
    assert "generic_plug_energy" in loaded
    for prof in loaded.values():
        assert prof.name
        assert prof.entities
        for ent in prof.entities:
            assert "platform" in ent
            assert isinstance(ent["dps"], dict) and ent["dps"]


def test_switch_profile_matches_a_plain_relay():
    loaded = P.load_profiles()
    best = P.suggest_profile(
        loaded, product_key=None, dps={"1"}, version="3.3"
    )
    assert best is not None
    assert best.id in ("generic_switch", "generic_2gang_switch")


def test_energy_plug_scores_above_plain_switch():
    loaded = P.load_profiles()
    dps = {"1", "18", "19", "20"}
    plug = loaded["generic_plug_energy"].score(product_key=None, dps=dps, version="3.3")
    plain = loaded["generic_switch"].score(product_key=None, dps=dps, version="3.3")
    assert plug > plain


def test_product_key_mismatch_is_rejected():
    prof = P.Profile(
        id="x",
        name="X",
        entities=[{"platform": "switch", "dps": {"switch": "1"}}],
        match={"product_key": ["abc"]},
    )
    assert prof.score(product_key="different", dps={"1"}, version=None) < 0
    assert prof.score(product_key="abc", dps={"1"}, version=None) > 0


def test_user_profile_overrides_bundled(tmp_path):
    (tmp_path / "generic_switch.yaml").write_text(
        "id: generic_switch\nname: My override\nentities:\n"
        "  - platform: switch\n    dps: {switch: '1'}\n",
        encoding="utf-8",
    )
    loaded = P.load_profiles(tmp_path)
    assert loaded["generic_switch"].name == "My override"
    assert loaded["generic_switch"].source == "user"
