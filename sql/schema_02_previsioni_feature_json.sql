-- ============================================================================
-- BeeWatch AI - estensione dello schema (M4-T8): le feature di ogni previsione
-- ============================================================================
--
-- Aggiunge `previsioni.feature_json`: i valori esatti delle feature con cui il modello
-- ha fatto quella previsione (stato, anno, resa dell'anno prima, media dei tre anni
-- prima, colonie dell'anno prima).
--
-- Perche' serve. `versione_modello` dice QUALE modello ha previsto e
-- `modelli.variabili_usate` dice quali feature usa, ma non i loro valori: quelli
-- vengono da `produzione_usda`, che l'ETL puo' ricaricare con dati diversi. Senza i
-- valori una previsione vecchia non si puo' piu' rifare ne' spiegare. La DoD di M4-T8
-- chiede «persistita con modello_versione e feature_json».
--
-- Perche' un file a parte e non una modifica a `schema.sql`. `schema.sql` gira solo al
-- primo avvio con il volume vuoto: chi ha gia' un database non riceverebbe la colonna, e
-- le previsioni fallirebbero. Qui la modifica e' ripetibile e si applica anche a un
-- database esistente (vedi sotto). Il nome ordina questo file DOPO `schema.sql` e PRIMA
-- di `seed.sql`, come serve: la tabella `previsioni` deve esistere gia'.
--
-- Esecuzione
-- ----------
-- Automatica: il contenitore MySQL esegue tutti gli .sql di `sql/` al primo avvio, in
-- ordine alfabetico (privilegi, schema, questo file, seed). Lo stesso fa
-- `00_test_db.sh` per il database dei test.
--
-- Su un volume gia' esistente non viene rieseguito: serve root, perche' l'utente
-- applicativo non ha ALTER (e non deve averlo). E' ripetibile senza danni, non tocca i
-- dati e lascia NULL le previsioni gia' salvate:
--
--   docker compose exec -T mysql sh -c \
--     'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --database="$MYSQL_DATABASE"' \
--     < sql/schema_02_previsioni_feature_json.sql
--
-- Se il programma trova il database senza questa colonna lo dice con un messaggio che
-- rimanda a questo comando.

-- MySQL non ha `ADD COLUMN IF NOT EXISTS`: si controlla `information_schema` e si
-- esegue l'ALTER solo se la colonna manca.
SET @esiste = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'previsioni'
      AND column_name = 'feature_json'
);

SET @istruzione = IF(
    @esiste = 0,
    'ALTER TABLE previsioni ADD COLUMN feature_json JSON NULL COMMENT ''Valori delle feature usate (M4-T8); NULL per le previsioni anteriori'' AFTER limite_superiore_kg',
    'DO 0'
);

PREPARE aggiungi FROM @istruzione;
EXECUTE aggiungi;
DEALLOCATE PREPARE aggiungi;
