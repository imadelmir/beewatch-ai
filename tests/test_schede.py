"""Le card del mockup (`app/schede.py`) e la Dashboard costruita con loro (blocco 3a)."""

from __future__ import annotations

from datetime import date

from app_finta import APP, esegui, installa, servizi_finti, valori
from streamlit.testing.v1 import AppTest


def script(corpo) -> AppTest:
    return AppTest.from_function(corpo, default_timeout=30)


def html_di(at: AppTest) -> str:
    return " ".join(e.proto.body for e in at.get("html"))


def test_la_data_estesa_e_in_italiano(app_pronta):
    import schede

    assert schede.data_estesa(date(2026, 11, 14)) == "14 novembre 2026"
    assert schede.data_estesa(date(2027, 1, 1)) == "1 gennaio 2027"


def test_la_testata_ha_titolo_sottotitolo_e_una_colonna_per_le_azioni(app_pronta):
    def corpo():
        import schede
        import streamlit as st

        with schede.testata("Alveari", "Gestisci i tuoi alveari."):
            st.button("Nuovo alveare")

    at = script(corpo).run()

    assert [t.value for t in at.title] == ["Alveari"]
    assert [c.value for c in at.caption] == ["Gestisci i tuoi alveari."]
    assert [b.label for b in at.button] == ["Nuovo alveare"]


def test_la_card_kpi_e_un_metric_vero_con_la_riga_sotto(app_pronta):
    def corpo():
        import schede

        schede.scheda_kpi("alveare", "Alveari", 24, None, variazione="+2", nota="questo mese")
        schede.scheda_kpi("miele", "Produzione", 1234.5, "kg", nota="nel 2026")
        schede.scheda_kpi("salute", "Stato", "Buono", None, nota="tutti sani", evidenzia=True)

    at = script(corpo).run()

    assert [(m.label, m.value) for m in at.metric] == [
        ("Alveari", "24"), ("Produzione", "1 234,5 kg"), ("Stato", "Buono"),
    ]  # fmt: skip
    assert [m.proto.delta for m in at.metric] == ["+2", "nel 2026", "tutti sani"]
    assert at.metric[0].proto.delta_description == "questo mese"


def test_gli_elenchi_proteggono_il_testo(app_pronta):
    def corpo():
        import schede

        schede.elenco([schede.Voce("<b>A1</b> & co", "ieri", "avviso", "attenzione")], "vuoto")
        schede.elenco([], "Nessuna notifica.")

    at = script(corpo).run()

    testo = html_di(at)
    assert "&lt;b&gt;A1&lt;/b&gt; &amp; co" in testo and "<b>A1</b>" not in testo
    assert 'class="bw-elenco con-icone"' in testo and "data:image/svg+xml;base64," in testo
    assert [c.value for c in at.caption] == ["Nessuna notifica."]


def test_la_ciambella_ha_il_totale_al_centro_e_salta_le_fette_vuote(app_pronta):
    import schede

    fette = [schede.Fetta("Sani", 3, "accento"), schede.Fetta("Critici", 0, "testo2")]
    figura = schede.figura_ciambella(fette, 3)

    assert list(figura.data[0].labels) == ["Sani"]
    assert figura.data[0].hole == 0.68
    assert figura.layout.annotations[0].text == "<b>3</b>"
    assert figura.layout.paper_bgcolor == "rgba(0,0,0,0)"  # si vede la card


def test_la_legenda_dice_numeri_e_percentuali(app_pronta):
    def corpo():
        import schede

        schede.legenda_ciambella(
            [schede.Fetta("In salute", 1, "accento"), schede.Fetta("Critici", 3, "testo2")], 4
        )

    testo = html_di(script(corpo).run())
    assert "In salute" in testo and "1 (25%)" in testo and "3 (75%)" in testo


def test_larea_della_produzione_e_gialla_e_parte_da_zero(app_pronta):
    import schede

    figura = schede.figura_area(["2025", "2026"], [67.5, 29.2], "kg")

    assert figura.data[0].fill == "tozeroy" and figura.data[0].line.color == "#F5B301"
    assert figura.layout.yaxis.rangemode == "tozero" and figura.layout.xaxis.type == "category"


# --------------------------------------------------------------------------- #
# La Dashboard
# --------------------------------------------------------------------------- #


def test_la_dashboard_ha_le_parti_del_mockup(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = esegui(APP / "schermate" / "home.py")

    assert not at.exception
    assert valori(at.title) == ["Dashboard"]
    assert valori(at.caption)[0] == "Benvenuto Apicoltore, ecco il riepilogo della tua attività."
    assert [m.label for m in at.metric] == [
        "Alveari attivi", "Ispezioni (30 giorni)", "Produzione stagione", "Stato generale",
    ]  # fmt: skip
    testo = html_di(at)
    for titolo in ("Produzione registrata", "Stato alveari", "Ultime notifiche",
                   "Prossime scadenze"):  # fmt: skip
        assert titolo in testo, titolo
    assert "bw-pillola-data" in testo
    assert [b.key for b in at.main.button] == [
        "home_nuova_ispezione", "home_notifiche", "home_soglia", "home_aiuto",
    ]  # fmt: skip


def test_lo_stato_generale_segue_gli_alveari(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = esegui(APP / "schermate" / "home.py")

    stato = next(m for m in at.metric if m.label == "Stato generale")
    assert stato.value == "Attenzione"  # nei dati finti ci sono alveari da controllare


def test_nuova_ispezione_porta_alla_pagina_ispezioni(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=30)
    at.session_state["accesso"] = "Apicoltore Dimostrativo"
    at.session_state["utente_id"] = 1
    at.run()

    at = at.button(key="home_nuova_ispezione").click().run()

    assert not at.exception
    assert any("Ispezioni" in t for t in valori(at.title))
