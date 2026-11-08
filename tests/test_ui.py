"""Gli helper condivisi di `app/ui.py` (M6-T2).

Tre livelli, dal più rapido al più vicino all'utente:

1. **sul codice** (AST e testo): le nove funzioni del catalogo con la firma della specifica, le
   quattro usate da tutte le pagine, la palette identica al §3, l'unico HTML in `badge_stato`;
2. **funzioni pure**: numeri all'italiana, stili degli stati e loro contrasto, spiegazione degli
   errori, controllo della banda, figure Plotly;
3. **con `AppTest`**: ogni helper disegnato davvero in uno script, la sidebar su Home e pagine,
   l'apiario attivo che resta scelto cambiando pagina, gli stati vuoto ed errore di ogni pagina.

Come per M6-T1: servizi veri con repository finti (`app_finta.py`), nessun database, nessuna rete.
"""

from __future__ import annotations

import ast
import inspect
import logging
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from app_finta import (
    APP,
    PAGINE,
    RADICE,
    ApiariFinti,
    DashboardFinto,
    esegui,
    installa,
    servizi_finti,
    valori,
)
from streamlit.testing.v1 import AppTest

from beewatch import exceptions
from beewatch.exceptions import (
    BeeWatchError,
    ConfigError,
    DatabaseError,
    LLMError,
    ModelError,
    ValidationError,
)
from beewatch.models import StatoAlveare

SPEC = RADICE / "docs" / "markdown" / "M6-interfaccia" / "ui_spec.md"
UI = APP / "ui.py"
HOME = APP / "Home.py"
SCHERMATE = [HOME, *PAGINE]  # la Home e le sei pagine
# Le pagine che leggono il database (le altre leggono solo il modello di previsione).
COL_DATABASE = {p.name for p in PAGINE} - {"3_Previsione.py", "6_Trasparenza.py"}

CATALOGO = {
    "intestazione": ["titolo", "descrizione"],
    "sidebar": [],
    "banner_ai": [],
    "metrica": ["etichetta", "valore", "unita", "delta", "aiuto"],
    "badge_stato": ["stato"],
    "blocco_vuoto": ["messaggio", "azione"],
    "mostra_errore": ["eccezione"],
    "grafico_serie": ["df", "x", "y", "titolo"],
    "stima_con_incertezza": ["valore", "minimo", "massimo", "unita"],
}
USATE_DA_TUTTE = ("intestazione", "sidebar", "metrica", "mostra_errore")


@pytest.fixture
def ui(app_pronta):
    """Il modulo `ui` importato come lo importano le pagine (dopo `avvio`)."""
    import ui as modulo

    return modulo


def albero(percorso: Path) -> ast.Module:
    return ast.parse(percorso.read_text(encoding="utf-8"), filename=str(percorso))


def nomi_chiamati(percorso: Path) -> list[str]:
    return [ast.unparse(n.func) for n in ast.walk(albero(percorso)) if isinstance(n, ast.Call)]


def leggi_spec() -> str:
    return SPEC.read_text(encoding="utf-8")


def sidebar_di(at: AppTest) -> list[str]:
    """Ciò che la sidebar mostra, nell'ordine: intestazioni e didascalie."""
    return valori(at.sidebar.header) + valori(at.sidebar.caption)


# =========================================================================== #
# 1. Sul codice
# =========================================================================== #


def test_il_catalogo_del_paragrafo_8_e_quello_atteso():
    # Se la specifica cambia il catalogo, questo test lo fa notare.
    sezione = leggi_spec().split("## 8. Catalogo dei componenti")[1].split("\n## ")[0]
    nomi = re.findall(r"^\| `(\w+)\(", sezione, flags=re.M)
    assert nomi == list(CATALOGO)


@pytest.mark.parametrize("nome", CATALOGO)
def test_ogni_funzione_del_catalogo_esiste_con_la_firma_della_specifica(ui, nome):
    funzione = getattr(ui, nome)
    parametri = list(inspect.signature(funzione).parameters)
    assert parametri[: len(CATALOGO[nome])] == CATALOGO[nome]
    assert funzione.__doc__, nome  # ogni helper dice cosa fa


