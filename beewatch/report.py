"""I report: struttura e esportazione in CSV, XLSX e PDF (M6-T12).

Un `Report` è una fotografia: un titolo, una sintesi (coppie etichetta-valore) e alcune sezioni
(tabelle con le loro colonne). I valori restano grezzi — numeri come numeri, date come testo
«gg/mm/aaaa», mancanti come None — e ogni formato li scrive a modo suo:

- **CSV**: separatore «;» e virgola decimale, come lo apre Excel in italiano, con il BOM UTF-8
  perché gli accenti non si rompano;
- **XLSX**: un foglio per la sintesi e uno per sezione, numeri veri (si possono sommare);
- **PDF**: titolo, sintesi e tabelle, con i font standard del PDF (niente file di font da
  portarsi dietro): coprono il latino-1, quindi i pochi caratteri fuori (— … « » ’) si traducono.

Il modulo non sa nulla del database: costruisce e scrive. I report li compone `services.py`.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any

from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Font

MODELLI = {
    "mensile": "Report mensile",
    "produzione": "Analisi della produzione",
    "sanitario": "Stato sanitario",
}
FORMATI = {
    "csv": ("text/csv", "CSV"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Excel (XLSX)"),
    "pdf": ("application/pdf", "PDF"),
}
MANCANTE = "—"
AVVERTENZA = (
    "Report generato da BeeWatch AI con i dati registrati nel quaderno. Non è una diagnosi e non "
    "sostituisce il parere di un veterinario o di un tecnico apistico."
)

Valore = str | int | float | None


@dataclass(frozen=True)
class Sezione:
    titolo: str
    colonne: tuple[str, ...]
    righe: tuple[tuple[Valore, ...], ...]
    nota: str | None = None


@dataclass(frozen=True)
class Report:
    modello: str  # una chiave di MODELLI
    titolo: str
    sottotitolo: str
    sintesi: tuple[tuple[str, Valore], ...]
    sezioni: tuple[Sezione, ...]
    id: int | None = None
    creato_il: str | None = field(default=None, compare=False)  # «gg/mm/aaaa hh:mm»

    def a_dict(self) -> dict[str, Any]:
        """Il contenuto da salvare nell'archivio (senza id e data, che sono della riga)."""
        return {
            "modello": self.modello,
            "titolo": self.titolo,
            "sottotitolo": self.sottotitolo,
            "sintesi": [list(c) for c in self.sintesi],
            "sezioni": [
                {"titolo": s.titolo, "colonne": list(s.colonne),
                 "righe": [list(r) for r in s.righe], "nota": s.nota}
                for s in self.sezioni
            ],
        }  # fmt: skip

    @classmethod
    def da_dict(cls, dati: dict[str, Any], *, id: int | None = None, creato_il: str | None = None):
        return cls(
            modello=dati["modello"],
            titolo=dati["titolo"],
            sottotitolo=dati["sottotitolo"],
            sintesi=tuple((e, v) for e, v in dati["sintesi"]),
            sezioni=tuple(
                Sezione(s["titolo"], tuple(s["colonne"]), tuple(tuple(r) for r in s["righe"]),
                        s.get("nota"))
                for s in dati["sezioni"]
            ),
            id=id,
            creato_il=creato_il,
        )  # fmt: skip

    def nome_file(self, formato: str) -> str:
        base = "".join(c if c.isalnum() else "_" for c in self.titolo.lower()).strip("_")
        while "__" in base:
            base = base.replace("__", "_")
        return f"beewatch_{base}.{formato}"


def valore_scritto(valore: Valore) -> str:
    """Un valore come lo legge un italiano: «1 234,5», «—» se manca."""
    if valore is None:
        return MANCANTE
    if isinstance(valore, bool):
        return "sì" if valore else "no"
    if isinstance(valore, int):
        return f"{valore:,}".replace(",", " ")
    if isinstance(valore, float):
        return f"{valore:,.1f}".replace(",", " ").replace(".", ",")
    return str(valore)


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #


def in_csv(report: Report) -> bytes:
    """Tutto in un file: il titolo, la sintesi e le sezioni, separate da una riga vuota."""
    uscita = io.StringIO()
    scrittore = csv.writer(uscita, delimiter=";", lineterminator="\r\n")
    scrittore.writerow([report.titolo])
    scrittore.writerow([report.sottotitolo])
    scrittore.writerow([])
    scrittore.writerow(["Sintesi"])
    for etichetta, valore in report.sintesi:
        scrittore.writerow([etichetta, valore_scritto(valore)])
    for sezione in report.sezioni:
        scrittore.writerow([])
        scrittore.writerow([sezione.titolo])
        scrittore.writerow(sezione.colonne)
        for riga in sezione.righe:
            scrittore.writerow([valore_scritto(v) for v in riga])
        if sezione.nota:
            scrittore.writerow([sezione.nota])
    scrittore.writerow([])
    scrittore.writerow([AVVERTENZA])
    return uscita.getvalue().encode("utf-8-sig")


