# M2 - T3 · Target di regressione e limiti di dominio

> **Milestone** M2 · Dati e database
> **Stato** completata
> **Commit** `M2 - T3 : choose regression target, measure baselines and define domain limits`
> **Risultati completi** → [`dati.md`](dati.md), sezioni *Il target*, *Modelli di riferimento*, *Limiti di trasferibilità*, *Cosa vedrà l'utente*

## Obiettivo

Scegliere e motivare cosa il modello deve prevedere, misurare quanto è difficile
il problema, e decidere **come si comunica una stima incerta** a un utente che
non è uno statistico.

## La scelta

**Il modello prevede `resa_per_colonia_kg`: quanto miele produce in media una
singola colonia in una stagione.**

Quattro delle sei grandezze numeriche si escludono da sole. `totalprod` e
`prodvalue` sono calcolate dalle altre (data leakage). `numcol` lo decide
l'apicoltore, non le api. `stocks` e `priceperlb` dipendono dal mercato.

Resta `yieldpercol`, ed è anche la scelta giusta nel merito: è l'unica grandezza
biologica, è indipendente dalla scala — un apiario di tre alveari e uno stato
con 500 000 colonie hanno rese confrontabili — ha la distribuzione più regolare,
ed è la domanda che l'utente si pone davvero.

## La cosa più importante di questa task

Sono stati misurati **due modelli banali**, per sapere quanto è difficile il
problema prima di affrontarlo. Su una divisione temporale onesta — si addestra
sul 1998-2009, si verifica sul 2010-2012:

| Modello di riferimento | MAE | R² |
|---|---|---|
| Predice sempre la media globale | 6,46 kg | −0,257 |
| Predice la media del suo stato | 5,73 kg | 0,134 |
| Media dello stato **+ tendenza annuale** | **4,25 kg** | 0,442 |

> **Un modello di machine learning che non scende sotto 4,25 kg di MAE su una
> divisione temporale non serve a niente: due medie e una retta fanno lo stesso.**

Quel numero diventa il **criterio di accettazione di M4**, dichiarato in
anticipo. Un progetto che sa quale soglia deve battere è molto più credibile di
uno che mostra un R² senza contesto.

> **Aggiornamento (ottobre 2026, DA-05).** In M4-T1 la baseline di persistenza
> (resa dell'anno prima) ha dato un MAE di 4,06 kg, più basso di 4,25. Il criterio
> di M4 è diventato *battere la persistenza* sulla stessa verifica; 4,25 kg resta
> come riferimento storico. Vedi
> [`DA-05_criterio_di_accettazione.md`](../M4-machine-learning/DA-05_criterio_di_accettazione.md).

L'R² negativo della prima riga dice una cosa precisa: predire la media del
passato è *peggio* che predire la media del futuro, perché la resa è calata e il
passato sovrastima sistematicamente.

## Una trappola documentata

Un terzo "modello" che predice la media del gruppo (stato, anno) ottiene MAE
0,00 e R² 1,000. Non è un modello: (`stato`, `anno`) è la chiave del dataset,
ogni gruppo contiene una riga sola e la "media" è il valore stesso.

È la stessa forma di errore del data leakage, travestita da aggregazione. **Se
in M4 un modello restituisce R² sospettosamente vicino a 1, è lì che bisogna
guardare.**

## I cinque limiti di trasferibilità

I dati descrivono apicoltura **commerciale statunitense aggregata per stato, dal
1998 al 2012**. L'utente è un apicoltore **amatoriale italiano nel 2026**.

1. **Aggregazione** — una riga è la media di uno stato intero, non descrive
   nessun apiario in particolare
2. **Scala e gestione** — nomadismo, selezione genetica, trattamenti programmati
3. **Geografia** — nessuno stato del dataset ha il clima italiano
4. **Epoca** — i dati si fermano al 2012, il modello estrapola di quattordici anni
5. **Variabili assenti** — forza della famiglia, regina, varroa, fioriture, meteo

Il modello **non è uno strumento diagnostico e non sostituisce un veterinario o
un tecnico apistico**. Questa frase deve comparire nell'applicazione, non solo
nel documento: è uno dei cinque punti etici obbligatori (M6-T8, M7-T4).

## Cosa vedrà l'utente

Un limite scritto in un documento che nessuno legge non è una mitigazione. Da
qui quattro regole che diventano requisiti di M6-T5 e M6-T8:

- **Mai un numero secco.** Sempre un intervallo, più in evidenza del valore
  centrale. L'80 % dei casi reali sta fra 18 e 40 kg.
- **Mai una percentuale di accuratezza.** Non significa nulla in una regressione
  e induce una fiducia che il modello non merita.
- **Mai un consiglio operativo derivato dalla previsione.** Il modello non sa
  niente del singolo alveare.
- **Se l'intervallo diventasse più largo della stima, la stima non si mostra.**
  Un intervallo `5 – 55 kg` non informa nessuno, e mostrarlo sarebbe peggio che
  tacere.

## File prodotti

| File | Contenuto |
|---|---|
| `docs/markdown/M2-dati/dati.md` | quattro sezioni nuove più l'indice del documento |

## Definition of Done

| Verifica | Esito |
|---|---|
| Target scelto e motivato | ✅ con l'esclusione motivata delle altre cinque grandezze |
| Sezione limiti di trasferibilità | ✅ cinque limiti, più la tabella di cosa possiamo e non possiamo dire |
| Strategia di comunicazione definita | ✅ formato della previsione e quattro divieti |
| *(oltre la DoD)* soglia di accettazione per M4 | ✅ MAE < 4,25 kg, misurata (sostituita da DA-05 in M4) |

## Miglioramenti futuri

- L'intervallo mostrato all'utente andrà costruito sui **residui reali** del
  modello di M4, non sui baseline: ± 6 kg è il valore provvisorio.
- La `versione_modello` e le sue metriche vivranno nella tabella `modelli`
  (M2-T4), così l'interfaccia potrà scrivere l'errore medio accanto alla stima.