def test_i_parametri_facoltativi_sono_quelli_della_specifica(ui):
    firma = inspect.signature(ui.metrica).parameters
    assert firma["delta"].default is None and firma["aiuto"].default is None
    assert inspect.signature(ui.blocco_vuoto).parameters["azione"].default is None


@pytest.mark.parametrize("schermata", SCHERMATE, ids=lambda p: p.name)
@pytest.mark.parametrize("helper", USATE_DA_TUTTE)
def test_le_quattro_funzioni_comuni_sono_usate_da_ogni_schermata(schermata, helper):
    assert helper in nomi_chiamati(schermata)


@pytest.mark.parametrize("schermata", SCHERMATE, ids=lambda p: p.name)
def test_ogni_schermata_passa_gli_errori_previsti_a_mostra_errore(schermata):
    gestori = [
        n
        for n in ast.walk(albero(schermata))
        if isinstance(n, ast.ExceptHandler) and "BeeWatchError" in ast.unparse(n.type)
    ]
    assert gestori, schermata.name
    for gestore in gestori:
        chiamate = [ast.unparse(c.func) for c in ast.walk(gestore) if isinstance(c, ast.Call)]
        assert "mostra_errore" in chiamate, schermata.name


@pytest.mark.parametrize("schermata", SCHERMATE, ids=lambda p: p.name)
def test_le_schermate_non_disegnano_titoli_sidebar_ne_errori_per_conto_loro(schermata):
    # Il titolo lo mette `intestazione`, la sidebar `sidebar`, gli errori `mostra_errore`:
    # chi li scrive a mano rompe l'aspetto comune.
    chiamate = nomi_chiamati(schermata)
    assert "st.title" not in chiamate
    assert "st.error" not in chiamate
    assert not any(c.startswith("st.sidebar") for c in chiamate)
    assert "with st.sidebar" not in schermata.read_text(encoding="utf-8")


def test_il_banner_ai_e_nella_pagina_dellassistente_subito_dopo_lintestazione():
    chiamate = [c for c in nomi_chiamati(PAGINE[3]) if c in ("intestazione", "banner_ai")]
    assert PAGINE[3].name == "4_Assistente_AI.py"
    assert chiamate == ["intestazione", "banner_ai"]


def test_nessun_form_e_duplicato_tra_le_pagine():
    chiavi: list[str] = []
    for percorso in sorted(APP.rglob("*.py")):
        for nodo in ast.walk(albero(percorso)):
            if isinstance(nodo, ast.Call) and ast.unparse(nodo.func) in ("st.form", "form"):
                chiavi.append(ast.unparse(nodo.args[0]) if nodo.args else "?")
    assert len(chiavi) == len(set(chiavi)), chiavi


def test_la_palette_e_identica_al_paragrafo_3_della_specifica(ui):
    sezione = leggi_spec().split("## 3. Palette")[1].split("\n## ")[0]
    righe = dict(re.findall(r"^\| ([^|]+?) \| `(#[0-9A-F]{6})` \|", sezione, flags=re.M))
    assert righe == {
        "Primario": ui.PRIMARIO,
        "Sfondo": "#FFFFFF",
        "Sfondo secondario": ui.SFONDO_SECONDARIO,
        "Testo": ui.TESTO,
        "Testo attenuato": ui.TESTO_ATTENUATO,
        "Bordo": ui.BORDO,
        "Positivo / in salute": ui.POSITIVO,
        "Attenzione": ui.ATTENZIONE,
        "Critico": ui.CRITICO,
        "Informazione / AI": ui.INFORMAZIONE,
        "Neutro": ui.NEUTRO,
    }


def test_nessun_colore_esadecimale_fuori_dalla_palette_in_app(ui):
    ammessi = {
        ui.PRIMARIO, ui.TESTO, ui.TESTO_ATTENUATO, ui.BORDO, ui.SFONDO_SECONDARIO, ui.POSITIVO,
        ui.ATTENZIONE, ui.CRITICO, ui.INFORMAZIONE, ui.NEUTRO, "#FFFFFF",
    }  # fmt: skip
    for percorso in sorted(APP.rglob("*.py")):
        trovati = set(re.findall(r"#[0-9A-Fa-f]{6}\b", percorso.read_text(encoding="utf-8")))
        assert trovati <= ammessi, (percorso.name, trovati - ammessi)


