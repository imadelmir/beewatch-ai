"""Supporto ai test Docker: stack temporanei e GUARDIA contro la cancellazione di risorse reali.

Un `Stack` è un progetto compose usa-e-getta: nome di progetto, volume e immagine propri
(`bwdockerfix-<sigla>`), credenziali casuali, `.env` finto passato con `--env-file` e un
file di override che toglie i nomi fissi del compose (`container_name`, nome del volume).

Chi pulisce lo fa con `down -v`, che cancella i volumi: un nome sbagliato qui vorrebbe
dire perdere il database di sviluppo. Per questo il codice non si fida di aver generato
i nomi giusti. Cinque difese, indipendenti fra loro:

1. i nomi propri si fissano alla creazione, e prima di ogni pulizia si controlla che
   nessuno sia stato modificato, che abbiano il prefisso e la sigla di QUESTO stack e che
   non siano risorse reali;
2. `esegui()` rifiuta qualunque comando docker che nomini una risorsa reale, anche solo
   per leggerla (le letture di controllo usano `subprocess` direttamente);
3. prima di creare e prima di cancellare si fa rendere la configurazione unita di compose
   e si verifica che usi solo i nomi propri (override effettivo: niente `container_name`,
   volume e immagine propri);
4. ogni contenitore trovato per etichetta viene ispezionato prima di `rm`: progetto e nome
   devono essere propri;
5. `fotografia_risorse_reali()` permette ai test di confrontare, prima e dopo, lo stato
   delle risorse reali: se qualcosa fosse stato toccato, il test fallisce.

Ogni violazione solleva `RisorsaRealeError` PRIMA di eseguire il comando.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import time
import uuid
from collections.abc import Callable
from pathlib import Path

RADICE_PROGETTO = Path(__file__).resolve().parents[1]
COMPOSE = RADICE_PROGETTO / "docker-compose.yml"

DB_NAME = "bw_stack"  # con il trattino basso: è il caso difficile dei privilegi
DB_USER = "app_stack"

PREFISSO = "bwdockerfix"

# Le risorse del progetto reale (docker-compose.yml, `docker compose up` dello sviluppatore).
VOLUMI_REALI = frozenset({"beewatch_dati_mysql"})
CONTENITORI_REALI = frozenset({"beewatch-mysql", "beewatch-app"})
IMMAGINI_REALI = frozenset({"beewatch-ai:dev"})
PROGETTI_REALI = frozenset({"beewatch", "beewatch-ai"})
RETI_REALI = frozenset({"beewatch-ai_default", "beewatch_default"})
RISORSE_REALI = VOLUMI_REALI | CONTENITORI_REALI | IMMAGINI_REALI | PROGETTI_REALI | RETI_REALI


class RisorsaRealeError(RuntimeError):
    """Un comando di test stava per toccare (o poteva toccare) una risorsa che non è sua."""


def docker_pronto() -> bool:
    try:
        esito = subprocess.run(["docker", "info"], capture_output=True, timeout=20, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return esito.returncode == 0


def porta_libera() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def porta_occupata(porta: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def attendi(condizione: Callable[[], bool], secondi: int, cosa: str) -> None:
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if condizione():
            return
        time.sleep(2)
    raise AssertionError(f"timeout ({secondi}s): {cosa}")


def ambiente_pulito() -> dict[str, str]:
    """L'ambiente di chi lancia i test, senza variabili che cambierebbero lo stack.

    Compose preferisce le variabili della shell al `--env-file`: un `DB_PASSWORD`
    esportato dallo sviluppatore sostituirebbe quello di prova.
    """
    prefissi = ("DB_", "MYSQL_", "LLM_", "MODEL_PATH", "LOG_LEVEL", "COMPOSE_")
    return {k: v for k, v in os.environ.items() if not k.startswith(prefissi)}


def nomi_in(argomento: str) -> set[str]:
    """I possibili nomi di risorsa contenuti in un argomento (`nome`, `chiave=nome`, `/nome`)."""
    return {argomento, argomento.rsplit("=", 1)[-1], argomento.lstrip("/")}


def fotografia_risorse_reali() -> dict[str, str]:
    """Stato delle risorse reali che esistono, in sola lettura (non passa da `Stack.esegui`)."""
    foto: dict[str, str] = {}

    def leggi(chiave: str, *comando: str) -> None:
        esito = subprocess.run(
            ["docker", *comando], capture_output=True, text=True, timeout=30, check=False
        )
        if esito.returncode == 0:
            foto[chiave] = esito.stdout.strip()

    for volume in sorted(VOLUMI_REALI):
        leggi(
            f"volume:{volume}", "volume", "inspect", volume, "-f", "{{.CreatedAt}}|{{.Mountpoint}}"
        )
    for contenitore in sorted(CONTENITORI_REALI):
        leggi(
            f"contenitore:{contenitore}",
            "inspect", contenitore, "-f",
            "{{.Id}}|{{.State.Status}}|{{.State.StartedAt}}|{{.State.FinishedAt}}",
        )  # fmt: skip
    return foto


def copia_sql_con_errore(destinazione: Path, file_rotto: str) -> Path:
    """Copia `sql/` in `destinazione` e aggiunge a `file_rotto` un'istruzione non valida."""
    destinazione.mkdir(parents=True, exist_ok=True)
    for sorgente in (RADICE_PROGETTO / "sql").glob("*.sql"):
        (destinazione / sorgente.name).write_bytes(sorgente.read_bytes())
    rotto = destinazione / file_rotto
    rotto.write_text(rotto.read_text(encoding="utf-8") + "\nQUESTO NON E' SQL;\n", encoding="utf-8")
    return destinazione


