"""
BeeWatch AI - pagina Trasparenza: dati, intelligenza artificiale e limiti, detti chiaro (M6-T8).

La dichiarazione etica è parte del prodotto. La pagina dice, in linguaggio non tecnico:

- quali dati tratta l'applicazione e dove li conserva;
- che i riepiloghi li scrive un'intelligenza artificiale generativa, e se le note escono dal PC
  (lo dice in base al provider configurato in questa installazione);
- i limiti del modello di previsione, con i numeri letti dal suo file di metadati;
- che non sostituisce un veterinario o un tecnico apistico;
- le regole che la riguardano (GDPR art. 5, 6, 17; AI Act art. 50).

I paragrafi stanno in `SEZIONI` e sono gli stessi di `docs/etica.md`, parola per parola: un test lo
controlla, così pagina e documento non possono divergere.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia, modello
from ui import formatta_numero, intestazione, metrica, mostra_errore, sidebar

from beewatch.exceptions import BeeWatchError

SEZIONI: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Che cosa fa BeeWatch AI",
        (
            "BeeWatch AI è un quaderno di campo per l'apicoltore amatoriale. Tiene l'anagrafica "
            "di apiari e alveari, il registro delle ispezioni e dei raccolti, e offre due aiuti: "
            "una stima della produzione di miele e un riepilogo scritto delle note di campo.",
            "Entrambi gli aiuti possono sbagliare. Questa pagina spiega come funzionano, dove "
            "possono sbagliare e che cosa succede ai tuoi dati.",
        ),
    ),
    (
        "Quali dati tratta e dove li conserva",
        (
            "L'applicazione conserva i dati che scrivi tu: il nome e l'indirizzo email del "
            "profilo, gli apiari con la località e, se le inserisci, le coordinate, gli alveari, "
            "le ispezioni con le note di campo, i raccolti, le stime di produzione e i riepiloghi "
            "scritti dall'assistente.",
            "La password non si salva: si salva solo un'impronta cifrata (hash), da cui non si "
            "può risalire alla password. Chi entra vede solo i propri apiari e i propri dati.",
            "Tutto sta in un database MySQL sul computer dove gira l'applicazione, dentro un "
            "contenitore Docker. Nessun dato viene copiato su un servizio esterno, con una sola "
            "eccezione possibile: le note di un'ispezione, quando chiedi un riepilogo e "
            "l'assistente usa un servizio esterno (vedi sotto).",
            "Le coordinate e la località degli apiari non vengono mai inviate all'assistente: per "
            "riassumere le note non servono. I file di registro (log) annotano che cosa è "
            "successo, ma non contengono il testo delle note.",
            "Il database è costruito per cancellare tutto: eliminando un utente spariscono con lui "
            "apiari, alveari, ispezioni, raccolti, stime e riepiloghi.",
        ),
    ),
    (
        "Un'intelligenza artificiale generativa scrive i riepiloghi",
        (
            "I riepiloghi della pagina Assistente AI li scrive un modello di linguaggio: un "
            "programma che ha imparato a produrre testo leggendone moltissimo. Non legge "
            "l'arnia: legge solo le note che hai scritto e qualche dato dell'alveare.",
            "Può sbagliare, inventare o fraintendere un'abbreviazione. Per questo ogni riepilogo "
            "dichiara quanto il modello si fida di sé (la confidenza), elenca che cosa le note non "
            "dicono, porta il nome del modello e la versione delle istruzioni che ha ricevuto (il "
            "prompt), e sta sotto un avviso che non si può chiudere.",
            "Se l'assistente gira sul tuo computer (Ollama), le note restano lì. Se usa un "
            "servizio esterno (OpenRouter), le note di quell'ispezione escono dal PC e vengono "
            "lette da quel servizio: l'applicazione lo dice prima di generare e lo ripete sotto "
            "il riepilogo.",
        ),
    ),
    (
        "I limiti del modello di previsione",
        (
            "Il modello di previsione ha imparato dalle rese medie per colonia degli stati USA, "
            "rilevate dal Dipartimento dell'Agricoltura statunitense (USDA) fra il 1998 e il "
            "2012. Stima quanto miele produce in media una colonia in uno stato e in un anno.",
            "Fra quei dati e il tuo apiario ci sono cinque distanze. Sono medie di stati interi, "
            "non di un apiario. Vengono da apicoltura commerciale, con nomadismo e selezione, non "
            "da poche arnie fisse. Nessuno stato del dataset ha il clima italiano. I dati si "
            "fermano al 2012. E mancano le cose che osservi davvero: forza della famiglia, "
            "regina, varroa, fioriture, meteo.",
            "Per questo una stima non è mai un numero solo: è sempre un intervallo, e quando "
            "l'intervallo è più largo della stima il valore centrale non si mostra. Va letta come "
            "ordine di grandezza, non come la produzione del tuo alveare.",
        ),
    ),
    (
        "Non sostituisce un veterinario",
        (
            "BeeWatch AI non è uno strumento diagnostico. Non sostituisce un veterinario né un "
            "tecnico apistico: per malattie, parassiti o una famiglia in difficoltà, rivolgiti al "
            "servizio veterinario della tua ASL o a un tecnico.",
        ),
    ),
    (
        "Le regole che valgono per i tuoi dati",
        (
            "GDPR, il regolamento europeo sulla protezione dei dati. Art. 5: si raccolgono solo i "
            "dati che servono, per lo scopo dichiarato, e si conservano al sicuro. Art. 6: i dati "
            "si trattano perché sei tu a usare l'applicazione e a inserirli. Art. 17: hai il "
            "diritto di farli cancellare, e il database è costruito per cancellarli tutti.",
            "AI Act, il regolamento europeo sull'intelligenza artificiale. BeeWatch AI non rientra "
            "fra i sistemi ad alto rischio: è un aiuto per un hobby, a rischio minimo. Vale però "
            "l'art. 50, sulla trasparenza: chi legge un testo scritto da un'intelligenza "
            "artificiale deve saperlo. Per questo c'è l'avviso sopra ogni riepilogo e c'è questa "
            "pagina.",
        ),
    ),
)

AVVERTENZA_VETERINARIO = SEZIONI[4][1][0]


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #

servizi = avvia("Trasparenza", "🔍")
sidebar()

intestazione(
    "🔍 Trasparenza",
    "Quali dati usa l'applicazione, chi scrive i riepiloghi e dove le stime possono sbagliare.",
)

# La frase più importante sta in cima, dove non si può non vederla.
st.warning(AVVERTENZA_VETERINARIO, icon="⚠️")

# Questa installazione: l'assistente è locale o esterno?
info = servizi.info_assistente()
st.subheader("L'assistente di questa installazione")
if info.in_locale is True:
    st.success(
        f"L'assistente usa **{info.descrizione}**, che gira su questo computer: le note delle "
        "ispezioni non escono dal PC.",
        icon="🏠",
    )
elif info.in_locale is False:
    st.warning(
        f"L'assistente usa **{info.descrizione}**, un servizio esterno: quando chiedi un "
        "riepilogo, le note di quell'ispezione escono dal PC e vengono inviate a quel servizio.",
        icon="🌐",
    )
else:
    st.info(
        "L'assistente non è configurato in questa installazione: nessuna nota viene inviata a un "
        "modello di linguaggio.",
        icon="ℹ️",
    )

# Il modello di previsione, con i suoi numeri letti dal file dei metadati.
st.subheader("Il modello di previsione in uso")
try:
    stato = modello()
except BeeWatchError as errore:
    mostra_errore(errore)
else:
    colonne = st.columns(4)
    with colonne[0]:
        metrica(
            "Errore medio",
            stato.mae_kg,
            "kg",
            aiuto="Di quanti chili per colonia sbaglia in media, su anni che non aveva visto.",
        )
    with colonne[1]:
        metrica("Righe di addestramento", stato.righe_addestramento, None)
    st.caption(
        f"Modello {stato.versione} ({stato.algoritmo}): in media sbaglia di "
        f"{formatta_numero(stato.mae_kg)} kg per colonia sul 2010–2012."
    )

for titolo, paragrafi in SEZIONI:
    st.subheader(titolo)
    for paragrafo in paragrafi:
        st.markdown(paragrafo)

st.caption(
    "Questa pagina riprende, parola per parola, il documento etico del progetto "
    "(`docs/etica.md`), dove gli stessi punti sono spiegati con i riferimenti al codice."
)
