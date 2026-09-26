# Aggiornamento automatico JackTV EPG

Il workflow **Update JackTV EPG** aggiorna `JackTV_EPG.xml.gz` ogni 6 ore
(00:17, 06:17, 12:17 e 18:17 UTC). GitHub può ritardare le esecuzioni programmate.
Il file deve essere nel ramo `main`; il workflow può partire anche da
**Actions → Update JackTV EPG → Run workflow**.

Il link nel player rimane:

`https://raw.githubusercontent.com/Jackmick99/JackTV/refs/heads/main/JackTV_EPG.xml.gz`

## Comportamento

- Scarica solo le fonti dei canali presenti nella playlist e già verificati in
  `epg/channels.json`. Non modifica la playlist né gli stream.
- Usa i file nazionali EPGShare e i dati italiani Zappr, senza ALL_SOURCES1.
- Non abbina nuovi canali per somiglianza. ID nuovi sono segnalati nel rapporto;
  gli ID vuoti restano privi di associazione automatica.
- Tiene circa un giorno di storico e fino a 14 giorni futuri, secondo la fonte.
- Scarta intervalli invalidi, duplicati e sovrapposizioni; conserva i fusi orari.
- Se un canale non ha dati nuovi validi, recupera i suoi programmi precedenti
  solo finché contengono eventi attuali o futuri. Non inventa programmi.
- Pubblica solo se almeno il 90% dei canali verificati ha dati nuovi e almeno
  il 95% ha dati nuovi o precedenti ancora validi. In caso contrario fallisce
  senza sostituire la guida online. Anche la vecchia guida può infine scadere:
  in tal caso occorre correggere la fonte, non riutilizzarla indefinitamente.

`epg/status.json` documenta l'ultima generazione pubblicata, la scadenza per
canale, i recuperi e le eventuali guide mancanti. Il rapporto dell'ultimo
tentativo è anche scaricabile dagli artifact dell'esecuzione su GitHub Actions.
Gli errori sono visibili in Actions; valgono le notifiche GitHub del tuo account.

Il workflow preesistente TRM H24 resta indipendente. Il nuovo workflow salva
solamente EPG e rapporto e recupera eventuali aggiornamenti concorrenti del ramo.
Non richiede token personali o segreti aggiuntivi: usa il GITHUB_TOKEN del job
con permesso `contents: write`. Eventuali regole del repository possono impedirlo.

## Nuovi canali

Aggiungi la voce alla playlist; per la guida, verifica l'edizione corretta e
aggiungi la corrispondenza in `channels.json`. Il solo nome non garantisce che
due feed condividano il palinsesto (regioni, lingue, FAST, East/West).
La cancellazione di un canale dalla playlist lo esclude dalla guida successiva.

## Uso locale

Con Python 3.12 o successivo, dalla cartella del repository:

```text
python scripts/update_epg.py
```

Non servono librerie aggiuntive. Per aggiornare una copia locale da usare nel
player occorre scaricare nuovamente l'EPG oppure eseguire questo comando.
Per sospendere gli aggiornamenti online, disabilita il workflow in GitHub Actions.