class Stack:
    """Un progetto compose temporaneo, con credenziali casuali e pulizia protetta."""

    def __init__(
        self,
        cartella: Path,
        porta_db: int | None,
        *,
        sql_dir: Path | None = None,
        mysql_controlli_rapidi: bool = False,
    ) -> None:
        self.sigla = uuid.uuid4().hex[:8]
        self.progetto = f"{PREFISSO}-{self.sigla}"
        self.immagine = f"{PREFISSO}-app:{self.sigla}"
        self.volume = f"{PREFISSO}_{self.sigla}_dati"
        # I nomi propri, fissati ora: se un attributo cambia dopo, la pulizia si rifiuta.
        self._propri = (self.progetto, self.volume, self.immagine)

        self.porta_app = porta_libera()
        self.porta_db = porta_db or 3306  # se DB_PORT manca, compose usa 3306
        self.password_app = secrets.token_hex(16)
        self.password_root = secrets.token_hex(16)

        righe = [
            f"DB_NAME={DB_NAME}",
            f"DB_USER={DB_USER}",
            f"DB_PASSWORD={self.password_app}",
            f"DB_ROOT_PASSWORD={self.password_root}",
            "DB_HOST=localhost",  # come in un .env vero: dentro Docker deve essere ignorato
            "LLM_PROVIDER=ollama",
            "LOG_LEVEL=INFO",
        ]
        if porta_db is not None:
            righe.append(f"DB_PORT={porta_db}")
        cartella.mkdir(parents=True, exist_ok=True)
        self.env_file = cartella / "stack.env"
        self.env_file.write_text("\n".join(righe) + "\n", encoding="utf-8")

        mysql_extra = ""
        if sql_dir is not None:  # script di init alternativi (per le prove con uno script rotto)
            mysql_extra += f"""    volumes: !override
      - type: volume
        source: dati_mysql
        target: /var/lib/mysql
      - type: bind
        source: "{sql_dir.as_posix()}"
        target: /docker-entrypoint-initdb.d
        read_only: true
"""
        if mysql_controlli_rapidi:  # solo per prove in cui il guasto e' atteso
            mysql_extra += """    healthcheck:
      interval: 3s
      timeout: 5s
      retries: 3
      start_period: 3s
"""
        self.override = cartella / "override.yml"
        self.override.write_text(
            f"""services:
  mysql:
    container_name: !reset null
{mysql_extra}  app:
    container_name: !reset null
    image: {self.immagine}
    ports: !override
      - "127.0.0.1:{self.porta_app}:8501"
    healthcheck:
      interval: 5s
      timeout: 10s
      retries: 2
      start_period: 15s
volumes:
  dati_mysql:
    name: {self.volume}
""",
            encoding="utf-8",
        )

    # -- guardia ------------------------------------------------------------ #

    def _verifica_nomi(self) -> None:
        """Difesa 1: i nomi sono quelli fissati alla creazione, di questo stack, non reali."""
        attuali = (self.progetto, self.volume, self.immagine)
        if attuali != self._propri:
            raise RisorsaRealeError(
                f"nomi modificati dopo la creazione: {attuali} != {self._propri}"
            )
        for nome in attuali:
            if nome in RISORSE_REALI:
                raise RisorsaRealeError(f"'{nome}' e' una risorsa del progetto reale")
            if not nome.startswith(PREFISSO) or self.sigla not in nome:
                raise RisorsaRealeError(f"'{nome}' non appartiene a questo stack ({self.sigla})")

    def _verifica_configurazione(self) -> None:
        """Difesa 3: la configurazione unita di compose usa solo nomi propri."""
        esito = self.compose("config", "--format", "json", controlla=False)
        if esito.returncode != 0:
            raise RisorsaRealeError("configurazione non verificabile: " + esito.stderr[-300:])
        cfg = json.loads(esito.stdout)
        problemi = []
        if cfg.get("name") != self.progetto:
            problemi.append(f"progetto {cfg.get('name')!r}")
        for nome, servizio in cfg.get("services", {}).items():
            if "container_name" in servizio:
                problemi.append(f"{nome}: container_name {servizio['container_name']!r}")
        if cfg["services"]["app"].get("image") != self.immagine:
            problemi.append(f"immagine {cfg['services']['app'].get('image')!r}")
        volumi = {v.get("name") for v in cfg.get("volumes", {}).values()}
        if volumi != {self.volume}:
            problemi.append(f"volumi {sorted(volumi)}")
        if problemi:
            raise RisorsaRealeError(
                "la configurazione nomina risorse non proprie: " + "; ".join(problemi)
            )

    def _verifica_contenitore(self, id_contenitore: str) -> None:
        """Difesa 4: un contenitore si rimuove solo se e' di questo progetto."""
        esito = self.esegui(
            "inspect", "-f", '{{.Name}}|{{index .Config.Labels "com.docker.compose.project"}}',
            id_contenitore, controlla=False,
        )  # fmt: skip
        nome, _, progetto = esito.stdout.strip().partition("|")
        nome = nome.lstrip("/")
        if esito.returncode != 0 or progetto != self.progetto or nome in CONTENITORI_REALI:
            raise RisorsaRealeError(
                f"il contenitore {nome!r} (progetto {progetto!r}) non e' di questo stack"
            )

    # -- comandi ------------------------------------------------------------ #

    def redigi(self, testo: str) -> str:
        for segreto in (self.password_app, self.password_root):
            testo = testo.replace(segreto, "***")
        return testo

    def esegui(
        self, *argomenti: str, controlla: bool = True, timeout: int = 120
    ) -> subprocess.CompletedProcess[str]:
        # Difesa 2: nessun comando puo' nominare una risorsa reale.
        for argomento in argomenti:
            reali = nomi_in(argomento) & RISORSE_REALI
            if reali:
                raise RisorsaRealeError(
                    f"comando rifiutato: nomina {sorted(reali)}: docker {argomenti[:4]}"
                )
        esito = subprocess.run(
            ["docker", *argomenti],
            env=ambiente_pulito(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if controlla and esito.returncode != 0:
            raise AssertionError(
                f"docker {' '.join(argomenti[:3])} è fallito ({esito.returncode}):\n"
                + self.redigi(esito.stdout + esito.stderr)[-3000:]
            )
        return esito

    def compose(self, *argomenti: str, **opzioni) -> subprocess.CompletedProcess[str]:
        return self.esegui(
            "compose", "-p", self.progetto, "-f", str(COMPOSE), "-f", str(self.override),
            "--env-file", str(self.env_file), *argomenti, **opzioni,
        )  # fmt: skip

    def container(self, servizio: str, tutti: bool = False) -> str:
        opzioni = ["-a"] if tutti else []
        return self.compose("ps", *opzioni, "-q", servizio).stdout.strip()

    def nel_container(
        self, servizio: str, *comando: str, ambiente: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        opzioni = [x for k, v in (ambiente or {}).items() for x in ("-e", f"{k}={v}")]
        return self.compose("exec", "-T", *opzioni, servizio, *comando, controlla=False)

    def salute(self, id_container: str) -> str:
        esito = self.esegui(
            "inspect", "-f", "{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}",
            id_container, controlla=False,
        )  # fmt: skip
        return esito.stdout.strip()

    def avvia(self, costruisci: bool = True) -> None:
        """`docker compose up --wait` (con `--build` se richiesto). Verifica i nomi prima."""
        self._verifica_nomi()
        self._verifica_configurazione()
        opzioni = ["--build"] if costruisci else []
        self.compose("up", "-d", *opzioni, "--wait", "--wait-timeout", "300", timeout=1500)

    def smonta(self) -> None:
        """Toglie tutto ciò che appartiene a questo stack, e nient'altro.

        Se qualcosa non torna solleva `RisorsaRealeError` senza aver eseguito nulla di
        distruttivo. Le risorse di prova rimaste vanno tolte a mano (hanno il prefisso
        `bwdockerfix`).
        """
        self._verifica_nomi()
        self._verifica_configurazione()
        etichetta = f"label=com.docker.compose.project={self.progetto}"
        ids = self.esegui("ps", "-aq", "--filter", etichetta, controlla=False).stdout.split()
        for id_contenitore in ids:
            self._verifica_contenitore(id_contenitore)  # tutti, prima di rimuoverne uno
        if ids:
            self.esegui("rm", "-f", "-v", *ids, controlla=False)
        self.compose("down", "-v", "--remove-orphans", controlla=False)
        self.esegui("volume", "rm", "-f", self.volume, controlla=False)
        self.esegui("image", "rm", "-f", self.immagine, controlla=False)
