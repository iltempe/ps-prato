# Guida al gemello digitale del Pronto Soccorso di Prato

Questa guida spiega come usare il gemello digitale del Pronto Soccorso del Santo Stefano:
come si avvia, cosa mostra ogni schermata, cosa significa ogni parametro e come leggere i
risultati senza fargli dire più di quello che sa. Non servono conoscenze di statistica o di
programmazione.

---

## 1. Che cos'è, in breve

Il gemello digitale è una **copia simulata del Pronto Soccorso** che gira sul tuo computer.
Dentro ci sono pazienti virtuali che arrivano, aspettano il medico, fanno esami, vengono
dimessi o ricoverati, esattamente come in un pronto soccorso vero.

La copia è stata **tarata sui dati reali**:

- i numeri ufficiali dell'ASL Toscana Centro ottenuti con l'accesso civico (accessi, tempi di
  permanenza, boarding, abbandoni, personale, anni 2020-2025);
- le presenze misurate ogni 15 minuti dal sito **pspratolive.it**.

Una volta tarata, la copia serve a due cose:

1. **Guardare avanti**: partendo da quante persone ci sono adesso in PS, prevede come andrà
   nelle prossime ore.
2. **Provare scelte diverse**: cosa succede se ci fosse un medico in più la sera, più letti in
   reparto, una casa di comunità che assorbe i codici minori? Il gemello lo simula e lo
   confronta con la situazione attuale, con un costo indicativo.

> Il gemello **non** è un sistema ufficiale e **non** sostituisce i dati dell'ASL. È uno
> strumento di analisi civica: dice cosa succederebbe *secondo il modello*. Quanto il modello
> è affidabile lo mostra lui stesso, nella scheda *Affidabilità*.

---

## 2. Dove si usa

### Online, per tutti

Su **https://pspratolive.it/gemello/** (o dal riquadro *Simulatore* nella pagina principale).
Non serve installare niente: le simulazioni girano nel tuo browser, anche da telefono.
La previsione delle prossime ore si aggiorna da sola a ogni rilevazione (ogni 15 minuti).

Rispetto alla versione locale, online:

- la previsione "e se" (linea blu nella scheda *Adesso*) è un'approssimazione: parte dalla
  previsione pubblicata e la sposta gradualmente verso il risultato della simulazione annua;
- *Su cosa investire* usa simulazioni più corte (circa un minuto di calcolo): i risultati sono un
  po' più rumorosi;
- il test delle previsioni passate e la calibrazione non si possono rifare: si vedono i
  risultati pubblicati.

Nessun parametro o risultato viene inviato a server: resta tutto sul tuo dispositivo.

### In locale, versione completa

**Serve:** un Mac con il progetto `ps-prato` nella cartella `Documenti/GitHub/PS` (c'è già).

Apri l'app **Terminale**, scrivi questo comando e premi Invio:

```
~/Documents/GitHub/PS/gemello/avvia.sh
```

Dopo qualche secondo si apre il browser su **http://localhost:8765**. Se non si apre da solo,
copia quell'indirizzo nel browser.

Per **spegnerlo**: torna nel Terminale e premi `Ctrl` + `C`.

L'avvio scarica anche gli ultimi dati dal repository (`git pull`), così il gemello parte
aggiornato. Funziona tutto sul tuo computer: nessun dato viene inviato altrove; il gemello
legge soltanto la pagina pubblica di pspratolive.it.

---

## 3. La schermata

**In alto a destra** c'è l'indicatore del collegamento:

- **pallino verde**: il gemello sta ricevendo i dati in tempo reale da pspratolive.it (si
  aggiorna da solo ogni 5 minuti);
- **pallino rosso**: il dato live non arriva (sito non raggiungibile, connessione assente
  o dato vecchio). Il gemello continua a funzionare con l'ultimo dato disponibile e lo dice.

**A sinistra** c'è il pannello dei **parametri**: le leve che puoi muovere (medici, accessi,
letti, ecc.). Ogni volta che ne cambi uno, il gemello ricalcola tutto da solo in pochi secondi.
Il pulsante **Ripristina** riporta tutto ai valori di partenza, cioè alla situazione reale.

**Al centro** ci sono le schede: *Adesso*, *Regime annuo*, *Su cosa investire*,
*Storico ASL*, *Affidabilità*.

**Sotto il menu del sito** ci sono tre sotto-link: *Simulazioni* (le schede qui sopra),
*Istruzioni* (questa guida) e *Metodo* (come è costruito e verificato il modello).

