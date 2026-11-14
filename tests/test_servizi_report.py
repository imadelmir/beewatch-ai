"""I tre modelli di report e l'archivio (M6-T12).

Unitari con anagrafica, ispezioni, raccolti e archivio in memoria; «oggi» è fissato al
14/11/2026, così i giorni dall'ultima ispezione non cambiano col calendario. In fondo, su MySQL:
schema, archivio, cancellazione a cascata con l'utente.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from anagrafica_finta import anagrafica_di_prova, ispezioni_di_prova, raccolti_di_prova
from report_finto import ReportInMemoria

from beewatch.database import Database
from beewatch.exceptions import ValidationError
from beewatch.models import Apiario
from beewatch.repositories import ApiariRepository
from beewatch.repositories_riferimento import ReportRepository, UtentiRepository
from beewatch.services import Servizi

OGGI = date(2026, 11, 14)
COLLINA = 10


def servizi() -> tuple[Servizi, ReportInMemoria]:
    apiari, alveari = anagrafica_di_prova()
    archivio = ReportInMemoria()
    s = Servizi(
        None,
        apiari=apiari,
        alveari=alveari,
        ispezioni=ispezioni_di_prova(alveari),
        raccolti=raccolti_di_prova(apiari),
        report=archivio,
    )
    return s, archivio


def sintesi(report) -> dict:
    return dict(report.sintesi)


# --------------------------------------------------------------------------- #
# I tre modelli
# --------------------------------------------------------------------------- #


def test_il_report_mensile_di_ottobre():
    s, _ = servizi()

    r = s.crea_report(1, COLLINA, "mensile", anno=2026, mese=10, oggi=OGGI)

    assert r.titolo == "Report mensile · Collina · ottobre 2026"
    assert sintesi(r) == {
        "Apiario": "Collina",
        "Periodo": "ottobre 2026",
        "Ispezioni": 2,
        "Alveari ispezionati": "2 di 2",
        "Ispezioni con rischio medio o alto": 1,
        "Miele raccolto (kg)": 0.0,
    }
    ispezioni, raccolti = r.sezioni
    assert [riga[:3] for riga in ispezioni.righe] == [
        ("05/10/2026", "A2", "Rischio alto"),  # in ordine di data
        ("30/10/2026", "A1", "Rischio basso"),
    ]
    assert ispezioni.righe[1][3] == 38.5 and ispezioni.righe[1][7] == "sì"  # peso, sciamatura
    assert raccolti.righe == ()


def test_il_report_mensile_di_maggio_ha_i_raccolti():
    s, _ = servizi()

    r = s.crea_report(1, COLLINA, "mensile", anno=2026, mese=5, oggi=OGGI)

    assert sintesi(r)["Miele raccolto (kg)"] == 29.2 and sintesi(r)["Ispezioni"] == 0
    assert r.sezioni[1].righe == (("30/05/2026", "Acacia", "Intero apiario", 29.2),)


def test_lanalisi_della_produzione():
    s, _ = servizi()

    r = s.crea_report(1, COLLINA, "produzione", oggi=OGGI)

    assert r.titolo == "Analisi della produzione · Collina"
    assert sintesi(r) == {
        "Apiario": "Collina",
        "Miele raccolto in tutto (kg)": 102.5,  # i 99 kg di un altro utente non ci sono
        "Anni con raccolti": 2,
        "Alveari attivi": 2,
        "Media per alveare (kg)": 51.25,
        "Anno migliore": "2025 (68,3 kg)",
    }
    per_tipo, per_alveare = r.sezioni
    assert per_tipo.righe == (
        (2025, "Acacia", 34.5),
        (2025, "Castagno", 21.0),
        (2025, "Millefiori", 12.8),
        (2026, "Acacia", 34.2),
    )
    assert dict(per_alveare.righe)["Intero apiario"] == 84.7
    assert "Intero apiario" in per_alveare.nota


def test_lo_stato_sanitario():
    s, _ = servizi()

    r = s.crea_report(1, COLLINA, "sanitario", oggi=OGGI)

    assert sintesi(r) == {
        "Apiario": "Collina",
        "Alveari attivi": 2,
        "In salute": 1,
        "Da controllare (mai o da oltre 30 giorni)": 1,  # A2: ultima il 05/10, 40 giorni fa
        "Con rischio medio o alto all'ultima ispezione": 1,
    }
    [alveari] = r.sezioni
    assert alveari.righe == (
        ("A1", "In salute", "30/10/2026", 15, "Rischio basso", 38.5),
        ("A2", "Debole", "05/10/2026", 40, "Rischio alto", None),
    )
    assert "non una diagnosi" in alveari.nota


def test_un_apiario_vuoto_da_report_vuoti_ma_onesti():
    s, _ = servizi()

    sanitario = s.crea_report(1, 11, "sanitario", oggi=OGGI)  # «Valle»
    produzione = s.crea_report(1, 11, "produzione", oggi=OGGI)

    assert sanitario.sezioni[0].righe == () and sintesi(sanitario)["Alveari attivi"] == 0
    assert sintesi(produzione)["Anno migliore"] is None
    assert sintesi(produzione)["Media per alveare (kg)"] is None


@pytest.mark.parametrize(
    ("argomenti", "campo"),
    [
        ({"modello": "settimanale"}, "modello"),
        ({"apiario_id": 20}, "apiario_id"),  # di un altro utente
        ({"mese": 13}, "mese"),
        ({"mese": 0}, "mese"),
        ({"anno": 1999}, "anno"),
        ({"anno": 2027}, "anno"),  # nel futuro rispetto a «oggi»
    ],
)
def test_gli_errori_dicono_il_campo(argomenti, campo):
    s, archivio = servizi()
    chiamata = {"apiario_id": COLLINA, "modello": "mensile", "anno": 2026, "mese": 10, **argomenti}

    with pytest.raises(ValidationError) as errore:
        s.crea_report(1, chiamata.pop("apiario_id"), chiamata.pop("modello"), oggi=OGGI, **chiamata)
    assert errore.value.campo == campo
    assert archivio.righe == {}


# --------------------------------------------------------------------------- #
# Archivio ed esportazione
# --------------------------------------------------------------------------- #


def test_ogni_report_creato_va_nellarchivio_e_si_riapre_identico():
    s, _ = servizi()
    primo = s.crea_report(1, COLLINA, "sanitario", oggi=OGGI)
    secondo = s.crea_report(1, COLLINA, "produzione", oggi=OGGI)

    archivio = s.archivio_report(1)

    assert [v.id for v in archivio] == [secondo.id, primo.id]
    assert archivio[0].titolo == "Analisi della produzione · Collina"
    assert archivio[0].creato_il == "14/11/2026 10:02"
    riaperto = s.report_salvato(1, primo.id)
    assert riaperto.a_dict() == primo.a_dict() and riaperto.id == primo.id


def test_un_report_salvato_resta_una_fotografia():
    s, _ = servizi()
    prima = s.crea_report(1, COLLINA, "produzione", oggi=OGGI)
    s._raccolti.righe.clear()  # i dati cambiano dopo

    assert s.report_salvato(1, prima.id).a_dict() == prima.a_dict()


def test_i_report_degli_altri_non_si_vedono_ne_si_cancellano():
    s, _ = servizi()
    r = s.crea_report(1, COLLINA, "sanitario", oggi=OGGI)

    assert s.archivio_report(2) == []
    with pytest.raises(ValidationError):
        s.report_salvato(2, r.id)
    with pytest.raises(ValidationError):
        s.elimina_report(2, r.id)


def test_eliminare_un_report():
    s, archivio = servizi()
    r = s.crea_report(1, COLLINA, "sanitario", oggi=OGGI)

    s.elimina_report(1, r.id)

    assert archivio.righe == {} and s.archivio_report(1) == []


def test_lesportazione_passa_dal_servizio_e_rifiuta_i_formati_ignoti():
    s, _ = servizi()
    r = s.crea_report(1, COLLINA, "sanitario", oggi=OGGI)

    assert s.esporta_report(r, "pdf").startswith(b"%PDF")
    with pytest.raises(ValidationError) as errore:
        s.esporta_report(r, "docx")
    assert errore.value.campo == "formato"


# --------------------------------------------------------------------------- #
# Con MySQL vero
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_integrazione_archivio_e_cancellazione_con_lutente(database_test: Database):
    with database_test.transazione() as cursore:
        cursore.execute(
            "INSERT INTO utenti (email, nome_completo, hash_password) VALUES (%s, %s, %s)",
            (f"report-{uuid.uuid4().hex}@beewatch.test", "Utente di prova", "x" * 60),
        )
        utente = cursore.lastrowid
    apiario = ApiariRepository(database_test).crea(Apiario(utente_id=utente, nome="Prova"))
    s = Servizi(database_test)

    r = s.crea_report(utente, apiario.id, "sanitario")

    assert [v.id for v in s.archivio_report(utente)] == [r.id]
    assert s.report_salvato(utente, r.id).a_dict() == r.a_dict()  # JSON identico, accenti compresi
    assert ReportRepository(database_test).elenco(utente)[0]["apiario_id"] == apiario.id
    UtentiRepository(database_test).elimina(utente)  # GDPR art. 17: spariscono anche i report
    with database_test.transazione() as cursore:
        cursore.execute("SELECT COUNT(*) AS n FROM report WHERE utente_id = %s", (utente,))
        assert cursore.fetchone()["n"] == 0


@pytest.mark.integration
def test_integrazione_i_tre_report_sullapiario_del_seed(database_test: Database):
    s = Servizi(database_test)
    apiario = s.elenca_apiari(1)[0].id
    creati = []
    try:
        for modello in ("mensile", "produzione", "sanitario"):
            r = s.crea_report(1, apiario, modello, anno=2026, mese=5)
            creati.append(r.id)
            for formato in ("csv", "xlsx", "pdf"):
                assert s.esporta_report(r, formato)
        produzione = s.report_salvato(1, creati[1])
        assert dict(produzione.sintesi)["Miele raccolto in tutto (kg)"] == pytest.approx(97.5)
    finally:
        for identificativo in creati:
            s.elimina_report(1, identificativo)
