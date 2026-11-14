# Mockup · Blocco 2 · Accesso, registrazione e primi passi

> **Richiesta** il progetto come il mockup ad alta fedeltà, solo con le funzioni vere (2026-11-14)
> **Stato** completato
> **Tavole** 06–12 («Autenticazione»: Accedi, Crea il tuo account, Aggiungi il tuo primo alveare),
> chiaro e scuro
> **Collegati** → `app/schermate/accedi.py` · `registrati.py` · `onboarding.py` · `app/ui.py` ·
> `app/stile/beewatch.css` · `beewatch/sicurezza.py`

## Obiettivo

Le tre schermate prima dell'app: come nel mockup, senza sidebar, con l'interruttore del tema in
alto a destra.

## Cosa c'è

**Accedi e Registrati: schermo diviso.** A sinistra il pannello di benvenuto (logo, «Monitora il
tuo **apiario con l'AI.**», tre caratteristiche con le loro icone, la riga del progetto in fondo)
su un nido d'ape più marcato; a destra il modulo.

| Elemento del mockup | Nell'app |
|---|---|
| Email e Password con le icone, occhio per vedere la password | `st.text_input(icon=…)` |
| Ricordami | sì: 30 giorni su questo browser (blocco 1) |
| «→ Accedi» giallo a tutta larghezza | sì |
| «oppure» fra due righe sottili | sì |
| Continua con Google | **al suo posto** «Entra con l'utente dimostrativo», che esiste davvero |
| Password dimenticata? | **no**: non c'è un servizio di recupero (servirebbe l'invio di email) |
| Nome e Cognome, Email, Password e Conferma | sì; nome e cognome si salvano insieme, come prima |
| barra «Password robusta» sotto la password | sì: `sicurezza.forza_password`, quattro gradini, la fascia anche a parole |
| Nome Apiario / Azienda | sì, facoltativo: l'apiario nasce subito, con il servizio della pagina Alveari |
| Accetto i Termini di Servizio e la Privacy Policy | «Accetto il trattamento dei miei dati descritto in Trasparenza»: è quello che esiste |

**Primi passi: card al centro.** Logo in alto, la fila dei passi (Profilo ✓ · Primo alveare ·
Preferenze), «Passo N di 3», Indietro e Continua, e «Salta configurazione» sotto la card.

| Passo | Campi |
|---|---|
| Profilo | è la registrazione, già fatta: compare con la spunta |
| Primo alveare | codice, apiario (o il suo nome, se non è stato scritto alla registrazione), stato, anno della regina |
| Preferenze | giorni per ricontrollare un alveare, avvisi sulle ispezioni a rischio, consenso all'assistente esterno: le preferenze delle Impostazioni |

Del mockup mancano **tipo d'arnia**, **numero di telaini** e la scelta **«Ispezioni manuali /
Bilancia IoT / Sensori meteo»**: l'app non registra questi dati. Aggiungerli vorrebbe dire cambiare
lo schema e tutte le pagine degli alveari; mostrarli senza salvarli ingannerebbe.

## Decisioni

**1. Niente sidebar prima dell'accesso e nei primi passi.** `st.navigation(position="hidden")`:
da Accedi a Registrati si passa con i link della pagina. Le pagine dell'app restano fuori dal menu
e dietro il lucchetto di `avvia` (M6-T11).

**2. La registrazione non usa `st.form`.** Dentro un form l'indicatore della password si
aggiornerebbe solo all'invio; così si aggiorna appena si esce dal campo.

**3. Gli SVG diventano immagini.** Streamlit ripulisce l'HTML e toglie gli `<svg>`: logo e icone
del pannello si inseriscono come `<img src="data:image/svg+xml;base64,…">`, con il colore del tema
attivo già dentro.

**4. Lo schermo diviso con il CSS dei contenitori con chiave.** Il pannello è il contenitore
`bw_lato_benvenuto`, il modulo `bw_lato_modulo`: il CSS toglie i margini della pagina solo quando
il pannello c'è (`:has(...)`), così le altre pagine non cambiano.

**5. Il quadratino delle caselle.** Con il colore del bordo del mockup (`#F2E9D2`) sul crema non si
vedeva: ora ha il colore del testo secondario.

## Come si prova

| Cosa | Dove |
|---|---|
| Accedi con il titolo «Bentornato», password sbagliata, utente dimostrativo, Esci, database spento | `tests/test_accesso.py` |
| Registrati: nome e cognome insieme, consenso, errori del servizio, apiario creato subito, indicatore della password | `tests/test_accesso.py` |
| primi passi: alveare (con o senza apiario), anno della regina, preferenze salvate, Indietro, Salta, campi obbligatori, database spento, nessuna sidebar | `tests/test_accesso.py` |
| i gradini della robustezza | `tests/test_sicurezza.py` |
| nel browser, chiaro e scuro, a 1440×900: accesso, registrazione completa con l'apiario, primo alveare, preferenze, arrivo nella Home | a mano, con uno stack MySQL isolato |
