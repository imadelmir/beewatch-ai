-- =========================================================================== --
-- BeeWatch AI - schema del database
-- =========================================================================== --
--
-- Task M2-T5. Traduzione in DDL dello schema progettato in M2-T4:
--   docs/markdown/M2-dati/M2-T4_schema.md   il ragionamento
--   docs/diagrams/er_diagram.dbml           il diagramma
--
-- Esecuzione
-- ----------
-- Automatica: il contenitore MySQL esegue questo file al primo avvio, perche'
-- `docker-compose.yml` monta la cartella `sql/` in /docker-entrypoint-initdb.d.
--
--     docker compose up -d
--
-- Manuale, su un database gia' avviato:
--
--     docker compose exec -T mysql mysql -u root -p < sql/schema.sql
--
-- Lo script e' idempotente: ogni oggetto e' creato con IF NOT EXISTS, quindi
-- rilanciarlo non produce errori e non tocca i dati esistenti. Per ripartire da
-- zero: `docker compose down -v && docker compose up -d`.
--
-- Requisiti
-- ---------
-- MySQL 8.0.16 o superiore. Prima di quella versione i vincoli CHECK venivano
-- accettati e ignorati in silenzio: lo schema sembrerebbe corretto e non lo
-- sarebbe. Il contenitore usa 8.4.
--
-- Convenzioni
-- -----------
--   tabelle          plurale, minuscolo            alveari, produzione_usda
--   chiave esterna   <tabella_singolare>_id        alveare_id, tipo_miele_id
--   date di sistema  creato_il, aggiornato_il      sempre al maschile
--   indici           idx_<tabella>_<colonne>
--   unicita'         uq_<tabella>_<colonne>
--   vincoli CHECK    chk_<tabella>_<regola>
--   chiavi esterne   fk_<tabella>_<tabella_riferita>
--
-- Gli identificatori e i contatori sono UNSIGNED: un id negativo non esiste, e
-- una chiave esterna deve avere esattamente lo stesso tipo della colonna a cui
-- punta, UNSIGNED compreso.
--
-- InnoDB crea da solo un indice su ogni colonna di chiave esterna: qui sono
-- dichiarati solo quelli che non nascono da soli, cioe' i compositi.
-- =========================================================================== --

-- Nota: qui non c'e' nessun CREATE DATABASE, ed e' voluto.
--
-- Il nome del database arriva da DB_NAME nel `.env`. Scriverlo a mano in questo
-- file significherebbe averlo in due posti: se qualcuno cambiasse DB_NAME, le
-- tabelle nascerebbero in un database e l'applicazione ne cercherebbe un altro.
--
-- Il database lo crea il contenitore, che legge DB_NAME e seleziona quel
-- database prima di eseguire questo script. Per l'esecuzione manuale si indica
-- con l'opzione -D:
--
--     mysql -u root -p -D beewatch < sql/schema.sql


-- --------------------------------------------------------------------------- --
-- Tabelle di riferimento
-- --------------------------------------------------------------------------- --
-- Valori fissi con un'etichetta da mostrare all'utente. Sono tabelle e non ENUM
-- perche' l'etichetta e il colore servono all'interfaccia: in un ENUM vivrebbero
-- nel codice, qui vivono nei dati.