# --------------------------------------------------------------------------- #
# XLSX
# --------------------------------------------------------------------------- #


def _nome_foglio(titolo: str, usati: set[str]) -> str:
    """Excel vuole nomi di foglio unici, fino a 31 caratteri, senza []:*?/\\."""
    nome = "".join(c for c in titolo if c not in "[]:*?/\\")[:31] or "Foglio"
    base, n = nome, 2
    while nome in usati:
        nome = f"{base[:28]} {n}"
        n += 1
    usati.add(nome)
    return nome


def in_xlsx(report: Report) -> bytes:
    libro = Workbook()
    grassetto = Font(bold=True)
    usati: set[str] = set()

    foglio = libro.active
    foglio.title = _nome_foglio("Sintesi", usati)
    foglio.append([report.titolo])
    foglio["A1"].font = Font(bold=True, size=14)
    foglio.append([report.sottotitolo])
    foglio.append([])
    for etichetta, valore in report.sintesi:
        foglio.append([etichetta, valore])
    foglio.append([])
    foglio.append([AVVERTENZA])
    foglio.column_dimensions["A"].width = 42
    foglio.column_dimensions["B"].width = 24

    for sezione in report.sezioni:
        foglio = libro.create_sheet(_nome_foglio(sezione.titolo, usati))
        foglio.append(list(sezione.colonne))
        for cella in foglio[1]:
            cella.font = grassetto
        for riga in sezione.righe:
            foglio.append(list(riga))
        if sezione.nota:
            foglio.append([])
            foglio.append([sezione.nota])
        for indice, nome in enumerate(sezione.colonne):
            lettera = foglio.cell(row=1, column=indice + 1).column_letter
            foglio.column_dimensions[lettera].width = max(12, min(40, len(nome) + 4))

    uscita = io.BytesIO()
    libro.save(uscita)
    return uscita.getvalue()


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #

_SOSTITUZIONI = {"—": "-", "–": "-", "…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "€": "EUR"}


def _latino(valore: Any) -> str:
    """Il testo nei limiti dei font standard del PDF (latino-1), senza perdere il senso."""
    risultato = "".join(_SOSTITUZIONI.get(c, c) for c in str(valore))
    return risultato.encode("latin-1", errors="replace").decode("latin-1")


def in_pdf(report: Report) -> bytes:
    pdf = FPDF(orientation="portrait", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_title(_latino(report.titolo))
    pdf.set_creator("BeeWatch AI")

    pdf.set_font("helvetica", style="B", size=16)
    pdf.multi_cell(0, 8, _latino(report.titolo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", size=10)
    pdf.multi_cell(0, 6, _latino(report.sottotitolo), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    _tabella(
        pdf, "Sintesi", ("Voce", "Valore"), [(e, valore_scritto(v)) for e, v in report.sintesi]
    )
    for sezione in report.sezioni:
        righe = [[valore_scritto(v) for v in riga] for riga in sezione.righe]
        _tabella(pdf, sezione.titolo, sezione.colonne, righe or [["Nessun dato"]])
        if sezione.nota:
            pdf.set_font("helvetica", style="I", size=8)
            pdf.multi_cell(0, 4, _latino(sezione.nota), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

    pdf.ln(2)
    pdf.set_font("helvetica", style="I", size=8)
    pdf.multi_cell(0, 4, _latino(AVVERTENZA), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _tabella(pdf: FPDF, titolo: str, colonne: tuple[str, ...], righe: list) -> None:
    pdf.set_font("helvetica", style="B", size=12)
    pdf.multi_cell(0, 7, _latino(titolo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", size=9)
    with pdf.table(line_height=5, text_align="LEFT", first_row_as_headings=True) as tabella:
        intestazione = tabella.row()
        for nome in colonne:
            intestazione.cell(_latino(nome))
        for riga in righe:
            r = tabella.row()
            for valore in list(riga) + [""] * (len(colonne) - len(riga)):
                r.cell(_latino(valore))
    pdf.ln(3)


def esporta(report: Report, formato: str) -> bytes:
    """Il report nel formato chiesto (`csv`, `xlsx`, `pdf`)."""
    scrittori = {"csv": in_csv, "xlsx": in_xlsx, "pdf": in_pdf}
    if formato not in scrittori:
        raise ValueError(f"Formato sconosciuto: {formato}")
    return scrittori[formato](report)
