-- ============================================================================
-- BeeWatch AI - privilegi dell'utente applicativo
-- ============================================================================
--
-- Chi fa cosa:
--
--     root           solo inizializzazione e amministrazione di MySQL. Esegue
--                    questi script e nessun altro li esegue. L'applicazione non ne
--                    conosce la password e non puo' collegarsi come root.
--     utente app     solo leggere e scrivere i DATI: SELECT, INSERT, UPDATE, DELETE.
--
-- Perche' basta questo. Il livello dati (M3) fa CRUD con query parametrizzate,
-- l'ETL carica con un upsert (INSERT ... ON DUPLICATE KEY UPDATE) dentro una
-- transazione, e M4-M6 leggono e salvano previsioni, report e messaggi: tutte
-- operazioni su righe. Le tabelle le crea `schema.sql`, che esegue root. Nello
-- schema non ci sono viste, trigger, procedure ne' tabelle temporanee, che
-- richiederebbero privilegi in piu'. Quindi niente CREATE, DROP, ALTER, INDEX,
-- GRANT: un bug (o un'iniezione SQL) nell'applicazione non puo' cancellare o
-- modificare lo schema, ne' creare utenti.
--
-- Se un domani servira' un privilegio in piu', lo si aggiunge qui con il motivo,
-- non lo si concede "per sicurezza".
--
-- Come funziona. L'immagine di MySQL crea da sola l'utente `MYSQL_USER`, ma gli da'
-- ALL PRIVILEGES sul database. Questo script gli toglie tutto e gli rida' soltanto
-- il necessario. Non conosce il nome dell'utente (gli script SQL non leggono le
-- variabili d'ambiente): lo ricava da chi ha privilegi sul database corrente.
-- Gira come tutti gli altri script di `docker-entrypoint-initdb.d`, con il database
-- applicativo gia' selezionato, e solo al primo avvio con il volume vuoto.
--
-- Su un volume gia' esistente non viene rieseguito. Per applicarlo senza perdere i
-- dati (e' ripetibile senza danni):
--
--   docker compose exec -T mysql sh -c \
--     'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --database="$MYSQL_DATABASE"' < sql/privilegi.sql

-- `Db` e' salvato con i trattini bassi preceduti da backslash (il nome e' un
-- "pattern"): lo si riusa cosi' com'e' nei comandi, per colpire la stessa riga.
-- L'utente di sistema `mysql.*` ha privilegi su altri database e non entra nel filtro.
SELECT
    CONCAT('REVOKE ALL PRIVILEGES ON `', Db, '`.* FROM `', User, '`@`', Host, '`'),
    CONCAT('GRANT SELECT, INSERT, UPDATE, DELETE ON `', Db, '`.* TO `', User, '`@`', Host, '`')
INTO @revoca, @concedi
FROM mysql.db
WHERE REPLACE(Db, '\\_', '_') = DATABASE()
  AND User NOT LIKE 'mysql.%'
LIMIT 1;

-- Se l'utente non c'e' (MYSQL_USER non impostato) i due comandi sono NULL: si
-- esegue un'istruzione vuota invece di fallire.
SET @revoca  = IFNULL(@revoca,  'DO 0');
SET @concedi = IFNULL(@concedi, 'DO 0');

PREPARE revoca  FROM @revoca;
EXECUTE revoca;
PREPARE concedi FROM @concedi;
EXECUTE concedi;
DEALLOCATE PREPARE revoca;
DEALLOCATE PREPARE concedi;
