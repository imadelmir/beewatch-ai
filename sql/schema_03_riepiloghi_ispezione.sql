-- ============================================================================
-- BeeWatch AI - estensione dello schema (M5-T5): i riepiloghi AI delle ispezioni
-- ============================================================================
--
-- Aggiunge la tabella `riepiloghi_ispezione`: il riepilogo strutturato che l'assistente AI
-- produce leggendo le note di un'ispezione (decisione DA-03, opzione A), con tutto ciò che
-- serve a ricondurlo a chi l'ha prodotto: provider, modello, versione del prompt, durata, token.
--
-- Perche' una tabella nuova e non `messaggi`. `messaggi` appartiene a una conversazione e ha
-- un testo libero; un riepilogo appartiene a UN'ISPEZIONE e ha una struttura (stato di salute,
-- criticita', azioni, confidenza) che l'interfaccia deve poter filtrare e mostrare senza
-- rileggere il testo. `stato_salute` e `confidenza` stanno in colonne proprie per questo:
-- il resto sta nel JSON, che e' la copia fedele di cio' che il modello ha prodotto e il
-- parser ha accettato (M5-T3).
--
-- Una ispezione puo' avere piu' riepiloghi: rigenerarlo con un modello o un prompt diversi
-- non cancella il vecchio, e i due si possono confrontare. Cancellando l'ispezione (o
-- l'utente) spariscono anche i suoi riepiloghi: contengono il contenuto delle note.
--
-- Non si salvano le risposte non valide (il «non disponibile» del fallback): non sono un
-- riepilogo, e l'errore e' nel log.
--
-- Perche' un file a parte e non una modifica a `schema.sql`: `schema.sql` gira solo al primo
-- avvio con il volume vuoto. Qui `CREATE TABLE IF NOT EXISTS` rende la modifica ripetibile e
-- applicabile anche a un database esistente. Il nome ordina questo file DOPO `schema.sql`
-- (servono `ispezioni` e `utenti`) e prima di `seed.sql`.
--
-- Esecuzione
-- ----------
-- Automatica: il contenitore MySQL esegue tutti gli .sql di `sql/` al primo avvio, in ordine
-- alfabetico. Lo stesso fa `00_test_db.sh` per il database dei test.
--
-- Su un volume gia' esistente non viene rieseguito: serve root (l'utente applicativo non ha
-- CREATE, e non deve averlo). E' ripetibile senza danni e non tocca i dati:
--
--   docker compose exec -T mysql sh -c \
--     'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --database="$MYSQL_DATABASE"' \
--     < sql/schema_03_riepiloghi_ispezione.sql
--
-- L'utente applicativo ha SELECT, INSERT, UPDATE e DELETE su tutto il database, quindi vale
-- subito anche per la tabella nuova. Se il programma trova il database senza questa tabella lo
-- dice con un messaggio che rimanda a questo comando.

CREATE TABLE IF NOT EXISTS riepiloghi_ispezione (
    id              INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    ispezione_id    INT UNSIGNED  NOT NULL,
    utente_id       INT UNSIGNED  NOT NULL,
    stato_salute    ENUM('buono', 'attenzione', 'critico', 'non_determinabile') NOT NULL,
    confidenza      ENUM('alta', 'media', 'bassa') NOT NULL,
    riepilogo_json  JSON          NOT NULL COMMENT 'Il riepilogo validato (schema di M5-T3)',
    provider        VARCHAR(20)   NOT NULL COMMENT 'ollama oppure openrouter',
    modello         VARCHAR(60)   NOT NULL,
    versione_prompt VARCHAR(20)   NOT NULL COMMENT 'Quale insieme di prompt ha prodotto il riepilogo',
    durata_ms       INT UNSIGNED  NOT NULL COMMENT 'Somma delle chiamate al provider, tentativo correttivo compreso',
    token_prompt    INT UNSIGNED  NULL COMMENT 'NULL se il provider non li dichiara',
    token_risposta  INT UNSIGNED  NULL,
    tentativi       TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '2 = e'' servito il tentativo correttivo',
    creato_il       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_riepiloghi_ispezione_data (ispezione_id, creato_il DESC),
    KEY idx_riepiloghi_utente_data (utente_id, creato_il DESC),

    CONSTRAINT fk_riepiloghi_ispezioni
        FOREIGN KEY (ispezione_id) REFERENCES ispezioni (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,

    CONSTRAINT fk_riepiloghi_utenti
        FOREIGN KEY (utente_id) REFERENCES utenti (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,

    CONSTRAINT chk_riepiloghi_tentativi CHECK (tentativi BETWEEN 1 AND 2)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Riepiloghi AI delle ispezioni, con modello e prompt che li hanno prodotti (DA-03)';