def test_il_testo_del_banner_e_quello_del_paragrafo_9_parola_per_parola(ui):
    sezione = leggi_spec().split("## 9. Banner AI")[1].split("\n## ")[0]
    citato = re.search(r'Testo: \*"(.+?)"\*', sezione, flags=re.S).group(1)
    assert ui.TESTO_BANNER_AI == " ".join(citato.split())


def test_ogni_eccezione_del_progetto_ha_una_spiegazione(ui):
    classi = {
        c
        for _, c in inspect.getmembers(exceptions, inspect.isclass)
        if issubclass(c, BeeWatchError)
    }
    spiegate = {classe for classe, _, _ in ui.SPIEGAZIONI_ERRORE}
    assert classi == spiegate
    assert ui.SPIEGAZIONI_ERRORE[-1][0] is BeeWatchError  # la generica è l'ultima


# =========================================================================== #
# 2. Funzioni pure
# =========================================================================== #


@pytest.mark.parametrize(
    ("valore", "decimali", "atteso"),
    [
        (4, None, "4"),
        (1234, None, "1 234"),
        (1234.5, None, "1 234,5"),
        (Decimal("1234.50"), None, "1 234,5"),
        (3.499, 1, "3,5"),
        (-2.25, 2, "-2,25"),
        (0, None, "0"),
        (None, None, "—"),
        (float("nan"), None, "—"),
        (True, None, "—"),  # un booleano non è un numero da mostrare
    ],
)
def test_formatta_numero_scrive_allitaliana(ui, valore, decimali, atteso):
    assert ui.formatta_numero(valore, decimali) == atteso


@pytest.mark.parametrize("stato", list(StatoAlveare))
def test_ogni_stato_dellalveare_ha_etichetta_icona_e_colore(ui, stato):
    etichetta, icona, sfondo, testo = ui.stile_stato(stato)
    assert etichetta and icona  # il colore non è mai l'unico veicolo (§3)
    assert ui.stile_stato(stato.value) == ui.stile_stato(stato)  # anche dal codice del database
    assert sfondo in {ui.POSITIVO, ui.ATTENZIONE, ui.CRITICO, ui.NEUTRO}


def test_gli_stati_hanno_il_significato_della_palette(ui):
    assert ui.stile_stato(StatoAlveare.IN_SALUTE)[2] == ui.POSITIVO
    assert ui.stile_stato(StatoAlveare.MORTO)[2] == ui.CRITICO  # «alveare perso»
    for stato in (StatoAlveare.IN_OSSERVAZIONE, StatoAlveare.DEBOLE, StatoAlveare.SCIAMATO):
        assert ui.stile_stato(stato)[2] == ui.ATTENZIONE
    assert len({ui.stile_stato(s)[0] for s in StatoAlveare}) == len(StatoAlveare)


@pytest.mark.parametrize("ignoto", [None, "", "boh", 3])
def test_uno_stato_ignoto_e_neutro_e_dichiarato_come_tale(ui, ignoto):
    assert ui.stile_stato(ignoto) == ("Stato sconosciuto", "?", ui.NEUTRO, "#FFFFFF")


