"""La struttura dei report e le tre esportazioni: CSV, XLSX, PDF (M6-T12)."""

from __future__ import annotations

import csv
import io

import pytest
from openpyxl import load_workbook

from beewatch.report import (
    AVVERTENZA,
    FORMATI,
    MODELLI,
    Report,
    Sezione,
    _latino,
    _nome_foglio,
    esporta,
    in_csv,
    in_pdf,
    in_xlsx,
    valore_scritto,
)

REPORT = Report(
    modello="mensile",
    titolo="Report mensile · Apiario del Noce · ottobre 2026",
    sottotitolo="Apiario del Noce, dal 01/10/2026 al 31/10/2026 — «prova»",
    sintesi=(("Ispezioni", 2), ("Miele raccolto (kg)", 1234.5), ("Ultima", None)),
    sezioni=(
        Sezione(
            "Ispezioni del mese",
            ("Data", "Alveare", "Rischio", "Peso (kg)"),
            (
                ("05/10/2026", "A2", "Rischio alto", None),
                ("30/10/2026", "A1", "Rischio basso", 38.5),
            ),
        ),
        Sezione("Raccolti del mese", ("Data", "Miele (kg)"), (), nota="Nessuna smielatura."),
    ),
)


def test_i_modelli_e_i_formati_sono_quelli_della_issue():
    assert list(MODELLI) == ["mensile", "produzione", "sanitario"]
    assert list(FORMATI) == ["csv", "xlsx", "pdf"]


@pytest.mark.parametrize(
    ("valore", "atteso"),
    [(None, "—"), (2, "2"), (12345, "12 345"), (1234.5, "1 234,5"), (True, "sì"), ("A1", "A1")],
)
def test_i_valori_si_scrivono_allitaliana(valore, atteso):
    assert valore_scritto(valore) == atteso


def test_il_contenuto_si_salva_e_si_rilegge_identico():
    copia = Report.da_dict(REPORT.a_dict(), id=7, creato_il="14/11/2026 10:00")

    assert copia.a_dict() == REPORT.a_dict()  # il contenuto torna identico
    assert copia.id == 7 and copia.sezioni[1].nota == "Nessuna smielatura."


def test_il_nome_del_file_e_pulito():
    assert REPORT.nome_file("pdf") == "beewatch_report_mensile_apiario_del_noce_ottobre_2026.pdf"


def test_il_csv_e_per_excel_in_italiano():
    dati = in_csv(REPORT)

    assert dati.startswith(b"\xef\xbb\xbf")  # BOM: gli accenti non si rompono in Excel
    righe = list(csv.reader(io.StringIO(dati.decode("utf-8-sig")), delimiter=";"))
    assert righe[0] == [REPORT.titolo]
    assert ["Miele raccolto (kg)", "1 234,5"] in righe  # virgola decimale
    assert ["Data", "Alveare", "Rischio", "Peso (kg)"] in righe
    assert ["05/10/2026", "A2", "Rischio alto", "—"] in righe
    assert ["Nessuna smielatura."] in righe and righe[-1] == [AVVERTENZA]


def test_lxlsx_ha_un_foglio_per_sezione_e_numeri_veri():
    libro = load_workbook(io.BytesIO(in_xlsx(REPORT)))

    assert libro.sheetnames == ["Sintesi", "Ispezioni del mese", "Raccolti del mese"]
    sintesi = libro["Sintesi"]
    assert sintesi["A1"].value == REPORT.titolo and sintesi["A1"].font.bold
    assert sintesi["B5"].value == 1234.5  # un numero, non il testo «1 234,5»
    ispezioni = libro["Ispezioni del mese"]
    assert [c.value for c in ispezioni[1]] == ["Data", "Alveare", "Rischio", "Peso (kg)"]
    assert ispezioni[1][0].font.bold
    assert [c.value for c in ispezioni[3]] == ["30/10/2026", "A1", "Rischio basso", 38.5]


def test_i_nomi_dei_fogli_rispettano_le_regole_di_excel():
    usati: set[str] = set()

    assert _nome_foglio("Per anno: tipo/miele [kg]?", usati) == "Per anno tipomiele kg"
    assert _nome_foglio("x" * 40, usati) == "x" * 31
    assert _nome_foglio("x" * 40, usati) == "x" * 28 + " 2"  # unico


def test_il_pdf_e_un_pdf_e_regge_ogni_carattere():
    dati = in_pdf(REPORT)

    assert dati.startswith(b"%PDF-") and dati.rstrip().endswith(b"%%EOF")
    assert len(dati) > 1000


@pytest.mark.parametrize(
    ("originale", "atteso"),
    [("a — b … ’x’ €", "a - b ... 'x' EUR"), ("àèìòù «»·", "àèìòù «»·"), ("🐝", "?")],
)
def test_il_testo_del_pdf_resta_nei_font_standard(originale, atteso):
    assert _latino(originale) == atteso


def test_un_report_vuoto_si_esporta_lo_stesso():
    vuoto = Report(
        "sanitario", "Stato sanitario · Valle", "nulla", (), (Sezione("Alveari", ("A",), ()),)
    )

    for formato in FORMATI:
        assert esporta(vuoto, formato)


def test_un_formato_sconosciuto_e_un_errore_di_programmazione():
    with pytest.raises(ValueError, match="Formato sconosciuto"):
        esporta(REPORT, "docx")
