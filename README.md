# SchoolHub Rust — anteprima di accelerazione

Progetto indipendente per SchoolHub 2.6.7, con interfaccia originale Tkinter e percorso critico di scansione file in Rust. Non è ancora una riscrittura completa né un installer.

## Cosa cambia

- Scansione SHA-256 parallela e limitata a 1–8 thread, senza affidarsi alla sola data di modifica. Output compatibile con le mappe di hash di SchoolHub.
- Cache in RAM del manifesto remoto: ogni controllo interroga il commit corrente; se il commit è invariato evita clone, checkout, download LFS e nuova scansione remota.
- Clone diretto del branch scelto; recupero originale per branch assenti/repository vuoti.
- Percorso rapido per sincronizzazioni senza modifiche, dopo verifica del commit remoto e del contenuto locale.
- Modalità facoltativa di cache Git di sessione: `fetch` incrementale dei soli oggetti mancanti, clone locale senza rete e riuso degli oggetti LFS. Disattivata per impostazione predefinita perché il cache contiene documenti in chiaro.
- Sincronizzazione con modifiche, gestione dei conflitti, cifratura AES-GCM del Vault, autenticazione e Git LFS rimangono nel codice originale. Non si introduce force-push; la cache dei documenti è solo opzionale e temporanea.

La velocità effettiva non è ancora misurata: dipende da rete, SSD/HDD, dimensioni e quantità di file. Senza cache su disco un cambio di commit richiede ancora il clone remoto; le modifiche a file reali continuano a usare la pipeline originale. Non sono ancora disponibili un installer, una riscrittura Rust integrale o test end-to-end con l'account dell'utente.

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

L'anteprima usa un profilo locale separato `%LOCALAPPDATA%\SchoolHubRust`. Non punta automaticamente al workspace esistente e non modifica il suo avvio automatico. Gli aggiornamenti originali sono disabilitati nell'anteprima. Usare inizialmente una copia di prova del workspace; non collegare il Vault originale fino alla verifica di compatibilità.

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

## Origine

SchoolHub di MeloniMirko, versione 2.6.7, branch schoolhub-build, commit 513285580fbbade3568c8fd4fb3692ab891e4460. Il codice di questo repository è un adattatore e motore di scansione indipendente. La UI, le funzionalità Vault e l'algoritmo originale di sincronizzazione restano nel progetto di origine.