**In alto a destra** ci sono due pulsanti per salvare la simulazione:

- **Esporta PDF** apre un rapporto stampabile: parametri modificati, costo, risultati annui
  (totali e per codice), grafici e avvertenze. Dalla finestra di stampa scegli *Salva come PDF*.
  Se non si apre nulla, consenti i pop-up per il sito.
- **Esporta JSON** scarica un file con tutti i parametri e tutti i risultati (previsione e
  regime annuo, base e con i parametri, per codice), utile per rielaborarli o per allegarli a
  un articolo.

*Istruzioni* e *Metodo* si aprono dai sotto-link in alto.

### Come leggere i grafici

| Elemento | Significato |
|---|---|
| Linea nera | dato **osservato** (misurato davvero) |
| Linea grigia tratteggiata | **caso base**: il PS così com'è oggi, simulato |
| Linea blu | **con i parametri scelti**: il PS con le modifiche che hai fatto |
| Fascia colorata intorno a una linea | **forchetta all'80%**: in 8 casi su 10 il valore vero cade lì dentro |
| Linea rossa orizzontale "83 postazioni" | la capacità del PS dichiarata dall'ASL |
| Linea verticale "adesso" | il momento dell'ultima rilevazione |

Se non hai cambiato nessun parametro, la linea grigia non c'è: c'è solo la previsione (blu).
Passando con il mouse sui grafici compaiono i valori esatti.

---

## 4. Le schede, una per una

### Adesso

Cosa succede ora e nelle prossime ore.

- **Riquadri in alto**: quante persone ci sono in PS adesso (e che percentuale delle 83
  postazioni rappresentano), quante aspettano la prima visita, quante se ne prevedono tra 3 e
  tra 12 ore, e la probabilità di restare oltre le 83 postazioni.
- **Grafico grande**: le ultime 24 ore misurate e la previsione delle prossime ore. Puoi
  scegliere l'orizzonte: 6, 12 o 24 ore.
- **Persone in attesa della prima visita**: stessa cosa, solo per chi non è ancora stato visitato.
- **Probabilità di essere oltre le 83 postazioni**, ora per ora.
- **Per codice di triage**: scegli un codice (1-5) e vedi presenti e in attesa di quel codice,
  misurati e previsti.
- **Stato attuale per codice**: la tabella dell'ultima rilevazione.

### Regime annuo

Come funzionerebbe il PS **in media su un anno intero** con i parametri scelti. È la scheda
giusta per valutare una scelta strutturale (es. "un medico in più ogni pomeriggio").

- **Riquadri**: permanenza media, attesa della prima visita, quota di persone oltre 24 ore,
  attesa di un letto (boarding), percentuale di tempo oltre le 83 postazioni, presenti medi,
  costo annuo indicativo delle modifiche. Sotto ogni numero c'è la variazione rispetto al caso
  base: **verde** se migliora, **rosso** se peggiora.
- **Presenti medi per ora del giorno**: la giornata tipo, reale e simulata.
- **Per codice di triage**: scegli l'indicatore dal menu (permanenza, attesa, oltre 24 ore,
  oltre 8 ore, presenti) e confronta reale, base e parametri scelti per ogni codice.
- **Confronto per codice**: una tabella con tutti gli indicatori per ognuno dei 5 codici.

Ogni calcolo richiede qualche secondo. Differenze sotto 1-2 punti percentuali sono rumore
statistico: non vanno lette come un effetto.

### Su cosa investire

Chiedi al gemello: *qual è il modo meno costoso per ridurre i tempi del X%?*

1. Scegli l'**obiettivo** (di partenza 30%).
2. Scegli la **metrica**:
   - *permanenza media in PS*: quanto resta in media ogni paziente;
   - *attesa della prima visita*;
   - *presenti medi (affollamento)*: quante persone ci sono in media in PS. È la metrica giusta
     quando le leve tolgono pazienti dal PS (vedi il riquadro qui sotto);
   - le stesse misure per un singolo codice (es. "permanenza media dei codici 3").

> **Attenzione all'effetto composizione.** La permanenza *media* è una media su tutti i
> pazienti. Se una casa di comunità toglie dal PS i codici bianchi, che restano poco, la media
> di chi resta sale, anche se il PS è più vuoto. Per valutare leve di questo tipo usa la
> metrica *presenti medi*.
3. Premi **Calcola**. Servono alcuni minuti.

