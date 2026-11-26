# SchoolHub

[Scarica la versione Windows](https://github.com/MatteoPorcu08/school-hub/releases) · [Controlla le compilazioni](https://github.com/MatteoPorcu08/school-hub/actions)

Progetto indipendente per SchoolHub 2.6.7, con interfaccia originale Tkinter e percorso critico di scansione file in Rust. Non è ancora una riscrittura completa; è disponibile una pipeline per l'eseguibile Windows autonomo.

## Cartella SchoolHub già presente sul disco

All'avvio della versione 0.2.3 viene proposta la cartella salvata dall'app originale (se esiste) o quella del profilo precedente. Si può scegliere un'altra cartella già esistente in qualsiasi disco. Il percorso predefinito dell'app originale è `%LOCALAPPDATA%\\SchoolHub\\Workspaces\\Scuola`. Non vengono spostati o rinominati documenti o Vault durante il collegamento. Se è presente un Vault valido collegato a quel percorso, resta disponibile con la password originale; altrimenti l'app può sincronizzare direttamente la cartella normale, senza cifratura obbligatoria. I file locali sostituiti o rimossi vengono conservati in `%LOCALAPPDATA%\\SchoolHubRust\\Backups\\FolderRecovery` (non cifrati). Il repository GitHub e il branch precedenti sono recuperati soltanto quando il percorso coincide. La prima sync confronta entrambe le versioni senza assumere una vecchia baseline; i conflitti richiedono scelta esplicita. Lo stato successivo è separato per percorso, repository e branch. Per sicurezza la prima sincronizzazione è manuale; si può poi attivare l'automatica nelle impostazioni. Non utilizzare il repository del codice per i documenti.

## Cosa cambia

- Scansione SHA-256 parallela e limitata a 1–8 thread, senza affidarsi alla sola data di modifica. Output compatibile con le mappe di hash di SchoolHub.
- Cache in RAM del manifesto remoto: ogni controllo interroga il commit corrente; se il commit è invariato evita clone, checkout, download LFS e nuova scansione remota.
- Clone diretto del branch scelto; recupero originale per branch assenti/repository vuoti.
- Percorso rapido per sincronizzazioni senza modifiche, dopo verifica del commit remoto e del contenuto locale.
- Modalità facoltativa di cache Git di sessione: `fetch` incrementale dei soli oggetti mancanti, clone locale senza rete e riuso degli oggetti LFS. Disattivata per impostazione predefinita perché il cache contiene documenti in chiaro.
- Sincronizzazione con modifiche, gestione dei conflitti, cifratura AES-GCM del Vault, autenticazione e Git LFS rimangono nel codice originale. Non si introduce force-push; la cache dei documenti è solo opzionale e temporanea.

La velocità effettiva non è ancora misurata: dipende da rete, SSD/HDD, dimensioni e quantità di file. Senza cache su disco un cambio di commit richiede ancora il clone remoto; le modifiche a file reali continuano a usare la pipeline originale. Non sono ancora disponibili una riscrittura Rust integrale o test end-to-end con l'account dell'utente.

## Eseguibile Windows e aggiornamenti automatici

Scarica `SchoolHub-Setup.exe` (installer consigliato) oppure `SchoolHub.exe` (portatile) dalla [release più recente](https://github.com/MatteoPorcu08/school-hub/releases/latest). L'installer crea il collegamento nel menu Start e può creare un collegamento desktop. Non richiede privilegi amministrativi. Entrambi gli eseguibili usano il logo originale SchoolHub, recuperato dall'archivio sorgente verificato. Non occorre installare Python, Rust o Cargo; la versione Windows integra MinGit, Git Credential Manager e Git LFS: non occorre installare o configurare Git. L'accesso avviene nel browser con l'account GitHub e le credenziali sono gestite da GCM. Git rimane il protocollo interno per conservare compatibilità, conflitti e LFS. Al primo avvio, dopo conferma del diritto di utilizzo, l'eseguibile scarica i sorgenti dell'interfaccia originale nel profilo locale e verifica i blob Git fissati. Serve Internet per il primo avvio; in seguito l'interfaccia può avviarsi offline.

L'app controlla automaticamente gli aggiornamenti all'avvio e ogni sei ore, scarica solo una versione stabile superiore dal repository MatteoPorcu08/school-hub, verifica dimensione e SHA-256, e attiva la nuova versione **al prossimo avvio**. Il file scaricato originale continua a funzionare da punto di ingresso. Non riavvia l'app durante una sincronizzazione. Gli aggiornamenti non sovrascrivono i documenti o il Vault. Le release non sono firmate con Authenticode: la fiducia dipende dal repository GitHub e da HTTPS, non da una firma indipendente. Windows SmartScreen potrebbe mostrare un avviso.

Per pubblicare un aggiornamento, incrementare `VERSION` (es. 0.2.1) e fare push su main. GitHub Actions esegue test, compila l'EXE, verifica il pacchetto e pubblica la release con checksum solo in caso di successo. Non riutilizzare un tag già pubblicato.

## Risoluzione problemi di installazione e avvio

- Dalla versione 0.2.1, usare `SchoolHub-Setup.exe` per l'installazione guidata. L'eseguibile `SchoolHub.exe` è la variante portatile, non un installer.
- Chiudere le istanze precedenti dell'app prima dell'installazione. Non eliminare i dati del profilo locale per reinstallare il programma.
- Se l'interfaccia non si avvia, controllare `%LOCALAPPDATA%\\SchoolHubRust\\startup-error.log` e verificare la connessione a GitHub al primo avvio. In caso di problemi di sincronizzazione controllare anche `schoolhub.log` nella stessa cartella.
- La release include il motore Git, GCM e LFS privati all'applicazione. In caso di errore nel login, aprire Accedi a GitHub e completare l'autorizzazione nel browser; il repository dati deve essere separato da quello del codice.
- I file SHA-256 allegati alle release consentono di verificare i download. Il software non è firmato digitalmente: non disabilitare le protezioni di Windows.

## Avvio in sviluppo (Windows)

Prerequisiti: Python 3 con Tkinter, Git per Windows con Git LFS e Git Credential Manager, Rust/Cargo (toolchain MSVC con Build Tools). Configurare Git LFS con `git lfs install` se necessario.

Il progetto originale è pubblico ma non dichiara una licenza: non ne redistribuiamo i sorgenti. L'interfaccia originale viene scaricata **solo localmente** dal commit fissato e verificata mediante ID Git dei blob. Procedere solo con il diritto di utilizzo del software originale.

```powershell
git clone https://github.com/MatteoPorcu08/school-hub.git
cd school-hub
py -m venv .venv
.\.venv\Scripts\python.exe setup.py --authorized
.\.venv\Scripts\python.exe launch.py
```

Per limitare il parallelismo su HDD: `$env:SCHOOLHUB_SCAN_WORKERS="1"`.

L'anteprima usa un profilo locale separato `%LOCALAPPDATA%\SchoolHubRust`. Nella versione Windows il percorso dei documenti viene scelto esplicitamente come descritto sopra. L'avvio automatico Windows originale non viene modificato. Gli aggiornamenti originali sono disabilitati nell'anteprima. Usare inizialmente una copia di prova del workspace; non collegare il Vault originale fino alla verifica di compatibilità.

**Importante:** questo repository pubblico contiene codice, non deve essere selezionato come repository di sincronizzazione dei documenti scolastici. Il Vault originale protegge i file locali, ma il flusso Git originale può caricare file in chiaro; usare un repository dati privato separato.

## Modalità massima velocità (facoltativa)

Solo se disponi di una cartella già esistente su un volume cifrato (es. BitLocker), puoi abilitare la cache degli oggetti Git e LFS prima dell'avvio:

```powershell
$env:SCHOOLHUB_GIT_CACHE_DIR="D:\\CacheCifrata"
.\\.venv\\Scripts\\python.exe launch.py
```

La cache viene creata con un nome casuale per sessione e rimossa alla chiusura normale. Un crash può lasciare file in chiaro sul volume; l'utente deve rimuoverli manualmente. Non selezionare una cartella condivisa, cloud o non cifrata. Non utilizzare questa modalità se non puoi proteggere il volume. L'app non può verificare autonomamente che sia cifrato. Se un fetch fallisce, il cache non viene usato come copia remota valida.

## Test

```
cargo test
cargo build --release
python -m unittest discover -s tests -v
```

## Componenti inclusi (Windows)

Le versioni sono fissate e gli archivi verificati tramite SHA-256 durante la compilazione:
- [MinGit 2.56.1](https://github.com/git-for-windows/git/releases/tag/v2.56.1.windows.1) (Git for Windows, componenti GPL e altre licenze; sorgenti e avvisi nel progetto ufficiale).
- [Git Credential Manager 3.0.2](https://github.com/git-ecosystem/git-credential-manager/releases/tag/v3.0.2) (MIT).
- [Git LFS 3.8.1](https://github.com/git-lfs/git-lfs/releases/tag/v3.8.1) (MIT).

L'interfaccia originale viene ancora scaricata localmente previa autorizzazione. Il logo originale è utilizzato su richiesta del proprietario di questo repository; i diritti appartengono all'autore originale, ed è necessario il suo consenso per redistribuirlo se richiesto. Il pacchetto è più grande perché contiene i componenti di sincronizzazione; il formato portatile onefile estrae i componenti all'avvio.

## Origine

SchoolHub di MeloniMirko, versione 2.6.7, branch schoolhub-build, commit 513285580fbbade3568c8fd4fb3692ab891e4460. Il codice di questo repository è un adattatore e motore di scansione indipendente. La UI, le funzionalità Vault e l'algoritmo originale di sincronizzazione restano nel progetto di origine.
