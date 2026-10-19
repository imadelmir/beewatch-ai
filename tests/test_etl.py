"""Test dell'ETL USDA: `extract` e `transform` (M3-T4), `load`, pipeline e CLI (M3-T5).

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
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from beewatch.etl import (
    COLONNE_PULITE,
    LB_IN_KG,
    EsitoCaricamento,
    ReportETL,
    _salva_report,
    conteggio_scarti,
    extract,
    load,
    run_pipeline,
    transform,
)
from beewatch.exceptions import DatabaseError, ETLError

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


def test_r8_i_limiti_dellintervallo_sono_ammessi(scrivi_csv) -> None:
    puliti, scartati = pulisci(
        scrivi_csv,
        '"AL",16000,71,1136000,159000,0.72,818000,1990',
        '"AL",16000,71,1136000,159000,0.72,818000,2026',
        anno_corrente=2026,
    )
    assert scartati.empty
    assert list(puliti["anno"]) == [1990, 2026]


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


# =========================================================================== #
# Load, pipeline e CLI (M3-T5)
# =========================================================================== #


def test_il_repository_carica_le_colonne_prodotte_da_transform() -> None:
    from beewatch.repositories_riferimento import COLONNE_PRODUZIONE

    assert COLONNE_PRODUZIONE == COLONNE_PULITE


def _report(scartate: pd.DataFrame | None = None, **valori) -> ReportETL:
    base = {
        "file": Path("data/honey.csv"),
        "sha256": "0" * 64,
        "lette": 5,
        "scartate_per_motivo": {"stato_non_valido": 1},
        "caricamento": EsitoCaricamento(inserite=3, aggiornate=1, invariate=0),
        "durata_secondi": 0.4567,
        "scartate": scartate if scartate is not None else pd.DataFrame(),
    }
    return ReportETL(**{**base, **valori})


def test_il_report_dice_lette_scartate_per_motivo_inserite_aggiornate_invariate_durata() -> None:
    scartate = pd.DataFrame(
        [{"riga": 4, "state": "PR", "year": 1999, "motivo": "stato_non_valido"}]
    )
    testo = _report(scartate).testo()

    for atteso in (
        "Righe lette:     5",
        "Righe scartate:  1",
        "  stato_non_valido: 1",
        "Inserite:        3",
        "Aggiornate:      1",
        "Invariate:       0",
        "Durata:          0.46 s",
        "  4  PR  1999  stato_non_valido",
    ):
        assert atteso in testo


def test_il_report_salvato_non_sovrascrive_quello_precedente(tmp_path: Path) -> None:
    primo = _salva_report(_report(), tmp_path)
    secondo = _salva_report(_report(lette=6), tmp_path)

    assert primo != secondo
    assert "Righe lette:     5" in primo.read_text(encoding="utf-8")
    assert "Righe lette:     6" in secondo.read_text(encoding="utf-8")


@pytest.fixture
def cli(logging_azzerato: None):
    """`scripts/run_etl.py` caricato come modulo: `main()` gira nello stesso processo, così
    valgono l'ambiente isolato di `ambiente_pulito` e i log nella cartella temporanea."""
    import importlib.util

    percorso = Path(__file__).resolve().parents[1] / "scripts" / "run_etl.py"
    specifica = importlib.util.spec_from_file_location("run_etl", percorso)
    modulo = importlib.util.module_from_spec(specifica)
    specifica.loader.exec_module(modulo)
    return modulo


def test_cli_aiuto(cli, capsys) -> None:
    with pytest.raises(SystemExit) as uscita:
        cli.main(["--help"])
    assert uscita.value.code == 0
    assert "--file" in capsys.readouterr().out


