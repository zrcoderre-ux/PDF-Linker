"""A nickname is the front of the name it shortens, and its fake is the front
of that name's fake.

"Ken" and "Kenneth" each drew an unrelated pool word, so one person read as
two. The longer takes precedence and the shorter is left nothing of its own:
"Ken" is "Cranston" with the same four letters dropped. Either may be drawn
first; a binding a reused key pinned never moves; and the key writes the
longer row first, since the short fake is a substring of the long one.

Run:  cd PDF-Linker && python3 -m pytest tests/test_nickname_fake.py -v
"""
import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _build(names, terms=()):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(list(names), [], list(terms),
                                          registry=reg), DET, registry=reg)
    return z, reg


def _fakes(z):
    return {str(r["real"]): str(r["fake"]) for r in z.records.values()}


def test_the_nickname_takes_the_front_of_the_full_names_fake():
    z, reg = _build(["Kenneth W. Bosworth"], ["Ken"])
    f = _fakes(z)
    long, short = f["Kenneth"], f["Ken"]
    assert long.startswith(short) and len(long) - len(short) == 4
    assert reg.nickname_swaps and reg.nickname_swaps[0][0] == "ken"
    out = z.apply("Kenneth W. Bosworth signed. Ken initialed. KEN agreed.")
    assert f"{short} initialed" in out and f"{short.upper()} agreed" in out


def test_a_nickname_harvested_after_the_full_name_takes_its_front():
    z, _reg = _build(["Kenneth W. Bosworth"])
    z.register_label_names("Attn: Ken Bosworth")
    f = _fakes(z)
    assert f["Ken Bosworth"].split()[0] == f["Kenneth"][:-4]


def test_a_pinned_nickname_never_moves():
    # A reused key pinned "Ken"; an amended template then names Kenneth.
    reg = P._PnFakeRegistry()
    tag = P._PnFakeRegistry._memo_tag("nametok")
    reg._memo[(tag, "ken")] = "Windlesham"
    reg._used.add("windlesham")
    z = P.Pseudonymizer(P._pn_build_terms(["Kenneth W. Bosworth"], [], ["Ken"],
                                          registry=reg), DET, registry=reg)
    f = _fakes(z)
    assert f["Ken"] == "Windlesham"
    assert not f["Kenneth"].startswith("Windlesham") and not reg.nickname_swaps


def test_persons_only():
    reg = P._PnFakeRegistry()
    a = reg.token("sunlight", P._PN_ENTITY_WORDS, "enttok")
    b = reg.token("sun", P._PN_ENTITY_WORDS, "enttok")
    assert not a.lower().startswith(b.lower())


def test_too_short_or_too_close_is_not_a_nickname():
    reg = P._PnFakeRegistry()
    a = reg.token("robert", P._PN_NAME_WORDS, "nametok")
    b = reg.token("ro", P._PN_NAME_WORDS, "nametok")          # two letters
    c = reg.token("rober", P._PN_NAME_WORDS, "nametok")       # one shorter
    assert not a.lower().startswith(b.lower())
    assert c.lower() != a.lower()[:-1]


def test_the_key_writes_the_longer_fake_first():
    rows = [{"real": "Ken", "fake": "Cran"}, {"real": "Other", "fake": "Pym"},
            {"real": "Kenneth", "fake": "Cranston"}]
    P._pn_key_longer_first(rows)
    assert [r["real"] for r in rows] == ["Kenneth", "Ken", "Other"]