CREATE TABLE IF NOT EXISTS stati_alveare (
    id        TINYINT UNSIGNED NOT NULL,
    codice    VARCHAR(20)      NOT NULL COMMENT 'Identificatore stabile usato dal codice',
    etichetta VARCHAR(60)      NOT NULL COMMENT 'Testo mostrato all''utente',
    colore    CHAR(7)          NULL     COMMENT 'Esadecimale, es. #3FB463',
    ordine    TINYINT UNSIGNED NOT NULL COMMENT 'Ordine di visualizzazione',

    PRIMARY KEY (id),
    UNIQUE KEY uq_stati_alveare_codice (codice)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Stati possibili di un alveare: in salute, debole, sciamato, morto...';


CREATE TABLE IF NOT EXISTS livelli_rischio (
    id        TINYINT UNSIGNED NOT NULL,
    codice    VARCHAR(20)      NOT NULL,
    etichetta VARCHAR(60)      NOT NULL,
    gravita   TINYINT UNSIGNED NOT NULL COMMENT '1 = nessuno ... 4 = alto',

    PRIMARY KEY (id),
    UNIQUE KEY uq_livelli_rischio_codice (codice),
    CONSTRAINT chk_livelli_rischio_gravita CHECK (gravita BETWEEN 1 AND 4)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Livello di rischio rilevato durante un''ispezione';


CREATE TABLE IF NOT EXISTS tipi_miele (
    id        TINYINT UNSIGNED NOT NULL,
    codice    VARCHAR(20)      NOT NULL,
    etichetta VARCHAR(60)      NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_tipi_miele_codice (codice)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Tipi di miele: acacia, millefiori, castagno, melata...';


-- --------------------------------------------------------------------------- --
-- Livello operativo
-- --------------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS utenti (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    email         VARCHAR(255) NOT NULL,
    nome_completo VARCHAR(120) NOT NULL,
    hash_password CHAR(60)     NOT NULL COMMENT 'bcrypt: mai la password in chiaro',
    tema          VARCHAR(10)  NOT NULL DEFAULT 'auto',
    creato_il     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aggiornato_il DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP,
    attivo        BOOLEAN      NOT NULL DEFAULT TRUE
                                        COMMENT 'FALSE disattiva l''accesso ma conserva i dati',

    PRIMARY KEY (id),
    UNIQUE KEY uq_utenti_email (email),
    CONSTRAINT chk_utenti_tema CHECK (tema IN ('auto', 'chiaro', 'scuro'))
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Apicoltori registrati. Cancellare una riga cancella tutti i suoi dati (GDPR art. 17)';


CREATE TABLE IF NOT EXISTS apiari (
    id            INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    utente_id     INT UNSIGNED  NOT NULL,
    nome          VARCHAR(120)  NOT NULL,
    localita      VARCHAR(160)  NULL,
    latitudine    DECIMAL(9, 6) NULL COMMENT 'Dato personale indiretto: mai inviato a un LLM esterno',
    longitudine   DECIMAL(9, 6) NULL,
    note          TEXT          NULL,
    creato_il     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aggiornato_il DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                         ON UPDATE CURRENT_TIMESTAMP,
    attivo        BOOLEAN       NOT NULL DEFAULT TRUE,

    PRIMARY KEY (id),
    UNIQUE KEY uq_apiari_utente_nome (utente_id, nome),
    KEY idx_apiari_utente_attivo (utente_id, attivo),

    CONSTRAINT fk_apiari_utenti
        FOREIGN KEY (utente_id) REFERENCES utenti (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,

    CONSTRAINT chk_apiari_latitudine  CHECK (latitudine  BETWEEN -90  AND 90),
    CONSTRAINT chk_apiari_longitudine CHECK (longitudine BETWEEN -180 AND 180)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Un apiario e'' un luogo fisico dove stanno gli alveari';


CREATE TABLE IF NOT EXISTS alveari (
    id                 INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    apiario_id         INT UNSIGNED      NOT NULL,
    stato_alveare_id   TINYINT UNSIGNED  NOT NULL,
    codice             VARCHAR(20)       NOT NULL COMMENT 'Unico dentro l''apiario, non nel database',
    data_installazione DATE              NULL,
    anno_regina        SMALLINT UNSIGNED NULL,
    note               TEXT              NULL,
    creato_il          DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aggiornato_il      DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                  ON UPDATE CURRENT_TIMESTAMP,
    attivo             BOOLEAN           NOT NULL DEFAULT TRUE,

    PRIMARY KEY (id),
    UNIQUE KEY uq_alveari_apiario_codice (apiario_id, codice),
    KEY idx_alveari_stato (stato_alveare_id),

    CONSTRAINT fk_alveari_apiari
        FOREIGN KEY (apiario_id) REFERENCES apiari (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,

    CONSTRAINT fk_alveari_stati_alveare
        FOREIGN KEY (stato_alveare_id) REFERENCES stati_alveare (id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,

    CONSTRAINT chk_alveari_anno_regina CHECK (anno_regina BETWEEN 2000 AND 2100)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Le singole arnie. Si disattivano, non si cancellano: lo storico resta valido';


CREATE TABLE IF NOT EXISTS ispezioni (
    id                 INT UNSIGNED     NOT NULL AUTO_INCREMENT,
    alveare_id         INT UNSIGNED     NOT NULL,
    livello_rischio_id TINYINT UNSIGNED NOT NULL,
    data_ispezione     DATE             NOT NULL COMMENT 'Quando e'' stata fatta, non quando e'' stata registrata',
    peso_kg            DECIMAL(6, 2)    NULL,
    telaini_covata     TINYINT UNSIGNED NULL,
    telaini_scorte     TINYINT UNSIGNED NULL,
    regina_vista       BOOLEAN          NOT NULL DEFAULT FALSE,
    sciamatura         BOOLEAN          NOT NULL DEFAULT FALSE,
    note               TEXT             NULL COMMENT 'Testo libero: e'' l''input dell''assistente AI (M5)',
    creato_il          DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aggiornato_il      DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                 ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_ispezioni_alveare_data (alveare_id, data_ispezione DESC),
    KEY idx_ispezioni_rischio (livello_rischio_id),

    CONSTRAINT fk_ispezioni_alveari
        FOREIGN KEY (alveare_id) REFERENCES alveari (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,

    CONSTRAINT fk_ispezioni_livelli_rischio
        FOREIGN KEY (livello_rischio_id) REFERENCES livelli_rischio (id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,

    CONSTRAINT chk_ispezioni_peso    CHECK (peso_kg >= 0),
    CONSTRAINT chk_ispezioni_covata  CHECK (telaini_covata <= 30),
    CONSTRAINT chk_ispezioni_scorte  CHECK (telaini_scorte <= 30)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Visite all''alveare: cosa si e'' visto e quando';


CREATE TABLE IF NOT EXISTS raccolti (
    id            INT UNSIGNED     NOT NULL AUTO_INCREMENT,
    apiario_id    INT UNSIGNED     NOT NULL,
    alveare_id    INT UNSIGNED     NULL COMMENT 'Facoltativo: solo se si tengono separati i melari',
    tipo_miele_id TINYINT UNSIGNED NOT NULL,
    data_raccolto DATE             NOT NULL,
    quantita_kg   DECIMAL(6, 2)    NOT NULL,
    note          TEXT             NULL,
    creato_il     DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aggiornato_il DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP
                                             ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_raccolti_apiario_data (apiario_id, data_raccolto DESC),
    KEY idx_raccolti_alveare (alveare_id),
    KEY idx_raccolti_tipo (tipo_miele_id),

    CONSTRAINT fk_raccolti_apiari
        FOREIGN KEY (apiario_id) REFERENCES apiari (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,

    CONSTRAINT fk_raccolti_alveari
        FOREIGN KEY (alveare_id) REFERENCES alveari (id)
        ON DELETE SET NULL ON UPDATE RESTRICT,

    CONSTRAINT fk_raccolti_tipi_miele
        FOREIGN KEY (tipo_miele_id) REFERENCES tipi_miele (id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,

    CONSTRAINT chk_raccolti_quantita CHECK (quantita_kg > 0)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Smielature. Il raccolto e'' dell''apiario; l''alveare e'' un dettaglio facoltativo. Che l''alveare appartenga a quell''apiario e'' verificato dall''applicazione (M3): un CHECK non puo'' leggere altre tabelle';


-- --------------------------------------------------------------------------- --
-- Riferimento USDA
-- --------------------------------------------------------------------------- --
-- Dati storici di sola lettura, ricaricati per intero dall'ETL (M3-T4).

CREATE TABLE IF NOT EXISTS stati_usa (
    codice CHAR(2)     NOT NULL,
    nome   VARCHAR(60) NOT NULL,

    PRIMARY KEY (codice)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'I 44 stati presenti nel dataset USDA';


CREATE TABLE IF NOT EXISTS produzione_usda (
    id                    INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    codice_stato          CHAR(2)           NOT NULL,
    anno                  SMALLINT UNSIGNED NOT NULL,
    numero_colonie        INT UNSIGNED      NOT NULL,
    resa_per_colonia_kg   DECIMAL(8, 4)     NOT NULL COMMENT 'Target del modello (M2-T3)',
    produzione_totale_kg  DECIMAL(14, 4)    NOT NULL COMMENT 'DERIVATA: colonie x resa. Mai fra i predittori',
    scorte_kg             DECIMAL(14, 4)    NOT NULL,
    prezzo_per_kg_usd     DECIMAL(8, 4)     NOT NULL,
    valore_produzione_usd DECIMAL(14, 2)    NOT NULL COMMENT 'DERIVATA: arrotondata alla fonte',

    PRIMARY KEY (id),
    UNIQUE KEY uq_produzione_usda_stato_anno (codice_stato, anno),
    KEY idx_produzione_usda_anno (anno),

    CONSTRAINT fk_produzione_usda_stati_usa
        FOREIGN KEY (codice_stato) REFERENCES stati_usa (codice)
        ON DELETE RESTRICT ON UPDATE CASCADE,

    CONSTRAINT chk_produzione_usda_anno CHECK (anno BETWEEN 1990 AND 2100),
    CONSTRAINT chk_produzione_usda_resa CHECK (resa_per_colonia_kg > 0)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Rilevazioni USDA 1998-2012, una riga per stato e anno';


-- --------------------------------------------------------------------------- --
-- Modelli di machine learning
-- --------------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS modelli (
    versione             VARCHAR(40)      NOT NULL COMMENT 'Es. v1.0.0, compare accanto a ogni previsione',
    algoritmo            VARCHAR(60)      NOT NULL,
    addestrato_il        DATETIME         NOT NULL,
    righe_addestramento  INT UNSIGNED     NOT NULL,
    variabili_usate      JSON             NOT NULL COMMENT 'Es. ["codice_stato", "anno"]',
    importanza_variabili JSON             NULL     COMMENT 'Spiegabilita'': peso di ogni variabile',
    mae_kg               DECIMAL(6, 3)    NOT NULL COMMENT 'Criterio DA-05: deve stare sotto il MAE della persistenza',
    rmse_kg              DECIMAL(6, 3)    NOT NULL,
    r2                   DECIMAL(5, 4)    NOT NULL,
    percorso_file        VARCHAR(255)     NOT NULL COMMENT 'Il .joblib in models/',
    attivo               BOOLEAN          NOT NULL DEFAULT FALSE,
    note                 TEXT             NULL,

    -- Un solo modello per volta puo' essere attivo, e lo garantisce il database.
    -- MySQL non ha indici parziali, ma i NULL non partecipano ai vincoli di
    -- unicita': la colonna vale 1 quando attivo e' vero e NULL altrimenti,
    -- quindi possono esistere infinite righe inattive e al massimo una attiva.
    attivo_unico TINYINT UNSIGNED
        GENERATED ALWAYS AS (IF(attivo, 1, NULL)) VIRTUAL,

    PRIMARY KEY (versione),
    UNIQUE KEY uq_modelli_uno_attivo (attivo_unico),

    CONSTRAINT chk_modelli_metriche CHECK (mae_kg >= 0 AND rmse_kg >= 0)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Versioni del modello con le loro metriche: rende ogni previsione spiegabile';


-- --------------------------------------------------------------------------- --
-- Tracciabilita'
-- --------------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS previsioni (
    id                       INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    utente_id                INT UNSIGNED      NOT NULL,
    alveare_id               INT UNSIGNED      NULL COMMENT 'NULL se l''alveare e'' stato eliminato',
    versione_modello         VARCHAR(40)       NOT NULL,
    codice_stato_riferimento CHAR(2)           NOT NULL,
    anno_riferimento         SMALLINT UNSIGNED NOT NULL,
    stima_kg                 DECIMAL(6, 2)     NOT NULL,
    limite_inferiore_kg      DECIMAL(6, 2)     NOT NULL COMMENT 'Obbligatorio: una stima si mostra sempre come intervallo (M2-T3)',
    limite_superiore_kg      DECIMAL(6, 2)     NOT NULL,
    creato_il                DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_previsioni_utente_data (utente_id, creato_il DESC),
    KEY idx_previsioni_alveare (alveare_id),
    KEY idx_previsioni_modello (versione_modello),
    KEY idx_previsioni_stato (codice_stato_riferimento),

    CONSTRAINT fk_previsioni_utenti
        FOREIGN KEY (utente_id) REFERENCES utenti (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,

    CONSTRAINT fk_previsioni_alveari
        FOREIGN KEY (alveare_id) REFERENCES alveari (id)
        ON DELETE SET NULL ON UPDATE RESTRICT,

    CONSTRAINT fk_previsioni_modelli
        FOREIGN KEY (versione_modello) REFERENCES modelli (versione)
        ON DELETE RESTRICT ON UPDATE CASCADE,

    CONSTRAINT fk_previsioni_stati_usa
        FOREIGN KEY (codice_stato_riferimento) REFERENCES stati_usa (codice)
        ON DELETE RESTRICT ON UPDATE CASCADE,

    CONSTRAINT chk_previsioni_anno      CHECK (anno_riferimento BETWEEN 1990 AND 2100),
    CONSTRAINT chk_previsioni_intervallo
        CHECK (limite_inferiore_kg <= stima_kg AND stima_kg <= limite_superiore_kg)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Ogni stima prodotta, con i suoi ingressi: riproducibile a distanza di mesi';


CREATE TABLE IF NOT EXISTS conversazioni (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    utente_id     INT UNSIGNED NOT NULL,
    titolo        VARCHAR(160) NOT NULL DEFAULT 'Nuova conversazione',
    creato_il     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aggiornato_il DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP
                                        COMMENT 'Data dell''ultimo messaggio: denormalizzazione voluta',

    PRIMARY KEY (id),
    KEY idx_conversazioni_utente_aggiornato (utente_id, aggiornato_il DESC),

    CONSTRAINT fk_conversazioni_utenti
        FOREIGN KEY (utente_id) REFERENCES utenti (id)
        ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Conversazioni con l''assistente AI';


CREATE TABLE IF NOT EXISTS messaggi (
    id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
    conversazione_id INT UNSIGNED NOT NULL,
    ruolo            ENUM('utente', 'assistente', 'sistema') NOT NULL,
    contenuto        TEXT         NOT NULL,
    provider         VARCHAR(20)  NULL COMMENT 'ollama oppure openrouter',
    modello          VARCHAR(60)  NULL,
    versione_prompt  VARCHAR(20)  NULL COMMENT 'Quale prompt di sistema ha prodotto la risposta',
    durata_ms        INT UNSIGNED NULL COMMENT 'Tempo di risposta del provider',
    token_prompt     INT UNSIGNED NULL,
    token_risposta   INT UNSIGNED NULL,
    creato_il        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_messaggi_conversazione_data (conversazione_id, creato_il),

    CONSTRAINT fk_messaggi_conversazioni
        FOREIGN KEY (conversazione_id) REFERENCES conversazioni (id)
        ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Le cinque colonne tecniche sono NULL per i messaggi scritti dall''utente';


-- --------------------------------------------------------------------------- --
-- Fine
-- --------------------------------------------------------------------------- --
-- Compare nel log del contenitore: `docker compose logs mysql`.

SELECT CONCAT('BeeWatch: schema creato in `', DATABASE(), '`, ',
              COUNT(*), ' tabelle') AS esito
FROM information_schema.tables
WHERE table_schema = DATABASE();
