"""`streamlit run app/Home.py` parte davvero (M6-T1).

Lancia Streamlit come lo lancerebbe una persona, in un sottoprocesso, dalla radice del progetto, e
aspetta che risponda. Non serve né MySQL né un `.env`: l'applicazione parte comunque, e l'errore di
configurazione compare solo quando qualcuno apre una pagina (lo prova `test_app_streamlit.py`).

Cosa prova: che il comando documentato parte senza errori, che il server risponde sul suo controllo
di salute e serve la pagina, che non scrive traceback sull'uscita. Cosa NON prova: il menu laterale
e l'aspetto grafico, che richiedono un browser.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from docker_support import porta_libera

RADICE = Path(__file__).resolve().parents[1]
ATTESA_MASSIMA = 60  # secondi: il primo avvio importa pandas, scikit-learn e streamlit


@pytest.fixture
def avvio_reale(tmp_path: Path) -> Iterator[tuple[str, subprocess.Popen]]:
    porta = porta_libera()
    # Ambiente minimo e pulito: niente DB_*, niente LLM_*, niente proxy della shell.
    ambiente = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA"}
    }
    ambiente["PYTHONIOENCODING"] = "utf-8"
    ambiente["NO_PROXY"] = "127.0.0.1,localhost"
    uscita = (tmp_path / "streamlit.log").open("w+", encoding="utf-8")
    processo = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app/Home.py",
            "--server.headless=true",
            f"--server.port={porta}",
            "--server.address=127.0.0.1",
            "--browser.gatherUsageStats=false",
        ],
        cwd=RADICE,
        env=ambiente,
        stdout=uscita,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{porta}"
    try:
        yield url, processo
    finally:
        processo.terminate()
        try:
            processo.wait(timeout=15)
        except subprocess.TimeoutExpired:
            processo.kill()
        uscita.close()


def leggi(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=3) as risposta:  # noqa: S310 - solo 127.0.0.1
        return risposta.status, risposta.read().decode("utf-8", "replace")


def aspetta_il_server(url: str, processo: subprocess.Popen) -> None:
    inizio = time.monotonic()
    while time.monotonic() - inizio < ATTESA_MASSIMA:
        if processo.poll() is not None:
            pytest.fail(f"streamlit è terminato con codice {processo.returncode} prima di partire")
        try:
            stato, corpo = leggi(f"{url}/_stcore/health")
            if stato == 200 and corpo.strip() == "ok":
                return
        except OSError:
            time.sleep(0.5)
    pytest.fail(f"streamlit non ha risposto in {ATTESA_MASSIMA} secondi")


def test_streamlit_run_app_home_py_parte_e_risponde(avvio_reale, tmp_path):
    url, processo = avvio_reale

    aspetta_il_server(url, processo)

    stato, pagina = leggi(url)
    assert stato == 200 and "streamlit" in pagina.lower()
    assert processo.poll() is None  # sta ancora girando
    registro = (tmp_path / "streamlit.log").read_text(encoding="utf-8")
    assert "Traceback" not in registro
    assert "Error" not in registro.replace("ErrorBoundary", "")
