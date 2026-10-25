# M5 - T3 · Schema di output strutturato e parser

> **Milestone** M5 · Componente AI generativa
> **Task** M5-T3
> **Stato** completata
> **Commit** `feat(m5): add the structured inspection summary schema and parser`
> **Collegati** → [`M5-T2_robustezza_chiamate.md`](M5-T2_robustezza_chiamate.md) · `beewatch/ai/riepilogo.py` · `tests/test_riepilogo.py`

## Obiettivo

Il modello risponde con testo. Anche chiedendogli JSON può restituire una risposta troncata, con
una frase prima e dopo, con un campo dimenticato o con un valore inventato («ottimo» invece di
«buono»). L'app non deve né crashare né mostrare all'utente una risposta che non rispetta lo
schema. Questo task definisce lo schema del riepilogo di un'ispezione e il codice che lo fa
rispettare. I prompt (M5-T4) e il salvataggio (M5-T5) sono altrove.

## Lo schema

Tutti i campi sono **obbligatori**: un campo assente non si distingue da uno dimenticato. Un elenco
può essere vuoto. I campi in più vengono ignorati.

| Campo | Tipo | Valori |
|---|---|---|
| `stato_salute` | stringa | `buono`, `attenzione`, `critico`, `non_determinabile` |
| `elementi_rilevati` | elenco di testi | ciò che le note dicono, max 20 voci |
| `criticita` | elenco di `{descrizione, gravita}` | `gravita`: `bassa`, `media`, `alta` |
| `azioni_suggerite` | elenco di `{azione, priorita, entro_giorni?}` | `priorita`: `bassa`, `media`, `alta`; `entro_giorni`: intero 1-365 oppure `null`/assente |
| `confidenza` | stringa | `alta`, `media`, `bassa` |
| `campi_non_deducibili` | elenco di testi | ciò che le note NON permettono di sapere |

Ogni testo è non vuoto e lungo al massimo 1000 caratteri. Maiuscole e spazi nei valori ammessi si
normalizzano (« Critico » → `critico`).

`non_determinabile` esiste perché «non so» è una risposta legittima: costringere il modello a
scegliere tra buono e critico con note vuote lo porta a inventare. `campi_non_deducibili` serve
allo stesso scopo: dichiarare il vuoto invece di riempirlo.

### Esempio valido

```json
{
  "stato_salute": "attenzione",
  "elementi_rilevati": ["regina vista", "covata compatta"],
  "criticita": [{"descrizione": "scorte scarse", "gravita": "media"}],
  "azioni_suggerite": [
    {"azione": "controllare le scorte", "priorita": "alta", "entro_giorni": 7}
  ],
  "confidenza": "media",
  "campi_non_deducibili": ["presenza di varroa"]
}
```

Valido anche con tutti gli elenchi vuoti, `stato_salute: "non_determinabile"` e `confidenza: "bassa"`.

### Esempi non validi (e cosa risponde il parser)

| Risposta del modello | Problema riportato |
|---|---|
| `{"stato_salute": "buono"}` | `campi mancanti: elementi_rilevati, criticita, …` |
| `"stato_salute": "ottimo"` | `stato_salute: «ottimo» non ammesso (ammessi: buono, attenzione, …)` |
| `"elementi_rilevati": "regina vista"` | `elementi_rilevati: deve essere un elenco` |
| `"criticita": [{"descrizione": "x", "gravita": "enorme"}]` | `criticita[0].gravita: «enorme» non ammesso …` |
| `"entro_giorni": "7"`, `7.5`, `true`, `0`, `366` | `…entro_giorni: deve essere un numero intero di giorni oppure null` / `fuori da 1-365` |
| JSON interrotto a metà | `il JSON è malformato o troncato` |
| `Non ho capito la richiesta.` | `la risposta non contiene un oggetto JSON` |

La validazione elenca **tutti** i problemi, non solo il primo: servono al messaggio correttivo.

## Cosa fa il codice (`beewatch/ai/riepilogo.py`)

