# Attivare l’aggiornamento automatico JackTV

Il pacchetto è pronto e testato, ma NON è ancora installato su GitHub.

1. Estrai `JackTV_aggiornamento_automatico.zip` sul PC.
2. Apri https://github.com/Jackmick99/JackTV e seleziona il ramo `main`.
3. Seleziona **Add file → Upload files**.
4. Trascina TUTTO il contenuto estratto: le cartelle `.github`, `scripts`, `epg`,
   `tests` e i file `JackTV_EPG.xml.gz` e `INSTALLAZIONE_EPG.md`.
   Non caricare lo ZIP e non trascinare la cartella esterna che lo contiene:
   `.github/workflows/update-epg.yml` deve trovarsi alla radice del repository.
5. Conferma le modifiche nel ramo `main`. Se usi un altro ramo, uniscilo a `main`.
6. Vai su **Actions → Update JackTV EPG**: il caricamento avvia il primo aggiornamento.
   Attendi il segno verde. Se non parte, usa **Run workflow** sul ramo `main`.

Da quel momento GitHub programmerà un aggiornamento ogni 6 ore, al minuto 17
(00:17, 06:17, 12:17, 18:17 UTC). L’esecuzione può subire ritardi.
Il link della guida e della playlist nel player rimangono gli stessi.
La playlist e la procedura esistente TRM H24 non sono incluse nel pacchetto e
non vengono sostituite. La cartella `.github` aggiunge un secondo workflow.

## Controllo del funzionamento

- In Actions cerca l’ultima esecuzione di **Update JackTV EPG** con segno verde.
- `epg/status.json` riporta data del controllo, copertura e scadenze per canale.
- In caso di errore, il rapporto è negli artifact `jacktv-epg-report`.
- Se le fonti peggiorano troppo, il workflow fallisce e conserva la guida precedente.
  Una guida precedente può comunque scadere: occorre risolvere l’errore segnalato.
- Se GitHub blocca la pubblicazione per i permessi o regole del ramo, verifica
  l’errore nella fase **Publish validated guide**; nessun token personale è richiesto.

## Verifica eseguita prima della consegna

Python 3.12: 8 test superati, inclusa la protezione della guida durante un guasto
completo delle fonti. Prova reale del 26 settembre 2026: 228 canali, 35.314 programmi;
226 guide nuove e 2 recuperate dalla guida precedente, nessuna mancante.
Le due recuperate sono Canale 8 e Canale 21, valide fino alla notte del 26/27
settembre: il recupero non prolunga gli orari e non inventa il palinsesto.
L’esecuzione effettiva su GitHub Actions deve ancora essere verificata dopo il caricamento.

Dettagli su fonti, nuovi canali e uso locale: `epg/README.md`.
Documentazione caricamento: https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository
