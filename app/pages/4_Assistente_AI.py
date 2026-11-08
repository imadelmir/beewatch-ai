"""
BeeWatch AI - pagina Assistente AI: il riepilogo delle note di un'ispezione (M6-T6).

L'anatomia del §6 della specifica, con il banner del §9 subito dopo l'intestazione:

- **banner AI**: permanente, non richiudibile (`banner_ai`);
- **controlli**: l'ispezione da riassumere (fra quelle con note dell'apiario attivo), le sue note
  come le leggerà il modello, il modello e la versione del prompt, il bottone;
- **contenuto**: il riepilogo in forma strutturata (stato di salute, confidenza, elementi rilevati,
  criticità, azioni per priorità, ciò che le note non dicono) e lo storico dei riepiloghi
  dell'ispezione;
- **note** in fondo.

La pagina non parla con il modello di linguaggio: chiama `genera_riepilogo_ispezione` dei servizi,
che costruisce il contesto, valida la risposta, fa al massimo un tentativo correttivo e salva. Il
testo scritto dal modello si mostra come testo semplice: asterischi, cancelletti o link nella
risposta non diventano formattazione.
"""

from __future__ import annotations

import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    alveari_dell_apiario,
    apiari,
    avvia,
    ispezioni_dell_apiario,
    riepiloghi_ispezione,
    svuota_letture,
)
from ui import (
    AZIONE_NESSUN_APIARIO,
    NESSUN_APIARIO,
    banner_ai,
    blocco_vuoto,
    etichetta_rischio,
    formatta_data,
    formatta_numero,
    intestazione,
    metrica,
    mostra_errore,
    sidebar,
)

from beewatch.exceptions import BeeWatchError

STATI_SALUTE = {
    "buono": "✔ Buono",
    "attenzione": "⚠ Attenzione",
    "critico": "✖ Critico",
    "non_determinabile": "? Non determinabile",
}
LIVELLI = {"alta": "Alta", "media": "Media", "bassa": "Bassa"}
ORDINE_PRIORITA = {"alta": 0, "media": 1, "bassa": 2}
CARATTERI_MARKDOWN = "\\`*_{}[]()#+-.!|<>~$"


def testo_semplice(testo: str) -> str:
    """Il testo del modello senza formattazione: ogni carattere speciale di Markdown si annulla."""
    return "".join("\\" + c if c in CARATTERI_MARKDOWN else c for c in testo)


def elenco(voci: list[str], vuoto: str) -> None:
    if voci:
        st.markdown("\n".join(f"- {voce}" for voce in voci))
    else:
        st.caption(vuoto)


def mostra_riepilogo(riepilogo) -> None:
    """Il riepilogo in forma strutturata: niente testo libero del modello fuori dai suoi campi."""
    # Due colonne e non quattro: «⚠ Attenzione» e «? Non determinabile» nella griglia della Home
    # si troncavano, e sono proprio i valori da leggere.
    colonne = st.columns(2)
    with colonne[0]:
        metrica(
            "Stato di salute",
            STATI_SALUTE.get(riepilogo.stato_salute, riepilogo.stato_salute),
            None,
            aiuto="Il giudizio del modello sulle note, non una diagnosi.",
        )
    with colonne[1]:
        metrica(
            "Confidenza",
            LIVELLI.get(riepilogo.confidenza, riepilogo.confidenza),
            None,
            aiuto="Quanto il modello si fida di ciò che ha dedotto: bassa vuol dire note "
            "scarse, ambigue o contraddittorie.",
        )

    st.markdown("**Elementi rilevati**")
    elenco(
        [testo_semplice(e) for e in riepilogo.elementi_rilevati],
        "Il modello non ha indicato elementi.",
    )

    st.markdown("**Criticità**")
    elenco(
        [
            f"{testo_semplice(c.descrizione)} — gravità {LIVELLI.get(c.gravita, c.gravita).lower()}"
            for c in riepilogo.criticita
        ],
        "Nessuna criticità indicata.",
    )

    st.markdown("**Azioni suggerite, dalla più urgente**")
    azioni = sorted(riepilogo.azioni_suggerite, key=lambda a: ORDINE_PRIORITA.get(a.priorita, 3))
    elenco(
        [
            f"**Priorità {LIVELLI.get(a.priorita, a.priorita).lower()}** · "
            f"{testo_semplice(a.azione)}"
            + (f" (entro {a.entro_giorni} giorni)" if a.entro_giorni is not None else "")
            for a in azioni
        ],
        "Nessuna azione suggerita.",
    )

    st.markdown("**Cosa l'AI non ha potuto dedurre dalle note**")
    elenco(
        [testo_semplice(c) for c in riepilogo.campi_non_deducibili],
        "Il modello non ha indicato lacune nelle note.",
    )


def provenienza(modello: str, provider: str, versione: str, durata_ms: int, tentativi: int) -> str:
    secondi = formatta_numero(durata_ms / 1000)
    correttivo = ", con un tentativo correttivo" if tentativi > 1 else ""
    return (
        f"Scritto da **{testo_semplice(modello)}** ({testo_semplice(provider)}) con il prompt "
        f"**{testo_semplice(versione)}**, in {secondi} s{correttivo}."
    )


def titolo_ispezione(ispezione) -> str:
    return (
        f"{formatta_data(ispezione.data_ispezione)} · {ispezione.codice_alveare} · "
        f"{etichetta_rischio(ispezione.livello_rischio)}"
    )


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #

servizi = avvia("Assistente AI", "🤖")
attivo = sidebar()
utente = st.session_state[CHIAVE_UTENTE]

intestazione(
    "🤖 Assistente AI",
    "Un riepilogo delle note di campo di un'ispezione, scritto da un modello di linguaggio.",
)
banner_ai()

try:
    apiari(utente)  # la sidebar non solleva: se il database è giù, lo dice il corpo
    alveari = alveari_dell_apiario(utente, attivo.id) if attivo else ()
    storico = ispezioni_dell_apiario(utente, attivo.id) if alveari else ()
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

if attivo is None:
    blocco_vuoto(NESSUN_APIARIO, AZIONE_NESSUN_APIARIO)
    st.stop()

con_note = [i for i in storico if i.note and i.note.strip()]
if not con_note:
    blocco_vuoto(
        f"Nessuna ispezione con note in {attivo.nome}.",
        "Registrane una in **Ispezioni** scrivendo le note di campo: sono ciò che l'assistente "
        "riassume.",
    )
    st.stop()

# --------------------------------------------------------------------------- #
# Controlli
# --------------------------------------------------------------------------- #

info = servizi.info_assistente()
st.caption(
    f"Assistente: **{info.descrizione}** · prompt **{info.versione_prompt}**. "
    "Le note vengono inviate a questo modello per scrivere il riepilogo."
)

per_id = {i.id: i for i in con_note}
scelta = per_id[
    st.selectbox(
        "Ispezione da riassumere",
        options=list(per_id),
        format_func={i.id: titolo_ispezione(i) for i in con_note}.__getitem__,
        # La chiave segue l'elenco: dopo una nuova ispezione riparte dalla più recente (M6-T4).
        key=f"ispezione_da_riassumere_{hash(tuple(per_id)) & 0xFFFFFFFF:x}",
        help="Le ispezioni dell'apiario attivo che hanno note, dalla più recente.",
    )
]
st.text_area(
    "Le note che il modello leggerà",
    value=scelta.note,
    height=160,
    disabled=True,
    key=f"note_da_riassumere_{scelta.id}",
)

generato = None
if st.button("Genera il riepilogo", type="primary", key="genera_riepilogo"):
    minuti = max(1, round(info.attesa_massima_s / 60))
    try:
        with st.spinner(
            "Sto interrogando il modello: di solito servono da pochi secondi a un minuto, "
            f"ma con un modello locale lento può richiedere fino a circa {minuti} minuti."
        ):
            generato = servizi.genera_riepilogo_ispezione(utente, scelta.id)
    except BeeWatchError as errore:  # LLMError (anche il timeout), ConfigError, ValidationError
        mostra_errore(errore)
    else:
        if generato.salvato:
            svuota_letture()  # lo storico qui sotto deve vederlo

# --------------------------------------------------------------------------- #
# Contenuto
# --------------------------------------------------------------------------- #

try:
    salvati = riepiloghi_ispezione(utente, scelta.id)
except BeeWatchError as errore:
    mostra_errore(errore)
    salvati = None

colonne = st.columns(4)
with colonne[0]:
    metrica(
        "Ispezioni con note",
        len(con_note),
        None,
        aiuto=f"Le ispezioni di {attivo.nome} che l'assistente può riassumere.",
    )
if salvati is not None:
    with colonne[1]:
        metrica(
            "Riepiloghi salvati",
            len(salvati),
            None,
            aiuto="I riepiloghi già generati per l'ispezione scelta.",
        )

if generato is not None:
    st.subheader(f"Riepilogo dell'ispezione del {formatta_data(scelta.data_ispezione)}")
    if not generato.valido:
        st.warning(generato.messaggio, icon="⚠️")
    else:
        mostra_riepilogo(generato.riepilogo)
        if not generato.salvato:
            st.warning(generato.messaggio, icon="⚠️")
    st.caption(
        provenienza(
            generato.modello,
            generato.provider,
            generato.versione_prompt,
            generato.durata_ms,
            generato.tentativi,
        )
    )
    if not generato.in_locale:
        st.caption("Le note di questa ispezione sono state inviate a un servizio esterno.")

st.subheader("Riepiloghi già generati per questa ispezione")

if salvati is not None and not salvati:
    blocco_vuoto(
        "Nessun riepilogo salvato per questa ispezione.",
        "Generane uno con il bottone qui sopra: ogni riepilogo resta, anche i precedenti.",
    )
for salvato in salvati or ():
    creato = salvato.creato_il.strftime("%d/%m/%Y %H:%M")
    confidenza = LIVELLI.get(salvato.riepilogo.confidenza, salvato.riepilogo.confidenza)
    with st.expander(
        f"{creato} · {salvato.modello} · prompt {salvato.versione_prompt} · "
        f"confidenza {confidenza.lower()}"
    ):
        mostra_riepilogo(salvato.riepilogo)
        st.caption(
            provenienza(
                salvato.modello,
                salvato.provider,
                salvato.versione_prompt,
                salvato.durata_ms,
                salvato.tentativi,
            )
        )

# --------------------------------------------------------------------------- #
# Note
# --------------------------------------------------------------------------- #

st.caption(
    "Il riepilogo legge solo le note scritte e qualche dato dell'alveare (le ultime ispezioni, i "
    "raccolti): non vede l'arnia. Le note non vengono modificate. Ogni riepilogo salvato porta con "
    "sé il modello e la versione del prompt che l'hanno scritto."
)