Il gemello prova ogni leva d'investimento da sola, poi costruisce un **mix**: a ogni passo
aggiunge la leva con il miglior rapporto tra beneficio e costo, tenendo conto di quelle già
scelte (due leve insieme non sempre sommano i loro effetti). Si ferma quando raggiunge
l'obiettivo, o quando nessuna leva aiuta più.

Il calcolo parte dai parametri impostati nel pannello di sinistra: se vuoi partire dalla
situazione reale, premi prima **Ripristina**.

### Storico ASL

I dati ufficiali 2020-2025 per codice: accessi, permanenza media, permanenza di ogni codice
rispetto alla media, quota oltre 24 ore. Il 2021 (pandemia) è escluso dalle linee perché
anomalo. In basso c'è la **crescita media annua degli accessi per codice**, che il gemello
usa quando sposti il parametro *Anni nel futuro*.

### Affidabilità

Qui il gemello mette alla prova se stesso.

- **Il gemello prevede bene?** Rifà le previsioni sugli ultimi giorni come se fosse stato
  acceso allora, e le confronta con quello che è successo davvero. Le confronta anche con due
  previsioni "banali": *resta tutto com'è* e *media delle stesse ore nei giorni passati*. In
  verde il metodo che sbaglia meno. La *copertura* dice quante volte il valore vero è caduto
  dentro la forchetta all'80%: dovrebbe essere vicina all'80%.
- **Il modello riproduce gli anni passati?** Dà al modello gli accessi di ciascun anno dal
  2020 al 2025 e controlla se ritrova le permanenze vere.
- **Calibrazione**: ritara il modello. Serve quando sono passate settimane di nuovi dati,
  oppure per tararlo su un altro anno ASL. Ci vogliono alcuni minuti.
- **Ricarica dati**: rilegge il file delle presenze dopo un aggiornamento.

---

## 5. I parametri

### Modello di base

| Parametro | Cosa significa |
|---|---|
| **Turni medici A / B** | Il documento ASL si presta a due letture sul turno serale 20-02. **A**: ci sono 4 medici (3 del notturno + 1 della "nottina"). **B**: c'è 1 solo medico. Il modello tarato con la lettura A riproduce l'andamento reale delle attese; con la B no. |
| **La rivalutazione passa davanti ai nuovi arrivi** | Dopo gli esami il paziente deve rivedere il medico per essere dimesso. Se la casella è accesa (valore di partenza) ha la precedenza sui nuovi arrivi; se è spenta aspetta il suo turno come un nuovo arrivo. Solo con la casella accesa il modello riproduce i tempi ASL di tutti i codici, quindi è l'ipotesi di riferimento. Spegnerla serve solo per confronto. |

### Medici in servizio