def _luminanza(esadecimale: str) -> float:
    canali = [int(esadecimale[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lineari = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canali]
    return 0.2126 * lineari[0] + 0.7152 * lineari[1] + 0.0722 * lineari[2]


def _contrasto(a: str, b: str) -> float:
    chiaro, scuro = sorted((_luminanza(a), _luminanza(b)), reverse=True)
    return (chiaro + 0.05) / (scuro + 0.05)


@pytest.mark.parametrize("stato", [*StatoAlveare, None])
def test_il_testo_dei_badge_si_legge_contrasto_wcag_aa(ui, stato):
    _, _, sfondo, testo = ui.stile_stato(stato)
    assert _contrasto(sfondo, testo) >= 4.5


@pytest.mark.parametrize(
    ("eccezione", "titolo"),
    [
        (ConfigError("x"), "La configurazione non è valida."),
        (DatabaseError("x"), "Non riesco a raggiungere il database."),
        (ValidationError("x", campo="peso_kg"), "Un dato inserito non è valido."),
        (ModelError("x"), "Il modello di previsione non è disponibile."),
        (LLMError("x"), "L'assistente AI non ha risposto come doveva."),
        (exceptions.ETLError("x"), "I dati storici USDA non sono stati caricati."),
        (BeeWatchError("x"), "Qualcosa non è andato come previsto."),
        (RuntimeError("x"), "Errore imprevisto."),
    ],
)
def test_spiega_errore_sceglie_la_classe_piu_specifica(ui, eccezione, titolo):
    trovato, rimedio = ui.spiega_errore(eccezione)
    assert trovato == titolo
    assert rimedio.endswith(".")  # sempre un'azione, scritta per intero


@pytest.mark.parametrize(
    ("valore", "minimo", "massimo"),
    [
        (30, None, 40),
        (30, 20, None),
        (30, None, None),
        (30, 40, 20),  # banda rovesciata
        (50, 20, 40),  # stima fuori dalla sua banda
        (10, 20, 40),
    ],
)
def test_una_stima_senza_banda_valida_non_si_puo_mostrare(ui, valore, minimo, massimo):
    with pytest.raises(ValueError):
        ui.controlla_banda(valore, minimo, massimo)


@pytest.mark.parametrize(
    ("valore", "minimo", "massimo"), [(30, 20, 40), (20, 20, 40), (None, 20, 40), (5, 5, 5)]
)
def test_una_banda_valida_passa_anche_senza_il_valore_centrale(ui, valore, minimo, massimo):
    ui.controlla_banda(valore, minimo, massimo)


def test_la_figura_della_serie_ha_assi_con_unita_e_colori_della_palette(ui):
    df = pd.DataFrame(
        {
            "anno": [2024, 2023, 2024, 2023],
            "kg": [30.0, 25.0, 12.0, 18.0],
            "alveare": ["A1", "A1", "B2", "B2"],
        }
    )
    figura = ui.figura_serie(
        df, "anno", "kg", "Produzione", etichetta_x="Anno", etichetta_y="Produzione (kg)",
        gruppo="alveare",
    )  # fmt: skip
    assert figura.layout.xaxis.title.text == "Anno"
    assert figura.layout.yaxis.title.text == "Produzione (kg)"
    assert figura.layout.title.text == "Produzione"
    assert [t.line.color for t in figura.data] == [ui.PRIMARIO, ui.TESTO]
    assert len({t.marker.symbol for t in figura.data}) == 2  # non solo il colore
    assert list(figura.data[0].x) == [2023, 2024]  # ordinata nel tempo


def test_la_figura_della_stima_ha_la_banda_derrore_asimmetrica(ui):
    figura = ui.figura_stima(30, 22, 41, "kg", "Produzione stimata")
    barra = figura.data[0]
    assert list(barra.x) == [30.0] and barra.orientation == "h"
    assert list(barra.error_x.array) == [11.0] and list(barra.error_x.arrayminus) == [8.0]
    assert figura.layout.xaxis.title.text == "Produzione (kg)"


def test_senza_valore_centrale_la_figura_mostra_solo_la_banda(ui):
    barra = ui.figura_stima(None, 22, 41, "kg", "Produzione stimata").data[0]
    assert list(barra.base) == [22.0] and list(barra.x) == [19.0]
    assert barra.error_x.array is None


def test_la_figura_della_stima_rifiuta_una_banda_assente(ui):
    with pytest.raises(ValueError):
        ui.figura_stima(30, None, 41, "kg", "x")


# =========================================================================== #
# 3. Con AppTest: ogni helper disegnato davvero
# =========================================================================== #


def script(corpo):
    """Un AppTest da una funzione: `corpo` importa `ui` e chiama l'helper da provare."""
    return AppTest.from_function(corpo, default_timeout=30)


def test_intestazione_mette_un_titolo_e_la_riga_di_contesto(app_pronta):
    def corpo():
        import ui

        ui.intestazione("🏠 Alveari", "Le arnie dell'apiario attivo.")

    at = script(corpo).run()
    assert valori(at.title) == ["🏠 Alveari"]
    assert valori(at.markdown) == ["Le arnie dell'apiario attivo."]


def test_banner_ai_e_un_avviso_blu_non_richiudibile(app_pronta):
    def corpo():
        import ui

        ui.banner_ai()

    at = script(corpo).run()
    [banner] = at.info
    assert banner.value.startswith("Il riepilogo qui sotto è generato da un'intelligenza")
    assert banner.icon == "🤖"
    assert not at.expander  # non nascondibile (§9)


def test_metrica_formatta_valore_unita_delta_e_aiuto(app_pronta):
    def corpo():
        import ui

        ui.metrica("Produzione", 1234.5, "kg", delta=-2.5, aiuto="Stagione in corso.")
        ui.metrica("Alveari", 4, None)
        ui.metrica("Peso", None, "kg", delta=None)
        ui.metrica("Crescita", 12, "kg", delta=3)
        ui.metrica("Scarto", 5, "kg", delta=float("nan"))

    at = script(corpo).run()
    produzione, alveari, peso, crescita, scarto = at.metric
    assert (produzione.label, produzione.value, produzione.delta) == (
        "Produzione",
        "1 234,5 kg",
        "-2,5 kg",
    )
    assert produzione.help == "Stagione in corso."
    assert alveari.value == "4" and not alveari.delta
    assert peso.value == "—"  # mancante: mai uno zero inventato
    assert crescita.delta == "+3 kg"
    assert not scarto.delta  # un delta mancante non si mostra


@pytest.mark.parametrize("stato", list(StatoAlveare))
def test_badge_stato_disegna_pastiglia_con_icona_testo_e_colore(ui, stato):
    def corpo():
        import streamlit as st
        import ui

        ui.badge_stato(st.session_state["stato"])

    at = script(corpo)
    at.session_state["stato"] = stato.value
    at.run()
    etichetta, icona, sfondo, _ = ui.stile_stato(stato)
    [pastiglia] = valori(at.markdown)
    assert f"{icona} {etichetta}" in pastiglia
    assert f"background:{sfondo}" in pastiglia
    assert pastiglia.startswith("<span") and pastiglia.endswith("</span>")


def test_blocco_vuoto_mostra_messaggio_e_azione(app_pronta):
    def corpo():
        import ui

        ui.blocco_vuoto("Nessun alveare registrato.", "Vai su Alveari per aggiungerne uno.")
        ui.blocco_vuoto("Nessun dato.")

    at = script(corpo).run()
    con_azione, senza = valori(at.info)
    assert con_azione.startswith("Nessun alveare registrato.")
    assert "**Cosa puoi fare:** Vai su Alveari per aggiungerne uno." in con_azione
    assert senza == "Nessun dato."


def test_mostra_errore_traduce_una_beewatcherror_in_italiano_con_il_rimedio(app_pronta, caplog):
    def corpo():
        import ui

        from beewatch.exceptions import ValidationError

        ui.mostra_errore(ValidationError("Il peso non può essere negativo.", campo="peso_kg"))

    with caplog.at_level(logging.WARNING, logger="beewatch.app.ui"):
        at = script(corpo).run()
    [errore] = valori(at.error)
    assert errore == (
        "**Un dato inserito non è valido.** Il peso non può essere negativo. (campo «peso_kg»)"
        "\n\nCorreggi il campo indicato e riprova."
    )
    assert not at.exception and not at.code  # nessun traceback a schermo
    assert any("ValidationError" in r.getMessage() for r in caplog.records)


def test_mostra_errore_non_mostra_il_messaggio_di_un_errore_imprevisto(app_pronta, caplog):
    def corpo():
        import ui

        ui.mostra_errore(KeyError("SELECT * FROM utenti WHERE password=..."))

    with caplog.at_level(logging.ERROR, logger="beewatch.app.ui"):
        at = script(corpo).run()
    [errore] = valori(at.error)
    assert errore.startswith("**Errore imprevisto.**")
    assert "SELECT" not in errore  # il dettaglio tecnico va nel log, non a schermo
    [riga] = [r for r in caplog.records if r.getMessage() == "Errore non gestito"]
    assert riga.exc_info is not None  # nel log, con lo stack


def test_grafico_serie_disegna_il_grafico_e_la_fonte(app_pronta):
    def corpo():
        import pandas as pd
        import ui

        df = pd.DataFrame({"anno": [2023, 2024], "kg": [25.0, 30.0]})
        ui.grafico_serie(
            df, "anno", "kg", "Produzione", etichetta_x="Anno", etichetta_y="Produzione (kg)",
            fonte="Raccolti registrati nel quaderno",
        )  # fmt: skip

    at = script(corpo).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 1
    assert valori(at.caption) == ["Fonte: Raccolti registrati nel quaderno"]


def test_grafico_serie_senza_dati_mostra_lo_stato_vuoto(app_pronta):
    def corpo():
        import pandas as pd
        import ui

        vuoto = pd.DataFrame({"anno": [], "kg": []})
        ui.grafico_serie(vuoto, "anno", "kg", "P", etichetta_x="Anno", etichetta_y="kg", fonte="f")

    at = script(corpo).run()
    assert not at.get("plotly_chart")
    assert valori(at.info) == ["Non ci sono ancora dati da mettere nel grafico."]


def test_stima_con_incertezza_mostra_valore_banda_grafico_e_avvertenza(app_pronta):
    def corpo():
        import ui

        ui.stima_con_incertezza(31, 22, 41, "kg", livello=0.8)

    at = script(corpo).run()
    [stima] = at.metric
    assert (stima.label, stima.value) == ("Produzione stimata", "31 kg")
    didascalie = valori(at.caption)
    assert didascalie[0] == "Banda di incertezza: da 22 a 41 kg (intervallo al 80%)."
    assert didascalie[-1].startswith("È una stima statistica")
    assert len(at.get("plotly_chart")) == 1


def test_stima_senza_valore_centrale_mostra_solo_la_banda(app_pronta):
    def corpo():
        import ui

        ui.stima_con_incertezza(None, 22, 41, "kg")

    at = script(corpo).run()
    [stima] = at.metric
    assert stima.value == "da 22 a 41 kg"
    assert "31" not in " ".join(valori(at.caption))


def test_stima_senza_banda_si_ferma_prima_di_disegnare(app_pronta):
    def corpo():
        import ui

        ui.stima_con_incertezza(31, None, 41, "kg")

    at = script(corpo).run()
    assert at.exception  # un errore di programmazione: deve vedersi in sviluppo
    assert not at.metric and not at.get("plotly_chart")


# =========================================================================== #
# 3b. La sidebar e l'apiario attivo
# =========================================================================== #


def test_la_sidebar_ha_identita_apiario_attivo_e_stato_del_sistema(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = esegui(HOME)

    assert not at.exception
    assert valori(at.sidebar.header) == ["🐝 BeeWatch AI"]
    [selettore] = at.sidebar.selectbox
    assert selettore.label == "Apiario attivo"
    assert selettore.options == ["Collina", "Valle"] and selettore.value == 10
    assert valori(at.sidebar.caption) == [
        "Versione 0.1.0",
        "**Modello:** v-stub (RandomForestRegressor)",
        "**Assistente AI:** llama3.1:8b via ollama (chiave: non richiesta)",
        "**Database:** connesso",
    ]
    assert len(at.sidebar.divider) == 1


def test_la_sidebar_e_identica_su_tutte_le_schermate(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    viste = {p.name: sidebar_di(esegui(p)) for p in SCHERMATE}

    assert len({tuple(v) for v in viste.values()}) == 1, viste


def test_cambiare_apiario_aggiorna_lo_stato_e_ogni_pagina(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())
    at = esegui(HOME)

    at.sidebar.selectbox[0].select(11).run()

    assert at.session_state["apiario_attivo_id"] == 11
    assert "Apiario attivo: **Valle** · 2 in tutto" in valori(at.caption)
    for pagina in PAGINE:  # la scelta sopravvive al cambio di pagina, in ogni direzione
        at.switch_page(str(pagina.relative_to(APP))).run()
        assert not at.exception, pagina.name
        assert at.session_state["apiario_attivo_id"] == 11, pagina.name
        assert at.sidebar.selectbox[0].value == 11, pagina.name
    at.switch_page("Home.py").run()
    assert at.sidebar.selectbox[0].value == 11


def test_senza_apiari_la_sidebar_lo_dice_e_non_mostra_il_selettore(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti(apiari=ApiariFinti(())))

    at = esegui(HOME)

    assert not at.sidebar.selectbox
    assert "Apiario attivo: nessuno. Nessun apiario registrato." in valori(at.sidebar.caption)
    assert "**Database:** connesso" in valori(at.sidebar.caption)


def test_se_il_database_non_risponde_la_sidebar_lo_dice_e_la_pagina_mostra_lerrore(
    app_pronta, monkeypatch
):
    giu = DatabaseError("Il server MySQL non risponde.")
    installa(
        app_pronta,
        monkeypatch,
        servizi_finti(dashboard=DashboardFinto(giu), apiari=ApiariFinti(errore=giu)),
    )

    at = esegui(HOME)

    assert not at.exception
    assert "**Database:** non raggiungibile" in valori(at.sidebar.caption)
    assert not at.sidebar.selectbox
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")


def test_se_il_modello_manca_la_sidebar_lo_dice(app_pronta, monkeypatch):
    def manca():
        raise ModelError("Il modello non è stato trovato.")

    installa(app_pronta, monkeypatch, servizi_finti(crea_predittore=manca))

    at = esegui(PAGINE[0])

    assert not at.exception
    assert "**Modello:** non disponibile" in valori(at.sidebar.caption)


# =========================================================================== #
# 3c. Gli stati di ogni pagina: con dati, vuoto, errore (specifica §11)
# =========================================================================== #


@pytest.mark.parametrize("pagina", PAGINE, ids=lambda p: p.name)
def test_ogni_pagina_con_dati_ha_intestazione_e_un_numero_di_contesto(
    app_pronta, monkeypatch, pagina
):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = esegui(pagina)

    assert not at.exception
    assert len(at.title) == 1 and len(at.markdown) >= 1  # titolo e riga di contesto
    assert at.metric and not at.error
    assert all(m.value not in ("", "—") for m in at.metric)


def test_solo_la_pagina_dellassistente_ha_il_banner_ai(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    con_banner = [p.name for p in SCHERMATE if any(i.icon == "🤖" for i in esegui(p).info)]

    assert con_banner == ["4_Assistente_AI.py"]


@pytest.mark.parametrize("pagina", PAGINE, ids=lambda p: p.name)
def test_ogni_pagina_regge_il_database_spento(app_pronta, monkeypatch, pagina):
    giu = DatabaseError("Il server MySQL non risponde.")
    installa(
        app_pronta,
        monkeypatch,
        servizi_finti(dashboard=DashboardFinto(giu), apiari=ApiariFinti(errore=giu)),
    )

    at = esegui(pagina)

    assert not at.exception
    assert len(at.title) == 1
    if pagina.name in COL_DATABASE:
        [errore] = valori(at.error)
        assert errore.startswith("**Non riesco a raggiungere il database.**")
        assert not at.metric  # niente numeri inventati
    else:  # Previsione e Trasparenza leggono solo il modello
        assert not at.error


@pytest.mark.parametrize("pagina", PAGINE, ids=lambda p: p.name)
def test_ogni_pagina_regge_il_modello_mancante(app_pronta, monkeypatch, pagina):
    def manca():
        raise ModelError("Il modello non è stato trovato: lancia scripts/train_model.py.")

    installa(app_pronta, monkeypatch, servizi_finti(crea_predittore=manca))

    at = esegui(pagina)

    assert not at.exception
    if "modello()" in pagina.read_text(encoding="utf-8"):
        [errore] = valori(at.error)
        assert errore.startswith("**Il modello di previsione non è disponibile.**")
    else:
        assert not at.error


@pytest.mark.parametrize("pagina", PAGINE, ids=lambda p: p.name)
def test_ogni_pagina_regge_il_database_vuoto(app_pronta, monkeypatch, pagina):
    installa(app_pronta, monkeypatch, servizi_finti(apiari=ApiariFinti(())))

    at = esegui(pagina)

    assert not at.exception and not at.error
    if pagina.name in COL_DATABASE:
        assert any(t.startswith("Nessun apiario registrato.") for t in valori(at.info))
