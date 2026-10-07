# =========================================================================== #
# BeeWatch AI - immagine dell'applicazione
# =========================================================================== #
#
#   docker compose build                    costruisce
#   docker compose up --build               avvia app + database
#   docker compose up -d mysql              solo il database (sviluppo normale)
#
# Durante lo sviluppo conviene far girare Streamlit sul computer e tenere nel
# contenitore solo MySQL: si ricarica a ogni salvataggio. Questa immagine serve
# alla consegna e a dimostrare che il progetto gira su una macchina che non ha
# niente installato.

FROM python:3.11-slim

# --------------------------------------------------------------------------- #
# Impostazioni di Python nel contenitore
# --------------------------------------------------------------------------- #
#   PYTHONDONTWRITEBYTECODE  niente file .pyc: l'immagine resta piu' pulita
#   PYTHONUNBUFFERED         i log escono subito, non a blocchi: senza, in caso
#                            di crash gli ultimi messaggi andrebbero persi
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# --------------------------------------------------------------------------- #
# Dipendenze
# --------------------------------------------------------------------------- #
# Copiate PRIMA del codice, e da sole. Docker riusa il livello gia' costruito
# finche' questo file non cambia: modificare una riga di Python non fa
# reinstallare pandas e scikit-learn, che sono la parte lenta.
#
# Solo `requirements.txt`, mai `requirements-dev.txt`: pytest e ruff servono a
# sviluppare, non a far girare l'applicazione, e un'immagine di consegna che li
# contiene dichiara di essere qualcosa che non e'.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------------------------------- #
# Il progetto
# --------------------------------------------------------------------------- #
COPY pyproject.toml README.md ./
COPY beewatch/ ./beewatch/
COPY app/ ./app/

# --no-deps: le dipendenze sono gia' installate sopra. Serve solo a rendere
# `import beewatch` disponibile da qualsiasi cartella.
RUN pip install --no-cache-dir --no-deps -e .

# --------------------------------------------------------------------------- #
# Utente non privilegiato
# --------------------------------------------------------------------------- #
# Un contenitore che gira come root e' un contenitore in cui una falla
# dell'applicazione diventa una falla della macchina. Costa due righe.
RUN useradd --create-home --uid 1000 beewatch \
    && chown -R beewatch:beewatch /app
USER beewatch

EXPOSE 8501

# "Sano" non vuol dire solo "Streamlit risponde": un'app che non vede il database
# non serve a nessuno. `beewatch.healthcheck` controlla, in ordine, che la
# configurazione sia valida, che Streamlit risponda (/_stcore/health) e che MySQL
# accetti le credenziali dell'app. Esce con 1 e una riga di motivo se qualcosa non va
# (la vedi in `docker inspect`), e non scrive nulla ne' stampa credenziali.
#
# --timeout sta sopra la somma dei due controlli di rete (3 secondi ciascuno).
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD ["python", "-m", "beewatch.healthcheck"]

# --server.address=0.0.0.0 e' obbligatorio: per impostazione predefinita
# Streamlit ascolta solo su localhost, che dentro un contenitore significa
# "nessuno puo' raggiungermi".
CMD ["streamlit", "run", "app/main.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
