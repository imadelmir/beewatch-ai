"""Test della guardia di pulizia dei test Docker (`docker_support.Stack`).

Nessun comando docker viene eseguito: `subprocess.run` è sostituito da un finto che si
limita a registrare ciò che gli viene chiesto. Così si può provare con nomi REALI
(`beewatch_dati_mysql`) senza correre il rischio di toccarli, e i test girano anche dove
Docker non c'è.

Ciò che si dimostra: la pulizia normale tocca solo risorse proprie; ogni tentativo di
nominare il volume, il progetto, l'immagine o i contenitori reali si ferma con
`RisorsaRealeError` prima di eseguire qualunque comando distruttivo.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import docker_support
import pytest
from docker_support import (
    CONTENITORI_REALI,
    IMMAGINI_REALI,
    PREFISSO,
    PROGETTI_REALI,
    RISORSE_REALI,
    VOLUMI_REALI,
    RisorsaRealeError,
    Stack,
)

VOLUME_REALE = "beewatch_dati_mysql"


class DockerFinto:
    """Sostituisce `subprocess.run`: registra i comandi e risponde con valori scelti."""

    def __init__(self, stack: Stack) -> None:
        self.comandi: list[list[str]] = []
        self.config = {
            "name": stack.progetto,
            "services": {"mysql": {"image": "mysql:8.4"}, "app": {"image": stack.immagine}},
            "volumes": {"dati_mysql": {"name": stack.volume}},
        }
        self.ids: list[str] = ["id_proprio_1", "id_proprio_2"]
        self.ispezione = f"{stack.progetto}-mysql-1|{stack.progetto}"  # nome|progetto

    def __call__(self, argomenti, **_opzioni) -> subprocess.CompletedProcess[str]:
        self.comandi.append(list(argomenti))
        uscita = ""
        if "config" in argomenti and "--format" in argomenti:
            uscita = json.dumps(self.config)
        elif argomenti[1:2] == ["ps"]:
            uscita = " ".join(self.ids)
        elif argomenti[1:2] == ["inspect"]:
            uscita = self.ispezione
        return subprocess.CompletedProcess(argomenti, 0, stdout=uscita, stderr="")

    def distruttivi(self) -> list[list[str]]:
        """Comandi che cancellano: rm, volume rm, image rm, compose ... down."""
        return [
            c for c in self.comandi
            if c[1:2] == ["rm"] or c[1:3] in (["volume", "rm"], ["image", "rm"]) or "down" in c
        ]  # fmt: skip

    def nomina_risorse_reali(self) -> list[str]:
        return sorted(
            {n for c in self.comandi for a in c for n in docker_support.nomi_in(a)} & RISORSE_REALI
        )


@pytest.fixture
def stack(tmp_path) -> Stack:
    return Stack(tmp_path, 3399)


@pytest.fixture
def docker(monkeypatch, stack: Stack) -> DockerFinto:
    finto = DockerFinto(stack)
    monkeypatch.setattr(docker_support.subprocess, "run", finto)
    return finto


# --------------------------------------------------------------------------- #
# Pulizia normale
# --------------------------------------------------------------------------- #


def test_i_nomi_dello_stack_sono_propri_e_mai_reali(stack: Stack) -> None:
    for nome in (stack.progetto, stack.volume, stack.immagine):
        assert nome.startswith(PREFISSO) and stack.sigla in nome
        assert nome not in RISORSE_REALI


def test_la_pulizia_normale_funziona_e_tocca_solo_risorse_proprie(
    stack: Stack, docker: DockerFinto
) -> None:
    stack.smonta()

    distruttivi = docker.distruttivi()
    assert distruttivi, "la pulizia non ha eseguito nulla"
    assert ["docker", "rm", "-f", "-v", "id_proprio_1", "id_proprio_2"] in distruttivi
    assert ["docker", "volume", "rm", "-f", stack.volume] in distruttivi
    assert ["docker", "image", "rm", "-f", stack.immagine] in distruttivi
    assert any("down" in c and "-v" in c and stack.progetto in c for c in distruttivi)
    assert docker.nomina_risorse_reali() == []  # nemmeno il percorso del repo (`beewatch-ai`)


# --------------------------------------------------------------------------- #
# Nomi: se non sono quelli dello stack, non si esegue NIENTE
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "attributo,valore",
    [
        pytest.param("volume", VOLUME_REALE, id="volume-reale"),
        pytest.param("progetto", "beewatch-ai", id="progetto-reale-beewatch-ai"),
        pytest.param("progetto", "beewatch", id="progetto-reale-beewatch"),
        pytest.param("immagine", "beewatch-ai:dev", id="immagine-reale"),
        pytest.param("volume", "un_volume_qualunque", id="volume-senza-prefisso"),
        pytest.param("volume", f"{PREFISSO}_ffffffff_dati", id="volume-di-un-altro-stack"),
        pytest.param("progetto", f"{PREFISSO}-ffffffff", id="progetto-di-un-altro-stack"),
    ],
)
def test_pulizia_con_nome_non_proprio_abortisce_senza_eseguire_nulla(
    stack: Stack, docker: DockerFinto, attributo: str, valore: str
) -> None:
    setattr(stack, attributo, valore)

    with pytest.raises(RisorsaRealeError):
        stack.smonta()

    assert docker.comandi == []  # nemmeno una lettura: si ferma prima


def test_anche_lavvio_con_un_nome_reale_abortisce(stack: Stack, docker: DockerFinto) -> None:
    stack.volume = VOLUME_REALE
    with pytest.raises(RisorsaRealeError):
        stack.avvia()
    assert docker.comandi == []


# --------------------------------------------------------------------------- #
# Ultima barriera: nessun comando può nominare una risorsa reale
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "comando",
    [
        ["volume", "rm", "-f", VOLUME_REALE],
        ["rm", "-f", "-v", "beewatch-mysql"],
        ["image", "rm", "-f", "beewatch-ai:dev"],
        ["compose", "-p", "beewatch-ai", "down", "-v"],
        ["ps", "-aq", "--filter", "label=com.docker.compose.project=beewatch-ai"],
        ["inspect", "/beewatch-mysql"],
        ["volume", "inspect", VOLUME_REALE],
    ],
    ids=lambda c: " ".join(c)[:48],
)
def test_nessun_comando_puo_nominare_una_risorsa_reale(
    stack: Stack, docker: DockerFinto, comando: list[str]
) -> None:
    with pytest.raises(RisorsaRealeError):
        stack.esegui(*comando)
    assert docker.comandi == []


def test_il_percorso_del_repo_non_e_scambiato_per_una_risorsa_reale(
    stack: Stack, docker: DockerFinto, monkeypatch
) -> None:
    """Il repo si chiama `beewatch-ai` e compare nel percorso di `-f`: non è un nome di progetto."""
    monkeypatch.setattr(docker_support, "COMPOSE", Path("/lavoro/beewatch-ai/docker-compose.yml"))

    stack.compose("config")  # non deve sollevare

    assert any("beewatch-ai" in a for c in docker.comandi for a in c)  # il percorso c'era davvero


# --------------------------------------------------------------------------- #
# Configurazione unita: l'override deve aver tolto i nomi fissi
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "difetto",
    [
        pytest.param(
            lambda c: c["services"]["mysql"].update(container_name="beewatch-mysql"),
            id="container-reale",
        ),
        pytest.param(
            lambda c: c["volumes"]["dati_mysql"].update(name=VOLUME_REALE),
            id="volume-reale-override-mancato",
        ),
        pytest.param(
            lambda c: c["services"]["app"].update(image="beewatch-ai:dev"), id="immagine-reale"
        ),
        pytest.param(lambda c: c.update(name="beewatch-ai"), id="progetto-diverso"),
    ],
)
def test_se_lunione_dei_file_nomina_risorse_non_proprie_non_si_avvia_ne_si_pulisce(
    stack: Stack, docker: DockerFinto, difetto
) -> None:
    difetto(docker.config)

    with pytest.raises(RisorsaRealeError):
        stack.avvia()
    with pytest.raises(RisorsaRealeError):
        stack.smonta()

    assert not any("up" in c for c in docker.comandi)
    assert docker.distruttivi() == []


def test_se_la_configurazione_non_si_puo_verificare_non_si_cancella_niente(
    stack: Stack, monkeypatch
) -> None:
    comandi: list[list[str]] = []

    def fallisce(argomenti, **_):
        comandi.append(list(argomenti))
        return subprocess.CompletedProcess(argomenti, 1, stdout="", stderr="errore di compose")

    monkeypatch.setattr(docker_support.subprocess, "run", fallisce)

    with pytest.raises(RisorsaRealeError):
        stack.smonta()
    assert not any(c[1:2] == ["rm"] or "down" in c for c in comandi)


# --------------------------------------------------------------------------- #
# Contenitori trovati per etichetta: si ispezionano TUTTI prima di rimuoverne uno
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "ispezione",
    [
        pytest.param("beewatch-mysql|{progetto}", id="nome-reale-con-etichetta-giusta"),
        pytest.param("beewatch-app|{progetto}", id="altro-nome-reale"),
        pytest.param("{progetto}-mysql-1|beewatch-ai", id="etichetta-di-un-altro-progetto"),
        pytest.param("{progetto}-mysql-1|", id="senza-etichetta"),
    ],
)
def test_un_contenitore_non_proprio_blocca_la_rimozione(
    stack: Stack, docker: DockerFinto, ispezione: str
) -> None:
    docker.ispezione = ispezione.format(progetto=stack.progetto)

    with pytest.raises(RisorsaRealeError):
        stack.smonta()

    assert docker.distruttivi() == []


def test_le_risorse_reali_elencate_corrispondono_al_compose() -> None:
    """Se il compose cambia nome ai contenitori o al volume, questo elenco va aggiornato."""
    testo = docker_support.COMPOSE.read_text(encoding="utf-8")
    for nome in CONTENITORI_REALI | VOLUMI_REALI | IMMAGINI_REALI:
        assert nome in testo, f"{nome} non e' piu' nel docker-compose.yml: aggiorna docker_support"
    assert PROGETTI_REALI  # il progetto reale prende il nome della cartella: `beewatch-ai`


# --------------------------------------------------------------------------- #
# Ogni controllo sui nomi, da solo
# --------------------------------------------------------------------------- #


def test_un_nome_diverso_ma_con_prefisso_e_sigla_giusti_e_comunque_rifiutato(
    stack: Stack, docker: DockerFinto
) -> None:
    """Passa prefisso e non e' reale: lo ferma solo il confronto con il nome originale."""
    stack.volume = f"{PREFISSO}_{stack.sigla}_altro"

    with pytest.raises(RisorsaRealeError, match="modificati"):
        stack.smonta()
    assert docker.comandi == []


@pytest.mark.parametrize("nome", ["volume_estraneo", "postgres_dati"])
def test_un_nome_generato_male_ma_coerente_e_rifiutato_per_prefisso_e_sigla(
    stack: Stack, docker: DockerFinto, nome: str
) -> None:
    """Un errore nella costruzione dei nomi (attributo e originale uguali) non basta."""
    stack.volume = nome
    stack._propri = (stack.progetto, nome, stack.immagine)

    with pytest.raises(RisorsaRealeError, match="non appartiene"):
        stack.smonta()
    assert docker.comandi == []


def test_la_barriera_sui_comandi_basta_da_sola_se_gli_altri_controlli_mancassero(
    stack: Stack, docker: DockerFinto, monkeypatch
) -> None:
    """Difesa a strati: senza controlli su nomi e configurazione, il comando non parte."""
    monkeypatch.setattr(Stack, "_verifica_nomi", lambda self: None)
    monkeypatch.setattr(Stack, "_verifica_configurazione", lambda self: None)
    stack.volume = VOLUME_REALE

    with pytest.raises(RisorsaRealeError, match="comando rifiutato"):
        stack.smonta()

    assert docker.nomina_risorse_reali() == []  # il comando col volume reale non e' partito
