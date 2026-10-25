"""La struttura dell'interfaccia Streamlit, verificata sul codice (M6-T1).

Nessun avvio di Streamlit: si leggono i file. Verificano le regole della specifica
(`docs/markdown/M6-interfaccia/ui_spec.md`) che altrimenti si romperebbero in silenzio: il tema
uguale a quello approvato, le sei pagine nell'ordine giusto, nessun accesso diretto a database,
modello o provider dentro `app/`, le cache con un tempo dichiarato, lo stato della sessione creato
in un punto solo.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
APP = RADICE / "app"
PAGINE = APP / "pages"
SPEC = RADICE / "docs" / "markdown" / "M6-interfaccia" / "ui_spec.md"

SEI_PAGINE = [
    "1_Alveari.py",
    "2_Ispezioni.py",
    "3_Previsione.py",
    "4_Assistente_AI.py",
    "5_Dashboard.py",
    "6_Trasparenza.py",
]
FILE_APP = sorted(APP.rglob("*.py"))

# Ciò che dentro app/ non si importa (specifica §2, DoD di M6-T1): il livello dati, il modello,
# il provider AI. Le pagine chiamano `beewatch.services`.
IMPORT_VIETATI = (
    "beewatch.database",
    "beewatch.repositories",
    "beewatch.repositories_riferimento",
    "beewatch.ai",
    "beewatch.ml",
    "joblib",
    "pickle",
    "mysql",
    "requests",
    "sqlalchemy",
    "sklearn",
)


def albero(percorso: Path) -> ast.Module:
    return ast.parse(percorso.read_text(encoding="utf-8"), filename=str(percorso))


def moduli_importati(percorso: Path) -> set[str]:
    trovati = set()
    for nodo in ast.walk(albero(percorso)):
        if isinstance(nodo, ast.Import):
            trovati |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            trovati.add(nodo.module)
            trovati |= {f"{nodo.module}.{a.name}" for a in nodo.names}
    return trovati


# --------------------------------------------------------------------------- #
# Tema
# --------------------------------------------------------------------------- #


def blocco_toml_della_specifica() -> dict:
    testo = SPEC.read_text(encoding="utf-8")
    sezione = testo[testo.index("## 5. Tema Streamlit") :]
    blocco = re.search(r"```toml\n(.*?)```", sezione, flags=re.S)
    assert blocco, "il §5 della specifica non ha più un blocco toml"
    return tomllib.loads(blocco.group(1))


def test_il_config_toml_esiste_ed_e_identico_al_paragrafo_5_della_specifica():
    config = tomllib.loads((RADICE / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config == blocco_toml_della_specifica()


def test_i_valori_del_tema_sono_quelli_approvati():
    tema = tomllib.loads((RADICE / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert tema["theme"] == {
        "base": "light",
        "primaryColor": "#C77D02",
        "backgroundColor": "#FFFFFF",
        "secondaryBackgroundColor": "#FAF6F0",
        "textColor": "#1A1A1A",
        "font": "sans serif",
    }
    assert tema["server"]["runOnSave"] is False
    assert tema["browser"]["gatherUsageStats"] is False


def test_il_config_toml_e_tracciato_da_git_e_non_ignorato():
    ignorati = (RADICE / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert not any(
        r.strip().rstrip("/") in (".streamlit", ".streamlit/config.toml") for r in ignorati
    )


# --------------------------------------------------------------------------- #
# Pagine e menu
# --------------------------------------------------------------------------- #


def test_ci_sono_esattamente_le_sei_pagine_della_specifica():
    assert sorted(p.name for p in PAGINE.glob("*.py")) == SEI_PAGINE


def test_lordine_nel_menu_e_quello_del_prefisso_numerico():
    # Streamlit ordina le pagine per il numero davanti al nome (poi alfabeticamente).
    ordinate = sorted(PAGINE.glob("*.py"), key=lambda p: (int(p.name.split("_")[0]), p.name))
    assert [p.name for p in ordinate] == SEI_PAGINE
    assert [int(p.name.split("_")[0]) for p in ordinate] == [1, 2, 3, 4, 5, 6]


def test_il_punto_di_ingresso_e_home_py_e_main_py_non_esiste_piu():
    assert (APP / "Home.py").is_file()
    assert not (APP / "main.py").exists()


@pytest.mark.parametrize("pagina", SEI_PAGINE)
def test_ogni_pagina_parte_con_avvia(pagina):
    sorgente = (PAGINE / pagina).read_text(encoding="utf-8")
    corpo = [
        n for n in albero(PAGINE / pagina).body if not isinstance(n, ast.Import | ast.ImportFrom)
    ]
    corpo = [
        n for n in corpo if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))
    ]
    prima = corpo[0]
    assert isinstance(prima, ast.Expr) and isinstance(prima.value, ast.Call), pagina
    assert prima.value.func.id == "avvia", pagina  # il primo comando è l'avvio comune
    assert "from avvio import avvia" in sorgente


def test_nessun_riferimento_a_app_main_py_resta_nei_file_di_lavoro():
    percorsi = [
        RADICE / "Dockerfile",
        RADICE / "docker-compose.yml",
        RADICE / "README.md",
        *FILE_APP,
    ]
    percorsi += [RADICE / "tests" / f for f in ("test_docker_compose.py", "test_docker_stack.py")]
    for percorso in percorsi:
        assert "app/main.py" not in percorso.read_text(encoding="utf-8"), percorso


def test_il_dockerfile_avvia_home_py_e_copia_la_cartella_di_streamlit():
    dockerfile = (RADICE / "Dockerfile").read_text(encoding="utf-8")
    assert '"streamlit", "run", "app/Home.py"' in dockerfile
    assert "COPY .streamlit/ ./.streamlit/" in dockerfile
    ignorati = (RADICE / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert not any(r.strip().rstrip("/") in (".streamlit", "app") for r in ignorati)


# --------------------------------------------------------------------------- #
# Nessuna logica applicativa dentro app/
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("percorso", FILE_APP, ids=lambda p: str(p.relative_to(APP)))
def test_nessun_import_proibito_dentro_app(percorso):
    importati = moduli_importati(percorso)
    trovati = sorted(
        m for m in importati for v in IMPORT_VIETATI if m == v or m.startswith(v + ".")
    )
    assert trovati == [], f"{percorso.name} importa {trovati}"


def test_il_client_del_modello_di_linguaggio_non_si_importa_nemmeno_per_nome():
    for percorso in FILE_APP:
        importati = moduli_importati(percorso)
        assert not any(m.startswith("beewatch.ai.llm") for m in importati), percorso
        assert not any(n.endswith(("crea_client", "LLMClient")) for n in importati), percorso


def test_le_pagine_chiamano_i_servizi_non_il_resto_di_beewatch():
    consentiti = {
        "beewatch.services",
        "beewatch.exceptions",
        "beewatch.logging_config",
        "beewatch.config",
        "beewatch",
    }
    for percorso in FILE_APP:
        propri = {m for m in moduli_importati(percorso) if m.split(".")[0] == "beewatch"}
        estranei = {
            m for m in propri if not any(m == c or m.startswith(c + ".") for c in consentiti)
        }
        assert estranei == set(), (percorso.name, estranei)


def test_nessun_sql_nei_file_di_app():
    for percorso in FILE_APP:
        assert not re.search(
            r"\b(SELECT|INSERT INTO|UPDATE \w+ SET|DELETE FROM)\b",
            percorso.read_text(encoding="utf-8"),
        ), percorso


def test_nessun_css_ne_html_iniettato():
    # Specifica §2 e §13: il tema è nativo. L'unica eccezione (badge_stato, M6-T2) non c'è ancora.
    for percorso in FILE_APP:
        testo = percorso.read_text(encoding="utf-8")
        assert "unsafe_allow_html" not in testo, percorso
        assert "<style" not in testo.lower(), percorso


def test_home_non_definisce_funzioni_ne_classi_ne_cicli():
    # Home mostra la panoramica: niente logica applicativa. Un'euristica, ma onesta: se serve una
    # funzione, va in avvio.py o nei servizi.
    nodi = [type(n).__name__ for n in ast.walk(albero(APP / "Home.py"))]
    for vietato in ("FunctionDef", "AsyncFunctionDef", "ClassDef", "For", "While", "Lambda"):
        assert vietato not in nodi, vietato


# --------------------------------------------------------------------------- #
# Cache e stato
# --------------------------------------------------------------------------- #


def decoratori(percorso: Path) -> dict[str, list[ast.expr]]:
    return {
        n.name: n.decorator_list
        for n in ast.walk(albero(percorso))
        if isinstance(n, ast.FunctionDef)
    }


def nome_decoratore(d: ast.expr) -> str:
    chiamata = d.func if isinstance(d, ast.Call) else d
    return ast.unparse(chiamata)


def test_servizi_e_modello_sono_risorse_in_cache():
    d = decoratori(APP / "avvio.py")
    assert nome_decoratore(d["servizi"][0]) == "st.cache_resource"
    assert nome_decoratore(d["modello"][0]) == "st.cache_resource"


def test_ogni_lettura_in_cache_ha_un_tempo_dichiarato():
    letture = 0
    for percorso in FILE_APP:
        for nome, lista in decoratori(percorso).items():
            for d in lista:
                if nome_decoratore(d) == "st.cache_data":
                    letture += 1
                    assert isinstance(d, ast.Call), f"{percorso.name}:{nome} senza ttl"
                    ttl = {k.arg: ast.unparse(k.value) for k in d.keywords}.get("ttl")
                    assert ttl, f"{percorso.name}:{nome} senza ttl"
    assert letture >= 1


def test_il_ttl_e_una_costante_dichiarata_e_ragionevole():
    sorgente = (APP / "avvio.py").read_text(encoding="utf-8")
    valore = int(re.search(r"^TTL_LETTURE_SECONDI = (\d+)", sorgente, flags=re.M).group(1))
    assert (
        10 <= valore <= 300
    )  # abbastanza per non rifare le query, abbastanza poco per i dati nuovi


def test_lo_stato_della_sessione_nasce_solo_in_avvio_py():
    for percorso in FILE_APP:
        if percorso.name == "avvio.py":
            continue
        for nodo in ast.walk(albero(percorso)):
            scrive = (
                isinstance(nodo, ast.Assign)
                and any("session_state" in ast.unparse(t) for t in nodo.targets)
            ) or (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and "session_state" in ast.unparse(nodo.func.value)
                and nodo.func.attr in {"setdefault", "update", "pop"}
            )
            assert not scrive, f"{percorso.name} scrive in session_state"


def test_lapiario_attivo_e_una_chiave_dello_stato_inizializzata_in_un_punto():
    sorgente = (APP / "avvio.py").read_text(encoding="utf-8")
    assert 'CHIAVE_APIARIO_ATTIVO = "apiario_attivo_id"' in sorgente
    assert sorgente.count("st.session_state.setdefault(") == 2  # utente e apiario attivo