| Parametro | Cosa significa |
|---|---|
| **Fascia 08-14, 14-20, 20-02, 02-08** | Quanti medici vedono pazienti in quella fascia (escluso il medico dell'osservazione breve). Ogni medico in più costa circa 165.000 € l'anno per coprire una fascia di 6 ore tutti i giorni. |
| **Tempo medico per paziente** | Quanto tempo il medico dedica a ogni paziente, rispetto al valore ricavato dai dati (×1,00). Sotto 1 = medici più rapidi (es. più supporto amministrativo o infermieristico); sopra 1 = più lenti. |

### Domanda

| Parametro | Cosa significa |
|---|---|
| **Accessi** | Moltiplica tutti gli accessi (es. ×1,20 = 20% di pazienti in più, come in un picco influenzale). |
| **Anni nel futuro** | Fa crescere gli accessi di ogni codice al ritmo medio 2022-2025 (i codici 4-5 crescono molto più dei codici 1-3). Utile per chiedersi *come sarà nel 2030 se non cambia niente*. |
| **Pazienza prima di abbandonare** | Quanto a lungo chi aspetta resiste prima di andarsene. Più pazienza = meno abbandoni ma più persone in sala d'attesa. |

### Per codice di triage

Scegli il codice con i pulsanti in alto (un pallino blu segnala quelli modificati).

| Parametro | Cosa significa | Esempio |
|---|---|---|
| **Accessi** | Più o meno pazienti di quel codice | codici 5 ×1,5 in estate |
| **Tempo tra visita e decisione** | Riduce esami, consulenze e osservazione di quel codice | −20% per i codici 3 con una TAC dedicata |
| **Gestiti fuori dal PS** (codici 3-5) | Quota di pazienti presi in carico altrove | 40% dei codici 5 in una casa di comunità |
| **Probabilità di ricovero** (codici 1-4) | Quanti pazienti di quel codice vengono ricoverati | ×0,9 con percorsi alternativi al ricovero |

### Letti a valle (boarding)

Il **boarding** è l'attesa di un letto in reparto da parte di chi deve essere ricoverato: il
paziente resta su una barella in PS finché un letto non si libera.

| Parametro | Cosa significa |
|---|---|
| **Letti in più nei reparti** | Letti aggiunti nei reparti che ricevono dal PS (degenza media 8 giorni). Costo indicativo: 600 € al giorno per letto. |
| **Degenza media in reparto** | Ridurre la degenza (dimissioni al mattino e nel weekend) libera letti senza costruirne di nuovi. |
| **I letti crescono con i ricoveri** | Da usare con *Anni nel futuro*: i letti aumentano quanto basta a seguire la crescita dei ricoveri. |

### Leve d'investimento

Interventi "a pacchetto" descritti nel file `leve.yaml` (fast track, diagnostica dedicata,
bed manager, CAU, ecc.), ciascuno con il suo costo. Spuntane uno per vederne l'effetto. I costi
e alcuni effetti sono **stime da verificare**: il file si può modificare con un editor di testo.

In fondo al pannello compare il **costo annuo indicativo** delle modifiche fatte.

---

## 6. Domande tipiche: come fare

**"Stasera il PS reggerà?"**
Scheda *Adesso*, senza toccare i parametri. Guarda la previsione e la probabilità di restare
oltre le 83 postazioni.

**"Se stasera ci fosse un medico in più, cosa cambierebbe?"**
Scheda *Adesso*. Porta *Fascia 20-02* da 4 a 5. La linea blu mostra la previsione con il
medico in più, quella grigia senza. Guarda soprattutto il grafico delle persone in attesa.

**"Un medico in più il pomeriggio, tutto l'anno: quanto si guadagna e quanto costa?"**
Scheda *Regime annuo*. Porta *Fascia 14-20* da 7 a 8 e leggi i riquadri e il costo.

**"Una casa di comunità che prende metà dei codici bianchi servirebbe?"**
Pannello *Per codice di triage* → Codice 5 → *Gestiti fuori dal PS* 50%. Poi scheda
*Regime annuo*: guarda **presenti medi** e **attesa della prima visita**, non la permanenza
media (vedi l'effetto composizione in *Su cosa investire*). Per i codici 4-5 l'effetto
sull'affollamento è limitato, perché quei pazienti restano in PS poche ore.

**"I codici 3 aspettano troppo: cosa servirebbe?"**
Scheda *Su cosa investire*, metrica *permanenza media dei codici 3*, obiettivo 30%, Calcola.

**"Come sarà il PS nel 2030 se non si fa niente?"**
*Anni nel futuro* = 5, poi scheda *Regime annuo*. Prova poi ad accendere *I letti crescono con i
ricoveri* per vedere quanto pesa il collo di bottiglia dei letti.

**"Quanto costa ridurre i tempi del 30%?"**
*Ripristina*, poi scheda *Su cosa investire*, obiettivo 30%, Calcola. Se il gemello risponde
che l'obiettivo **non è raggiunto con le leve disponibili**, non è un errore: con gli interventi
descritti in `leve.yaml` non ci si arriva, e servono interventi più forti sui tempi dopo la
visita o sui letti. Puoi aggiungerne di nuovi modificando `leve.yaml`.

**"Dove serve un medico in più?"**
Sposta di una unità ciascuna fascia, una alla volta, e guarda nella scheda *Regime annuo*
l'**attesa della prima visita**. Un medico in più accorcia soprattutto l'attesa della visita;
sulla permanenza complessiva incide poco, perché la maggior parte del tempo si passa dopo la
visita.

---

## 7. Leggere i risultati con prudenza

- **È una simulazione, non una misura.** I numeri dicono cosa succederebbe *se* il pronto
  soccorso funzionasse come il modello. Il modello è stato verificato (scheda *Affidabilità*),
  ma resta una semplificazione.
- **Vede i numeri, non le persone.** Conosce quanti pazienti ci sono per codice, non chi sono,
  da quanto aspettano, quali esami fanno. Non sa quanti medici sono davvero in turno stasera
  né quanti letti sono liberi.
- **Le previsioni a breve** sono state verificate sull'ultimo mese. Sul numero di presenti il
  gemello sbaglia in media di circa 6 persone a un'ora e di circa 15 a dodici ore. Sulle
  persone in attesa sbaglia di circa 3 persone a un'ora e di 5 a tre ore. È la previsione
  migliore tra quelle confrontate, ma resta una stima, con la sua forchetta.
- **Gli effetti delle leve sono probabilmente un massimo.** Negli anni passati il PS era lento
  anche quando arrivavano meno pazienti: i tempi non dipendono solo da quanti pazienti
  arrivano. Ridurre gli accessi potrebbe quindi rendere meno di quanto simulato.
- **I costi sono indicativi** (stipendi medi, costo medio di un giorno di degenza) e vanno
  verificati con dati aziendali prima di essere citati.
- **Le differenze piccole** (1-2 punti percentuali) sono rumore della simulazione.

Quando citi un risultato, conviene dire sempre: *"secondo un modello tarato sui dati ASL e
sulle presenze misurate"*, indicare l'ipotesi usata (turni A/B, rivalutazione) e, per le
proiezioni, gli anni.

---

## 8. Aggiornare e ritarare

- **Ogni avvio** con `avvia.sh` scarica gli ultimi dati. Mentre è acceso, il gemello legge il
  dato live ogni 5 minuti e lo conserva.
- **Ogni qualche settimana**, o quando cambia la stagione, conviene ritarare: scheda
  *Affidabilità* → *Calibrazione* → *Calibra* (per la lettura A, e se vuoi anche la B).
- **Quando arriveranno i dati ASL 2026**, basterà aggiungerli in `data/ufficiali/` nello
  stesso formato e scegliere l'anno nella calibrazione.
- **Per cambiare le ipotesi** (obiettivo predefinito, costi, effetti delle leve, porta del
  server) si modificano i file `config.yaml` e `leve.yaml` con un editor di testo; ogni voce
  è commentata. Poi si riavvia il gemello.

---

## 9. Glossario

| Termine | Significato |
|---|---|
| **Codice di triage** | Priorità assegnata all'arrivo: 1 emergenza, 2 urgenza indifferibile, 3 urgenza differibile, 4 urgenza minore, 5 non urgenza. Sul sito pspratolive.it compaiono come colori (rosso, giallo, verde, azzurro, bianco). |
| **Permanenza** | Tempo totale passato in PS, dall'accettazione alla chiusura della pratica. |
| **Attesa della prima visita** | Tempo tra l'arrivo e il primo contatto con il medico. |
| **Presenti** | Persone in PS in un certo momento: in attesa + in trattamento. |
| **Boarding** | Attesa in PS, già con la decisione di ricovero, che si liberi un letto in reparto. |
| **83 postazioni** | Posti (sedute o barelle) del PS dichiarati dall'ASL. |
| **Forchetta all'80%** | Intervallo in cui, secondo il modello, il valore vero cade 8 volte su 10. |
| **Caso base** | Il PS simulato così com'è oggi, senza modifiche. |
| **Regime** | Il comportamento medio su un lungo periodo, al netto delle oscillazioni giornaliere. |
| **Calibrazione** | Regolazione del modello finché riproduce i dati reali. |
| **Leva** | Un intervento possibile (più medici, più letti, una CAU...) con il suo costo. |
| **Legge di Little** | Presenti medi = arrivi per ora × permanenza media. È il legame che collega le presenze misurate ai tempi dell'ASL. |
| **CAU** | Centro di assistenza e urgenza: struttura territoriale per i casi meno gravi. |

---

## 10. Se qualcosa non va

| Problema | Cosa fare |
|---|---|
| Il browser dice "impossibile raggiungere il sito" | Il gemello non è acceso: rilancia `avvia.sh` e aspetta il messaggio "Gemello digitale … http://localhost:8765". |
| Pallino rosso in alto | Il dato live non arriva. Controlla la connessione; il gemello usa intanto l'ultimo dato salvato. |
| "Scenario non calibrato" nel pannello | Quella combinazione di turni e rivalutazione non è ancora tarata: scheda *Affidabilità* → *Calibrazione*. |
| I grafici restano sbiaditi | Il calcolo è in corso; con parametri nuovi la prima volta servono alcuni secondi. |
| "Address already in use" all'avvio | Il gemello è già acceso in un'altra finestra del Terminale: usa quella, oppure chiudila con `Ctrl` + `C`. |
| "Code in crescita" / "instabile" | Con quei parametri il PS non ce la fa: ogni giorno entrano più pazienti (o più ricoveri) di quanti se ne possano gestire, e le code crescono senza fine. Non è un errore del programma. |

Per i dettagli tecnici (come è costruito il modello, come è stato tarato e verificato) vedi
la nota di **[Metodo](/metodo)** (file `METODO.md`).