def test_cli_file_assente_esce_con_1_e_un_messaggio_senza_traceback(
    cli, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    for nome, valore in {"DB_NAME": "x", "DB_USER": "y", "DB_PASSWORD": "PW-ETL-cli"}.items():
        monkeypatch.setenv(nome, valore)

    codice = cli.main(["--file", str(tmp_path / "manca.csv"), "--report-dir", str(tmp_path)])

    uscita = capsys.readouterr()
    assert codice == 1
    assert uscita.err.startswith("ETL non eseguito: Il file del dataset non esiste")
    assert "Traceback" not in uscita.err and "PW-ETL-cli" not in uscita.err
    assert list(tmp_path.glob("etl_*.txt")) == []  # nessun report per un ETL non eseguito


# -- integrazione: MySQL vero, database di test ------------------------------ #

STATI_DEL_TEST = ("AL", "IA", "WY", "NE")
NEBRASKA_2006 = '"NE",47000,73,3431000,3843000,0.93,3191000,2006'


@pytest.fixture
def produzione_pulita(database_test) -> Iterator[None]:
    """Toglie prima e dopo le righe degli stati usati qui, e solo quelle."""

    def _pulisci() -> None:
        with database_test.transazione() as cursore:
            cursore.execute(
                "DELETE FROM produzione_usda WHERE codice_stato IN (%s, %s, %s, %s)",
                STATI_DEL_TEST,
            )

    _pulisci()
    yield
    _pulisci()


def _nel_database(database_test) -> dict[tuple[str, int], dict]:
    with database_test.transazione() as cursore:
        cursore.execute(
            "SELECT * FROM produzione_usda WHERE codice_stato IN (%s, %s, %s, %s)",
            STATI_DEL_TEST,
        )
        return {(r["codice_stato"], r["anno"]): r for r in cursore.fetchall()}


@pytest.mark.integration
def test_integrazione_load_inserisce_poi_non_duplica_poi_aggiorna(
    scrivi_csv, database_test, produzione_pulita
) -> None:
    puliti, _ = pulisci(scrivi_csv, ALABAMA_1998, IOWA_2005, WYOMING_2012)

    assert load(puliti, database_test) == EsitoCaricamento(3, 0, 0)
    assert load(puliti, database_test) == EsitoCaricamento(0, 0, 3)  # idempotente

    cambiati = puliti.copy()
    cambiati.loc[0, "numero_colonie"] = 17000
    assert load(cambiati, database_test) == EsitoCaricamento(0, 1, 2)

    righe = _nel_database(database_test)
    assert len(righe) == 3
    alabama = righe[("AL", 1998)]
    assert alabama["numero_colonie"] == 17000
    # Il database conserva 4 decimali (DECIMAL(8,4)): sono i valori di dati.md.
    assert alabama["resa_per_colonia_kg"] == Decimal("32.2051")
    assert alabama["prezzo_per_kg_usd"] == Decimal("1.5873")
    assert alabama["produzione_totale_kg"] == Decimal("515280.9323")
    assert alabama["valore_produzione_usd"] == Decimal("818000.00")


@pytest.mark.integration
def test_integrazione_un_errore_a_meta_non_lascia_scritture_parziali(
    scrivi_csv, database_test, produzione_pulita
) -> None:
    puliti, _ = pulisci(scrivi_csv, ALABAMA_1998, IOWA_2005, WYOMING_2012)
    rotti = puliti.copy()
    rotti.loc[2, "resa_per_colonia_kg"] = -1.0  # viola il CHECK del database, all'ultima riga

    with pytest.raises(DatabaseError):
        load(rotti, database_test)

    assert _nel_database(database_test) == {}  # nemmeno le prime due righe


@pytest.mark.integration
def test_integrazione_seed_mancante_etl_error_prima_di_scrivere(
    scrivi_csv, database_test, produzione_pulita
) -> None:
    puliti, _ = pulisci(scrivi_csv, ALABAMA_1998)
    con_stato_ignoto = pd.concat([puliti, puliti.assign(codice_stato="ZZ")], ignore_index=True)

    with pytest.raises(ETLError, match=r"stati_usa non contiene 1 stati del dataset \(ZZ\)"):
        load(con_stato_ignoto, database_test)
    assert _nel_database(database_test) == {}


@pytest.mark.integration
def test_integrazione_due_esecuzioni_della_pipeline_stesse_righe_e_report_su_file(
    scrivi_csv, database_test, produzione_pulita, tmp_path: Path
) -> None:
    percorso = scrivi_csv(ALABAMA_1998, IOWA_2005, '"PR",1,1,1,1,1,1,2000', NEBRASKA_2006)
    cartella = tmp_path / "report"

    primo = run_pipeline(percorso, database_test, cartella)
    righe_dopo_il_primo = len(_nel_database(database_test))
    secondo = run_pipeline(percorso, database_test, cartella)

    assert righe_dopo_il_primo == len(_nel_database(database_test)) == 3
    assert (primo.lette, primo.scartate_per_motivo) == (4, {"stato_non_valido": 1})
    assert primo.caricamento == EsitoCaricamento(3, 0, 0)
    assert secondo.caricamento == EsitoCaricamento(0, 0, 3)
    salvati = sorted(cartella.glob("etl_*.txt"))
    assert len(salvati) == 2
    assert primo.testo() in {s.read_text(encoding="utf-8") for s in salvati}


@pytest.mark.integration
def test_integrazione_la_cli_popola_il_database_e_stampa_il_report(
    cli, scrivi_csv, config_db_test, database_test, produzione_pulita,
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys,
) -> None:  # fmt: skip
    for nome, valore in {
        "DB_HOST": config_db_test.host,
        "DB_PORT": str(config_db_test.porta),
        "DB_NAME": config_db_test.nome,
        "DB_USER": config_db_test.utente,
        "DB_PASSWORD": config_db_test.password,
    }.items():
        monkeypatch.setenv(nome, valore)

    codice = cli.main(
        ["--file", str(scrivi_csv(ALABAMA_1998, WYOMING_2012)), "--report-dir", str(tmp_path)]
    )

    uscita = capsys.readouterr()
    assert codice == 0, uscita.err
    assert "Inserite:        2" in uscita.out
    assert config_db_test.password not in uscita.out + uscita.err
    assert set(_nel_database(database_test)) == {("AL", 1998), ("WY", 2012)}
    assert len(list(tmp_path.glob("etl_*.txt"))) == 1


# =========================================================================== #
# CSV mini in tests/fixtures (M3-T6)
# =========================================================================== #
# `honey_mini.csv`: 3 stati x 5 anni (2008-2012) con valori SINTETICI, non USDA,
# ma coerenti (produzione = colonie x resa), più due righe invalide: Porto Rico
# (R7) e una riga senza scorte (R2). AL 2010 ha scorte superiori alla produzione
# (R11). Il CSV vero non è nel repository (DA-04).

CSV_MINI = Path(__file__).resolve().parent / "fixtures" / "honey_mini.csv"


def test_csv_mini_quindici_righe_pulite_e_due_scartate(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="beewatch.etl")

    grezzo = extract(CSV_MINI)
    puliti, scartati = transform(grezzo, anno_corrente=2026)

    assert len(grezzo) == 17
    assert len(puliti) == 15
    assert puliti.groupby("codice_stato")["anno"].apply(list).to_dict() == {
        stato: [2008, 2009, 2010, 2011, 2012] for stato in ("AL", "CA", "ND")
    }
    assert conteggio_scarti(scartati) == {"campo_obbligatorio_mancante": 1, "stato_non_valido": 1}
    assert list(scartati["riga"]) == [17, 18]
    assert "Scorte superiori alla produzione: AL 2010" in caplog.text
    assert not puliti.isna().any().any()


def test_csv_mini_coerente_produzione_uguale_a_colonie_per_resa() -> None:
    """Il controllo di coerenza di dati.md, ripetuto sulle righe pulite (in kg)."""
    puliti, _ = transform(extract(CSV_MINI), anno_corrente=2026)
    attesa = puliti["numero_colonie"] * puliti["resa_per_colonia_kg"]
    assert (attesa - puliti["produzione_totale_kg"]).abs().max() < 1e-6


def test_solo_intestazione_nessuna_riga_nessun_errore(scrivi_csv) -> None:
    puliti, scartati = transform(extract(scrivi_csv()), anno_corrente=2026)
    assert puliti.empty and scartati.empty
    assert list(puliti.columns) == list(COLONNE_PULITE)
    assert conteggio_scarti(scartati) == {}


@pytest.fixture
def produzione_mini_pulita(database_test) -> Iterator[None]:
    def _pulisci() -> None:
        with database_test.transazione() as cursore:
            cursore.execute("DELETE FROM produzione_usda WHERE codice_stato IN ('AL', 'CA', 'ND')")

    _pulisci()
    yield
    _pulisci()


def _righe_mini(database_test) -> list[dict]:
    with database_test.transazione() as cursore:
        cursore.execute(
            "SELECT * FROM produzione_usda WHERE codice_stato IN ('AL', 'CA', 'ND') "
            "ORDER BY codice_stato, anno"
        )
        return cursore.fetchall()


@pytest.mark.integration
def test_integrazione_csv_mini_idempotenza(database_test, produzione_mini_pulita, tmp_path) -> None:
    """DoD M3-T6: due esecuzioni, stesse righe, stessi valori, stessi id."""
    primo = run_pipeline(CSV_MINI, database_test, tmp_path)
    dopo_il_primo = _righe_mini(database_test)
    secondo = run_pipeline(CSV_MINI, database_test, tmp_path)
    dopo_il_secondo = _righe_mini(database_test)

    assert primo.caricamento == EsitoCaricamento(inserite=15, aggiornate=0, invariate=0)
    assert secondo.caricamento == EsitoCaricamento(inserite=0, aggiornate=0, invariate=15)
    assert len(dopo_il_primo) == 15
    assert dopo_il_secondo == dopo_il_primo  # nemmeno un valore o un id è cambiato


@pytest.mark.integration
def test_integrazione_csv_mini_rollback_se_una_riga_fallisce(
    database_test, produzione_mini_pulita
) -> None:
    puliti, _ = transform(extract(CSV_MINI), anno_corrente=2026)
    load(puliti.iloc[:5], database_test)  # AL già caricato
    prima = _righe_mini(database_test)

    rotti = puliti.copy()
    rotti.loc[0, "numero_colonie"] = 9999  # aggiornerebbe AL 2008...
    rotti.loc[14, "prezzo_per_kg_usd"] = 99999.0  # ...ma l'ultima riga sfora DECIMAL(8,4)

    with pytest.raises(DatabaseError):
        load(rotti, database_test)

    assert _righe_mini(database_test) == prima  # né l'aggiornamento né le righe nuove


@pytest.mark.integration
def test_integrazione_caricare_zero_righe_non_scrive_nulla(database_test) -> None:
    vuoto = pd.DataFrame({c: [] for c in COLONNE_PULITE})
    assert load(vuoto, database_test) == EsitoCaricamento(0, 0, 0)
