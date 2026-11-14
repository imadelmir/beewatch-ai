# M6 - T10 · Tema, stile e identità visiva

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T10 (issue #56, P1)
> **Stato** completata
> **Commit** `feat(m6): bring the mockup identity in through the native theme and pin UI versions`
> **Collegati** → [`ui_spec.md`](ui_spec.md) §2, §3, §5, §13 · `.streamlit/config.toml` · mockup `BeeWatch-AI_Mockup-UI_corretto` (fuori dal repository)

## Obiettivo

Dalla issue: «dare all'applicazione l'identità visiva del mockup senza compromettere la stabilità:
tutto il CSS in un unico punto, versioni bloccate, e un'app che resta pienamente usabile anche se lo
stile non venisse applicato». La issue non ha una Definition of Done compilata: quella usata qui è in
fondo, ricavata dalla descrizione.

## Che cosa ho preso dal mockup, e che cosa no

Il mockup ad alta fedeltà (57 tavole, design system chiaro e scuro) ha: accento giallo miele, card
con angoli arrotondati e bordo leggero, titoli in grassetto, sidebar chiara color miele, valori delle
metriche grandi e leggibili, font Poppins, tema scuro, sfondo a nido d'ape.

| Elemento del mockup | Come | Dove |
|---|---|---|
| card arrotondate con bordo leggero | `baseRadius = "0.75rem"`, `borderColor`, `showWidgetBorder` | tema nativo |
| bottoni arrotondati | `buttonRadius = "0.5rem"` | tema nativo |
| titoli in grassetto | `headingFontWeights` | tema nativo |
| sidebar color miele | `[theme.sidebar] backgroundColor = "#FFF8E7"`, `showSidebarBorder` | tema nativo |
| valori delle metriche leggibili | `metricValueFontSize = "1.875rem"`: un po' più piccoli del predefinito, così entrano nelle card della griglia a quattro colonne | tema nativo |
| intestazioni delle tabelle, link, colori dei grafici | `dataframeHeaderBackgroundColor`, `linkColor`, `chartCategoricalColors` dalla palette del §3 | tema nativo |
| tema scuro | **no**: §13 della specifica (raddoppia le combinazioni da verificare, zero requisiti) | — |
| font Poppins | **no**: §13 (un font esterno è una richiesta di rete o un file da aggiungere al repository) | — |
| sfondo a nido d'ape | **no**: richiede CSS iniettato | — |
| accento giallo `#F5B301` | **no**, resta l'ambra `#C77D02` approvata nel §3: il giallo del mockup su fondo bianco non ha il contrasto per il testo | — |

## Decisioni

**1. Il punto unico dello stile è `.streamlit/config.toml`, e il CSS è zero.** Streamlit 1.60 ha chiavi
native per quasi tutto ciò che il mockup chiedeva (raggi, bordi, pesi dei titoli, dimensione delle
metriche, sidebar separata). Con il tema nativo le regole del §2 e del §13 restano intatte: nessun
`unsafe_allow_html` oltre a `badge_stato`, nessun selettore delle classi interne di Streamlit che un
aggiornamento potrebbe rompere. Un test vieta file `.css` nell'app.

**2. Senza stile l'app è la stessa.** Il tema cambia solo l'aspetto: senza `config.toml` l'app gira
con il tema predefinito di Streamlit, con tutti i contenuti e tutte le funzioni. Tutti i test AppTest
girano proprio così (AppTest non applica il tema), e sono verdi.

**3. Versioni bloccate.** `streamlit>=1.60,<1.68` e `plotly>=5.24,<7` in `requirements.txt` e in
`pyproject.toml`: l'intervallo provato (1.60 in locale, 1.67 in CI). Un test controlla che ci siano un
minimo e un massimo e che la versione installata ci rientri. Un altro controlla che **ogni chiave del
tema esista** nella versione installata: Streamlit ignora in silenzio una chiave sbagliata, il test no.

**4. La specifica è aggiornata.** Il §5 contiene il nuovo blocco `toml` (un test lo confronta con il
file) e una nota che spiega l'estensione e le esclusioni.

## Verifiche

| Cosa | Dove |
|---|---|
| `config.toml` identico al §5; valori approvati e nuovi colori dalla palette | `tests/test_app_struttura.py` |
| ogni chiave del tema esiste nella versione installata (provato con 1.60 e 1.67) | `test_ogni_chiave_del_tema_esiste_nella_versione_installata` |
| nessun file CSS | `test_lo_stile_e_solo_nel_config_toml_senza_file_css` |
| versioni bloccate e rispettate | `test_le_versioni_dellinterfaccia_sono_bloccate_e_quella_installata_rientra` |
| l'app senza stile | tutta la suite AppTest, che gira senza tema |

**Nel browser** (stack MySQL isolato, ETL, seed): sidebar color miele, titoli in grassetto, card
arrotondate con bordo; nessun avviso sul tema nel log di Streamlit. A 1366×768 nessuna metrica
troncata sulla Dashboard; a 1024 px, dove in M6-T9 si troncavano quasi tutti i valori, ora si tronca
solo la data dell'ultima ispezione, mentre restano troncate alcune etichette lunghe (che hanno il loro
aiuto con il testo intero).

## File coinvolti

| File | Azione |
|---|---|
| `.streamlit/config.toml` | esteso con le chiavi native del tema |
| `docs/markdown/M6-interfaccia/ui_spec.md` | §5 aggiornato, con la nota su M6-T10 |
| `requirements.txt`, `pyproject.toml` | Streamlit e Plotly bloccati |
| `tests/test_app_struttura.py` | test del tema, delle chiavi e delle versioni |

## Definition of Done (ricavata dalla descrizione della issue)

| Voce | Esito |
|---|---|
| identità visiva del mockup | fatto per gli elementi compatibili con la specifica (tabella sopra) |
| tutto lo stile in un unico punto | fatto: `.streamlit/config.toml`, nessun CSS |
| versioni bloccate | fatto, con il test |
| l'app resta pienamente usabile senza stile | fatto: il tema è solo aspetto; la suite AppTest gira senza |
| nessun rischio per la stabilità | fatto: nessun selettore interno, chiavi verificate sulle due versioni |