1. **`estrai_json`** toglie recinti ```` ```json ````, frasi prima e dopo, graffe sparse nel testo
   precedente (prova ogni `{` con `json.JSONDecoder.raw_decode`). Non ripara il JSON rotto. Se il testo
   cita `"stato_salute"` ma nessun oggetto decifrabile lo contiene, è troncato: *non* si prende per
   buono l'oggetto annidato che per caso è rimasto intero (una criticità, un'azione).
2. **`valida_riepilogo`** costruisce il `Riepilogo` (dataclass congelate, senza librerie) o solleva
   `RiepilogoNonValido` con l'elenco dei problemi. È una sottoclasse di `LLMError`.
3. **`genera_riepilogo(client, sistema, utente)`** usa il client di M5-T1/T2:
   - risposta valida → una sola chiamata;
   - non valida → **una** seconda chiamata che ripete la richiesta, mostra al modello la sua risposta
     sbagliata (troncata a 2000 caratteri) e i problemi trovati, e chiede un solo oggetto JSON;
   - non valida di nuovo → **nessuna terza chiamata**: `EsitoRiepilogo(valido=False)` con
     `Riepilogo.non_disponibile()`, un riepilogo onesto («stato non determinabile», confidenza bassa, e
     la spiegazione che il modello non ha prodotto nulla di leggibile; le note non sono state toccate).

`EsitoRiepilogo` porta una `RispostaLLM` per ogni chiamata, con durata e token sommabili: M5-T5 salverà
modello, durata e token veri.

## Decisioni

**1. Un errore del provider non si corregge con una frase.** `LLMError` (server spento, chiave
rifiutata, timeout dopo i tentativi di M5-T2) esce da `genera_riepilogo`: il tentativo correttivo è
solo per i problemi di *formato*. Chi chiama (M5-T5) sa distinguere i due casi.

**2. Il fallback non è un riepilogo finto.** Il «non disponibile» ha `valido=False`: chi lo salva o lo
mostra può dirlo all'utente invece di spacciarlo per l'opinione del modello.

**3. Nessuna riparazione del JSON.** Chiudere parentesi o aggiungere virgole su una risposta troncata
significherebbe inventare il contenuto che manca. Meglio chiedere di nuovo.

**4. Log senza contenuti.** Al fallimento si registrano il numero del tentativo, la lunghezza della
risposta e i problemi (nomi di campi e tipi), mai il testo del modello né le note.

**5. Nessun pydantic.** Il progetto non lo usa; le dataclass e le funzioni di validazione bastano e non
aggiungono una dipendenza.

## Limiti dichiarati

Lo schema controlla la **forma**, non la **verità**: un modello può restituire un JSON perfetto con
una criticità inventata. Per questo ci sono `confidenza` e `campi_non_deducibili`, e il prompt (M5-T4)
dovrà vietare dati non presenti nelle note. Che un modello vero rispetti questi vincoli non si dimostra
con i test automatici e va verificato a mano (vedi #26).

## Test di mutazione

17 mutanti sul codice (un tentativo in più o in meno, `entro_giorni` 0 e 366 accettati, booleano preso per
numero, limiti di lunghezza spostati, valori non normalizzati, oggetto annidato preso per risposta,
campi mancanti ignorati, JSON non richiesto, fallback marcato valido, messaggio correttivo senza
i problemi, token sommati con `None`…): **17 uccisi**, nessun sopravvissuto.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/ai/riepilogo.py` | creato: schema, estrazione, validazione, generazione |
| `tests/test_riepilogo.py` | creato (72 test, `riepilogo.py` al 100%) |
| `tests/llm_fake.py` | creato: `LLMFinto`, un client finto senza rete, riusabile da M5-T5 e M5-T6 |

## Definition of Done

| Voce | Prova |
|---|---|
| schema documentato con esempi validi e non validi | sezioni «Lo schema» e «Esempi non validi» sopra |
| test con JSON troncato, testo attorno al JSON, campi mancanti | `test_json_troncato_e_un_errore_chiaro` (30/50/90%), `test_testo_prima_e_dopo_il_json`, `test_ogni_campo_mancante_e_nominato` (6 campi), `test_json_troncato_poi_corretto_al_secondo_tentativo` |
| nessun crash in nessuno dei casi | `test_nessuna_eccezione_per_nessuna_risposta_malformata` (14 risposte strane → fallback, mai un'eccezione); `test_due_fallimenti_danno_il_fallback_senza_terza_chiamata` |
