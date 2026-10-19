"""Test dell'ETL USDA: `extract` e `transform` (M3-T4).

Nessun database e nessun file vero: ogni test scrive il proprio piccolo CSV in
una cartella temporanea. Si verifica che:

- un file assente, senza colonne, con valori non numerici o fuori range si
  fermi con `ETLError` e un messaggio che indica colonna e righe;
- `transform` applichi R1–R12 di `docs/markdown/M2-dati/dati.md`: conversioni
  esatte (i tre casi calcolati a mano in dati.md sono i valori attesi), scarti
  con il loro motivo, nessuna riga persa né inventata, nessun arrotondamento.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pytest

from beewatch.etl import (
    COLONNE_PULITE,
    LB_IN_KG,
    conteggio_scarti,
    extract,
    transform,
)
from beewatch.exceptions import ETLError

INTESTAZIONE = '"state","numcol","yieldpercol","totalprod","stocks","priceperlb","prodvalue","year"'

# Le tre righe verificate a mano in dati.md («Verifica su tre righe»).
ALABAMA_1998 = '"AL",16000,71,1136000,159000,0.72,818000,1998'
IOWA_2005 = '"IA",28000,88,2464000,1232000,1.21,2981000,2005'
WYOMING_2012 = '"WY",50000,51,2550000,459000,1.87,4769000,2012'


@pytest.fixture
def scrivi_csv(tmp_path: Path):
    """Scrive un CSV con l'intestazione della fonte (o un'altra) e restituisce il percorso."""

    def _scrivi(*righe: str, intestazione: str = INTESTAZIONE, nome: str = "honey.csv") -> Path:
        percorso = tmp_path / nome
        percorso.write_text("\n".join([intestazione, *righe]) + "\n", encoding="utf-8")
        return percorso

    return _scrivi


def pulisci(scrivi_csv, *righe: str, anno_corrente: int = 2026):
    return transform(extract(scrivi_csv(*righe)), anno_corrente=anno_corrente)


# --------------------------------------------------------------------------- #
# Conversioni: i valori calcolati a mano in dati.md
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "riga,resa,produzione,scorte,prezzo",
    [
        (ALABAMA_1998, 32.2051, 515_280.93, 72_121.19, 1.5873),
        (IOWA_2005, 39.9161, 1_117_651.60, 558_825.80, 2.6676),
        (WYOMING_2012, 23.1332, 1_156_660.54, 208_198.90, 4.1226),
    ],
    ids=["alabama_1998", "iowa_2005", "wyoming_2012"],
)
def test_le_tre_righe_verificate_a_mano(
    scrivi_csv, riga: str, resa: float, produzione: float, scorte: float, prezzo: float
) -> None:
    puliti, scartati = pulisci(scrivi_csv, riga)

    assert scartati.empty
    pulita = puliti.iloc[0]
    # dati.md riporta 4 decimali per resa e prezzo, 2 per le quantità totali.
    assert pulita["resa_per_colonia_kg"] == pytest.approx(resa, abs=5e-5)
    assert pulita["produzione_totale_kg"] == pytest.approx(produzione, abs=5e-3)
    assert pulita["scorte_kg"] == pytest.approx(scorte, abs=5e-3)
    assert pulita["prezzo_per_kg_usd"] == pytest.approx(prezzo, abs=5e-5)


def test_il_prezzo_si_divide_e_le_quantita_si_moltiplicano(scrivi_csv) -> None:
    """La verifica di plausibilità di dati.md: un kg costa più di una libbra e pesa di più."""
    pulita = pulisci(scrivi_csv, ALABAMA_1998)[0].iloc[0]
    assert pulita["prezzo_per_kg_usd"] == 0.72 / LB_IN_KG > 0.72
    assert pulita["resa_per_colonia_kg"] == 71 * LB_IN_KG < 71


def test_nessun_arrotondamento_r6(scrivi_csv) -> None:
    pulita = pulisci(scrivi_csv, ALABAMA_1998)[0].iloc[0]
    assert pulita["resa_per_colonia_kg"] == 71 * 0.45359237  # tutti i decimali, non 32.2051
    assert pulita["resa_per_colonia_kg"] != round(pulita["resa_per_colonia_kg"], 4)


def test_le_righe_pulite_hanno_nomi_e_tipi_del_database(scrivi_csv) -> None:
    puliti, _ = pulisci(scrivi_csv, ALABAMA_1998, IOWA_2005)

    assert list(puliti.columns) == list(COLONNE_PULITE)
    prima = puliti.iloc[0]
    assert (prima["codice_stato"], prima["anno"], prima["numero_colonie"]) == ("AL", 1998, 16000)
    assert prima["valore_produzione_usd"] == 818000  # R4: dollari, non convertiti
    for colonna in ("anno", "numero_colonie", "valore_produzione_usd"):
        assert puliti[colonna].dtype == "int64", colonna  # R12: interi, non float
    assert not puliti.isna().any().any()


# --------------------------------------------------------------------------- #
# Extract: il file e la sua forma
# --------------------------------------------------------------------------- #


def test_file_assente(tmp_path: Path) -> None:
    with pytest.raises(ETLError, match="non esiste") as info:
        extract(tmp_path / "manca.csv")
    assert "data/" in str(info.value)  # dice anche dove metterlo


def test_colonne_mancanti_elencate(scrivi_csv) -> None:
    percorso = scrivi_csv(
        '"AL",16000,71,0.72,1998', intestazione='"state","numcol","yieldpercol","priceperlb","year"'
    )
    with pytest.raises(ETLError) as info:
        extract(percorso)
    assert "totalprod, stocks, prodvalue" in str(info.value)


@pytest.mark.parametrize(
    "riga,colonna",
    [
        ('"AL",sedicimila,71,1136000,159000,0.72,818000,1998', "numcol"),
        ('"AL",16000,71,1136000,159000,"0,72",818000,1998', "priceperlb"),
        ('"AL",16000,71,1136000,159000,0.72,818000,MCMXCVIII', "year"),
    ],
    ids=["testo_al_posto_di_un_intero", "virgola_decimale", "anno_romano"],
)
def test_valori_non_numerici_con_colonna_e_riga(scrivi_csv, riga: str, colonna: str) -> None:
    with pytest.raises(ETLError, match="non numerici") as info:
        extract(scrivi_csv(ALABAMA_1998, riga))
    assert f"«{colonna}»" in str(info.value)
    assert "righe 3)" in str(info.value)  # riga 1 = intestazione, riga 2 = Alabama


def test_un_intero_con_decimali_e_un_errore_di_formato(scrivi_csv) -> None:
    with pytest.raises(ETLError, match="numeri interi") as info:
        extract(scrivi_csv('"AL",16000.5,71,1136000,159000,0.72,818000,1998'))
    assert "«numcol»" in str(info.value)


def test_gli_interi_scritti_con_lesponente_sono_accettati(scrivi_csv) -> None:
    """Il file vero contiene «2.2e+07» e «4e+05» (Florida 2001, North Dakota 2008)."""
    grezzo = extract(scrivi_csv('"ND",4e+05,90,3.6e+07,8640000,1.36,48960000,2008'))
    assert grezzo.loc[0, "numcol"] == 400_000
    assert grezzo.loc[0, "totalprod"] == 36_000_000


@pytest.mark.parametrize(
    "riga,colonna",
    [
        ('"AL",0,71,1136000,159000,0.72,818000,1998', "numcol"),
        ('"AL",1000001,71,1136000,159000,0.72,818000,1998', "numcol"),
        ('"AL",16000,201,1136000,159000,0.72,818000,1998', "yieldpercol"),
        ('"AL",16000,71,0,159000,0.72,818000,1998', "totalprod"),
        ('"AL",16000,71,1136000,-1,0.72,818000,1998', "stocks"),
        ('"AL",16000,71,1136000,159000,0.09,818000,1998', "priceperlb"),
        ('"AL",16000,71,1136000,159000,10.01,818000,1998', "priceperlb"),
        ('"AL",16000,71,1136000,159000,0.72,0,1998', "prodvalue"),
    ],
)
def test_valori_fuori_dal_range_accettato(scrivi_csv, riga: str, colonna: str) -> None:
    """dati.md, «Range e qualità»: fuori dal range accettato è un errore di formato."""
    with pytest.raises(ETLError, match="fuori dal range") as info:
        extract(scrivi_csv(riga))
    assert f"«{colonna}»" in str(info.value)


def test_i_limiti_del_range_sono_ammessi(scrivi_csv) -> None:
    extract(scrivi_csv('"AL",1,1,1,0,0.10,1,1998', '"AR",1000000,200,5,5,10.00,5,1998'))


@pytest.mark.parametrize(
    "contenuto",
    [b"", b"\xff\xfe\x00s\x00t\x00a\x00t\x00e\x00"],
    ids=["vuoto", "non_utf8"],
)
def test_un_file_che_non_e_un_csv_leggibile(tmp_path: Path, contenuto: bytes) -> None:
    percorso = tmp_path / "rotto.csv"
    percorso.write_bytes(contenuto)
    with pytest.raises(ETLError):
        extract(percorso)


def test_bom_colonne_in_piu_e_spazi_sono_tollerati(tmp_path: Path) -> None:
    percorso = tmp_path / "con_bom.csv"
    percorso.write_text(
        INTESTAZIONE + ',"nota"\n' + ALABAMA_1998.replace('"AL"', '" al "') + ',"x"\n',
        encoding="utf-8-sig",
    )
    puliti, scartati = transform(extract(percorso), anno_corrente=2026)
    assert scartati.empty
    assert puliti.loc[0, "codice_stato"] == "AL"  # R7: spazi tolti, maiuscolo


def test_i_messaggi_citano_al_massimo_cinque_righe(scrivi_csv) -> None:
    righe = [f'"AL",x,71,1136000,159000,0.72,818000,{anno}' for anno in range(1998, 2006)]
    with pytest.raises(ETLError) as info:
        extract(scrivi_csv(*righe))
    assert "righe 2, 3, 4, 5, 6 e altre 3" in str(info.value)


# --------------------------------------------------------------------------- #
# Transform: scarti, motivi, righe che restano
# --------------------------------------------------------------------------- #


def test_ogni_scarto_ha_riga_e_motivo(scrivi_csv) -> None:
    puliti, scartati = pulisci(
        scrivi_csv,
        ALABAMA_1998,                                          # riga 2: buona
        '"AL",16000,71,,159000,0.72,818000,1999',              # riga 3: R2
        '"PR",16000,71,1136000,159000,0.72,818000,1999',       # riga 4: R7, Porto Rico
        '"AL",16000,71,1136000,159000,0.72,818000,1989',       # riga 5: R8, troppo vecchio
        '"AL",16000,71,1136000,159000,0.72,818000,2027',       # riga 6: R8, nel futuro
        '"AL",17000,72,1224000,159000,0.72,818000,1998',       # riga 7: R9, doppione di riga 2
        IOWA_2005,                                             # riga 8: buona
    )  # fmt: skip

    assert list(puliti["codice_stato"] + puliti["anno"].astype(str)) == ["AL1998", "IA2005"]
    assert list(zip(scartati["riga"], scartati["motivo"], strict=True)) == [
        (3, "campo_obbligatorio_mancante"),
        (4, "stato_non_valido"),
        (5, "anno_non_plausibile"),
        (6, "anno_non_plausibile"),
        (7, "chiave_duplicata"),
    ]
    assert conteggio_scarti(scartati) == {
        "anno_non_plausibile": 2,
        "campo_obbligatorio_mancante": 1,
        "chiave_duplicata": 1,
        "stato_non_valido": 1,
    }


def test_il_duplicato_scartato_e_il_secondo_e_finisce_nel_log(scrivi_csv, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="beewatch.etl")
    puliti, scartati = pulisci(
        scrivi_csv, ALABAMA_1998, '"al",99999,99,1136000,159000,0.72,818000,1998'
    )
    assert puliti.loc[0, "numero_colonie"] == 16000  # resta la prima
    assert scartati.loc[0, "numcol"] == 99999  # lo scarto conserva i valori originali
    assert "Chiave duplicata" in caplog.text and "AL 1998 (riga 3)" in caplog.text


def test_il_primo_motivo_vince(scrivi_csv) -> None:
    """Uno stato inesistente con un campo vuoto è scartato per R2, non due volte."""
    _, scartati = pulisci(scrivi_csv, '"ZZ",,71,1136000,159000,0.72,818000,1500')
    assert list(scartati["motivo"]) == ["campo_obbligatorio_mancante"]


@pytest.mark.parametrize(
    "riga",
    [
        '"",16000,71,1136000,159000,0.72,818000,1998',
        '"   ",16000,71,1136000,159000,0.72,818000,1998',
        '"AL",16000,71,1136000,159000,0.72,818000,',
    ],
    ids=["stato_vuoto", "stato_di_spazi", "anno_vuoto"],
)
def test_r2_ogni_campo_vuoto_scarta_la_riga_senza_inventare_valori(scrivi_csv, riga: str) -> None:
    puliti, scartati = pulisci(scrivi_csv, riga)
    assert puliti.empty
    assert list(scartati["motivo"]) == ["campo_obbligatorio_mancante"]


def test_r8_lanno_corrente_e_quello_di_oggi_se_non_indicato(scrivi_csv) -> None:
    from datetime import date

    anno_prossimo = date.today().year + 1
    grezzo = extract(scrivi_csv(f'"AL",16000,71,1136000,159000,0.72,818000,{anno_prossimo}'))
    _, scartati = transform(grezzo)
    assert list(scartati["motivo"]) == ["anno_non_plausibile"]


def test_r1_r10_estremi_e_stati_con_pochi_anni_restano(scrivi_csv) -> None:
    puliti, scartati = pulisci(
        scrivi_csv,
        '"HI",9000,136,1224000,252000,1.69,2069000,2002',      # resa massima del dataset
        '"NJ",4000,19,76000,27000,1.67,127000,2003',           # resa minima
        '"CA",510000,74,37740000,9056000,0.6,22644000,1999',   # il produttore più grande
        '"SC",15000,48,720000,72000,1.13,814000,2010',         # stato con copertura parziale
    )  # fmt: skip
    assert scartati.empty
    assert len(puliti) == 4


def test_r11_scorte_maggiori_della_produzione_restano_con_un_avviso(scrivi_csv, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="beewatch.etl")
    nebraska_2006 = '"NE",47000,73,3431000,3843000,0.93,3191000,2006'  # anomalia A2 di dati.md
    puliti, scartati = pulisci(scrivi_csv, nebraska_2006, ALABAMA_1998)
    assert scartati.empty and len(puliti) == 2
    assert "Scorte superiori alla produzione: NE 2006" in caplog.text
    assert "AL 1998" not in caplog.text


def test_nessuna_riga_persa_e_input_non_modificato(scrivi_csv) -> None:
    grezzo = extract(scrivi_csv(ALABAMA_1998, '"ZZ",1,1,1,1,1,1,1998', IOWA_2005, ALABAMA_1998))
    copia = grezzo.copy()

    puliti, scartati = transform(grezzo, anno_corrente=2026)

    assert len(puliti) + len(scartati) == len(grezzo)
    pd.testing.assert_frame_equal(grezzo, copia)  # funzione pura: l'ingresso resta com'era


def test_nessuno_scarto_conteggio_vuoto(scrivi_csv) -> None:
    _, scartati = pulisci(scrivi_csv, ALABAMA_1998)
    assert conteggio_scarti(scartati) == {}
    assert list(scartati.columns) == ["riga", *extract(scrivi_csv(ALABAMA_1998)).columns, "motivo"]


def test_il_fattore_di_conversione_e_scritto_una_volta_sola() -> None:
    """R3: il fattore vive in una sola costante, mai riscritto a mano."""
    pacchetto = Path(__file__).resolve().parents[1] / "beewatch"
    occorrenze = sum(
        f.read_text(encoding="utf-8").count("0.45359237") for f in pacchetto.rglob("*.py")
    )
    assert occorrenze == 1
