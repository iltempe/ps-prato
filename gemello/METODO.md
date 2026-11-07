# Nota di metodo · Gemello digitale del PS Santo Stefano

Questa nota descrive come è costruito il modello, su quali dati è tarato, come è stato
verificato e quali sono i suoi limiti. È pensata per chi deve valutarne l'affidabilità
(giornalisti, ricercatori, tecnici dell'azienda sanitaria). Per l'uso pratico vedi la
**[Guida](/guida)** (`GUIDA.md`).

Situazione al 7 novembre 2026: dati ASL 2025, presenze dal 9/9/2026 al 7/11/2026.

---

## 1. Dati

| Fonte | Contenuto | Uso nel modello |
|---|---|---|
| ASL Toscana Centro, accesso civico prot. 158918/2026 (`data/ufficiali/`) | Per anno 2020-2025 e per codice di triage: accessi, permanenza media, quota oltre 8 h e oltre 24 h; boarding (numero e attesa media); abbandoni; postazioni (83); personale medico per fascia | **bersagli di calibrazione** (anno di riferimento 2025) e validazione storica |
| pspratolive.it (`data/presenze.csv`, live `data/latest.json`) | Ogni 15 minuti, per codice colore: persone in attesa e in trattamento (fonte primaria ASL, tramite l'aggregatore prontosoccorso.live) | attese per codice, curva oraria, stato iniziale del gemello, test retroattivo |

**Corrispondenza colori → codici.** Non è dichiarata dalla fonte. È ricavata con la Legge di
Little: presenti medi per colore ≈ accessi ASL × permanenza ASL per codice / 8760. Torna con
rosso = 1, giallo = 2, verde = 3, azzurro = 4, bianco = 5 (es. verde: 82,9 presenti misurati
contro 83,4 attesi per il codice 3).

**Allineamento dei periodi.** Le presenze misurate (autunno 2026) sono riportate al carico
2025 in proporzione (presenti ASL 2025 con Little / presenti medi misurati).

---

## 2. Bilancio delle ore-paziente (diagnosi senza simulazione)

Ore-paziente 2025 = Σ accessi × permanenza = **1.075.694** (123 presenti in media, permanenza
media 11,1 h). Scomposizione per fase:

| Fase | Fonte | Quota delle ore |
|---|---|---|
| Attesa della prima visita | presenti "in attesa" misurati (Little) | 13% |
| Boarding (attesa del letto dopo la decisione di ricovero) | ASL: 9.149 × 13 h 15′ | 11% |
| Processo (visita, esami, consulenze, osservazione, attesa esiti) | differenza | **76%** |

Il codice 3 da solo vale il 68% delle ore. I codici 4-5 insieme valgono il 13%: nessuna leva
che agisca solo su di loro può ridurre la permanenza complessiva oltre il 13%.

---

## 3. Simulazione a eventi discreti

Libreria SimPy (`modello/simulazione.py`). Ogni paziente virtuale segue questo percorso:

1. **Arrivo**: processo di Poisson non omogeneo. Il volume per codice viene dall'ASL; il
   profilo orario è stimato **deconvolvendo** la curva oraria delle presenze misurate con la
   distribuzione della permanenza (minimi quadrati non negativi con regolarizzazione).
2. **Attesa della prima visita**: coda unica di medici con orario per fascia (lettura A: 8 / 7
   / 4 / 3 medici nelle fasce 08-14 / 14-20 / 20-02 / 02-08). Ordine di presa in carico "a
   scadenza": priorità = arrivo + margine per codice (il codice 1 passa sempre davanti). I
   margini sono tarati sulle attese misurate per codice. Abbandono possibile per i codici 3-5
   (pazienza esponenziale).
3. **Visita** (tempo medico per codice × un fattore unico tarato).
4. **Processo**: due percorsi per codice. Con probabilità *q* il paziente segue un percorso
   **lungo** (osservazione, consulenze, attesa di posto), altrimenti uno **breve**; entrambi
   lognormali. Il percorso non occupa il medico.
5. **Rivalutazione/dimissione** dal medico, con precedenza sui nuovi arrivi (vedi §5).
6. **Boarding**, solo per chi è ricoverato: coda dei letti di reparto come sistema a molti
   serventi (Erlang C). Per chi aspetta, il tempo è esponenziale con media
   1 / (letti liberati al giorno − ricoveri al giorno). Il margine è ricavato dall'attesa ASL
   (13 h 15′ → 1,81 letti/giorno di margine); quota dei ricoveri da PS sui reparti = 60%
   (ipotesi).

Le postazioni (83) non sono un vincolo rigido: il PS reale le supera stabilmente (sedute e
barelle aggiunte). Il modello misura il tempo passato oltre quella soglia.

---

## 4. Calibrazione

Parametri regolati automaticamente, ciascuno su un bersaglio (a passi separati, perché il
sistema medici lavora vicino alla saturazione e un aggiornamento congiunto oscilla):

| Parametro | Bersaglio |
|---|---|
| quota del percorso lungo per codice | quota oltre 8 h ASL per codice |
| dispersione del percorso lungo (codici 1-3) | quota oltre 24 h ASL per codice |
| durata del percorso lungo per codice | permanenza media ASL per codice |
| probabilità di ricovero (scala) | numero di boarding ASL |
| capacità dei letti | attesa media di boarding ASL |
| margini di priorità per codice | attesa della prima visita misurata per codice |
| fattore tempo medico | persone in attesa misurate (media) |
| pazienza | tasso di abbandono ASL |

### Risultato (scenario di riferimento: turni A, rivalutazione con precedenza)

| Indicatore | Simulato | Reale |
|---|---|---|
| Permanenza media | 11,4 h | 11,1 h |
| Presenti medi | 126 | 123 |
| Persone in attesa della visita | 12,8 | 15,8 |
| Boarding: attesa | 13,6 h | 13,2 h |
| Abbandoni | 5,1% | 4,7% |

| Codice | Permanenza sim / reale | Oltre 8 h sim / reale | Oltre 24 h sim / reale | Attesa visita sim / reale |
|---|---|---|---|---|
| 1 | 18,4 / 18,7 h | 50% / 47% | 23% / 22% | 4′ / 5′ |
| 2 | 23,9 / 23,6 h | 53% / 55% | 35% / 28% | 29′ / 33′ |
| 3 | 16,0 / 15,5 h | 35% / 35% | 23% / 16% | 1 h 38′ / 2 h 06′ |
| 4 | 3,8 / 3,9 h | 5% / 6% | 4% / 2% | 53′ / 1 h 14′ |
| 5 | 2,2 / 2,3 h | 2% / 2% | 2% / 1% | 25′ / 27′ |

Errori residui: le persone in attesa sono sottostimate di circa il 20% e la quota oltre 24 h
dei codici 2-3 è sovrastimata di 5-7 punti. In una coda vicina alla saturazione permanenza e
attesa si contendono la taratura: migliorare l'una peggiora l'altra.

---

## 5. Quale ipotesi reggono i dati

Due aspetti del funzionamento reale non sono dichiarati. Il modello li tratta come
alternative e controlla quale riproduce i dati.

**Turni medici 20-02.** La tabella ASL indica "nottina (20-02): 1" e "notturno: 3".
- **A**: 3 medici notturni + 1 medico della nottina = 4 medici tra le 20 e le 2.
- **B**: 1 solo medico tra le 20 e le 2.

Test indipendente: la curva oraria delle persone in attesa, che non è usata per tarare.
Correlazione fra curva simulata e misurata: **A = +0,73**; **B = −0,34**. Con B il modello
mette i picchi di attesa nelle ore sbagliate, qualunque sia la taratura. La lettura A è
quella coerente con i dati.

**Rivalutazione prima della dimissione.** Il paziente che ha finito gli esami aspetta il medico
come un nuovo arrivo ("normale") o ha la precedenza? Con la variante normale la calibrazione
non riesce a riprodurre i codici 3 (permanenza 10,1 h contro 15,5; oltre 24 h 4% contro
16%), perché la coda per la dimissione crea troppe permanenze tra 8 e 24 h. Con la
precedenza tutti i codici tornano entro il 5% sulla permanenza. **Riferimento: precedenza.**

---

## 6. Validazioni

### 6.1 Anni passati (modello tarato sul 2025, solo accessi per codice dell'anno)

| Anno | Accessi | Permanenza reale | Permanenza simulata | Boarding reale | Boarding simulato |
|---|---|---|---|---|---|
| 2020 | 65.060 | 11,0 h | 10,3 h | — | 2,6 h |
| 2022 | 85.558 | 11,0 h | 11,2 h | 20,4 h | 7,7 h |
| 2023 | 91.111 | 10,3 h | 11,3 h | 14,5 h | 9,5 h |
| 2024 | 94.341 | 10,8 h | 11,7 h | 10,4 h | 14,5 h |
| 2025 | 97.007 | 11,1 h | 11,4 h | 13,2 h | 13,4 h |

La permanenza complessiva è riprodotta entro circa un'ora in tutti gli anni. Il boarding no:
nel 2022 era molto più lungo di quanto il solo carico spieghi. La disponibilità di letti è
cambiata nel tempo, indipendentemente dagli accessi. Per questo le proiezioni sui letti vanno
lette come indicazioni di direzione.

### 6.2 Previsione a breve (backtest, 30 giorni, 225 previsioni, una ogni 3 ore)

Errore medio assoluto, in persone. Persistenza = "resta tutto com'è"; media oraria = profilo
medio dei giorni precedenti ancorato al livello attuale.

| Orizzonte | Presenti: gemello | persistenza | media oraria | In attesa: gemello | persistenza | media oraria |
|---|---|---|---|---|---|---|
| +1 h | **5,9** | 6,9 | 6,0 | **3,3** | 3,8 | 6,1 |
| +3 h | **10,2** | 14,5 | 10,3 | **5,2** | 7,2 | 5,9 |
| +6 h | **13,8** | 21,6 | 14,3 | 6,2 | 10,5 | **5,9** |
| +12 h | **15,5** | 24,7 | 17,3 | 6,4 | 13,1 | **5,9** |

Il gemello è la previsione migliore o alla pari a tutti gli orizzonti sui presenti, e fino a
3 ore sulle persone in attesa. La forchetta all'80% contiene il valore vero nel 74-82% dei
casi (fattore di allargamento 1,8).

**Metodo di previsione: analoghi.** Il modello calibrato viene simulato a lungo (8 × 180
giorni). Per lo stato reale di adesso si scelgono i 60 istanti simulati più simili (stessa ora
± 1 h, presenze per codice vicine) e si usa la loro evoluzione successiva. Questa viene
corretta per la differenza di livello osservato−simulato (con un'attenuazione di 24 h) e per
la differenza fra profilo orario reale e simulato. Il metodo "a iniezione", che ricostruisce
lo stato interno da zero, è più debole (non batte la persistenza) ed è disponibile solo per
confronto.

---

## 7. Leve d'investimento e ottimizzazione

Le leve sono descritte in `leve.yaml`: cosa cambiano nel modello e quanto costano. Costi di
riferimento: medico 110.000 €/anno, cioè circa 165.000 €/anno per coprire 6 ore al giorno;
infermiere 48.000 €/anno; giornata di degenza 600 €.

**Algoritmo**: ricerca *greedy* sulla simulazione, con 6 repliche × 182 giorni per scenario.
A ogni passo aggiunge la leva con il miglior rapporto riduzione/costo, dato il mix già
scelto, fino all'obiettivo.

### Risultato con il modello di riferimento (obiettivo −30% di permanenza media)

| Leva da sola | Effetto sulla permanenza | Costo/anno |
|---|---|---|
| Diagnostica dedicata H24 | −6,7% | 600 k€ |
| Bed manager / dimissioni anticipate | −4,8% | 250 k€ |
| +10 letti di area medica | −4,5% | 2.190 k€ |
| Fast track codici 4-5 | −2,9% | 475 k€ |
| Protocolli consulenze | −2,9% | 120 k€ |
| +1 medico (una fascia) | −1,9 / −2,5% | 165 k€ |
| CAU codici minori | +3,7% (effetto composizione, vedi sotto) | 900 k€ |

Mix scelto, in ordine: consulenze → bed management → +1 medico 20-02 → +1 medico 14-20 →
diagnostica → altri medici → fast track → letti. Raggiunge **−24,6%** e si ferma: **con le
leve elencate il −30% non si raggiunge**. Per arrivarci servono interventi più forti sul
processo dopo la visita (il 76% delle ore) o sulla disponibilità di letti.

Con la rivalutazione in precedenza i medici in più pesano poco sulla permanenza (circa −2%
ciascuno) ma molto sull'**attesa della prima visita**: un medico in più per 2 ore la riduce
del 7-19% secondo la fascia, di più tra le 14 e le 18 e tra le 22 e le 24.

**Effetto composizione.** La permanenza *media* è calcolata su tutti i pazienti. Una leva che
toglie dal PS pazienti brevi (CAU, codici 5) fa salire la media degli altri anche se il PS è
meno affollato. Per valutare queste leve si usa la metrica **presenti medi** (ore-paziente),
disponibile in `ottimizza.py --metrica presenti` e nell'interfaccia. Con questa metrica la CAU
vale −5,6% da sola ed entra nel mix. Il mix arriva a **−26,2% dei presenti medi** (circa
94 presenti invece di 127), sempre senza raggiungere il −30%: l'attesa della visita scende
da 72′ a 10′, ma il PS resta oltre le 83 postazioni il 74% del tempo. Per lo stesso motivo,
nelle proiezioni la permanenza media cala negli anni (crescono soprattutto i codici 5).

### Proiezioni (crescita accessi per codice 2022-2025: +0,9%, +1,8%, +1,6%, +5,4%, +18,3%)

Senza interventi e a letti invariati, la permanenza sale a 11,8 h nel 2026, 12,7 h nel 2027 e
15,4 h nel 2028. Dal 2029 i ricoveri superano i letti disponibili e le code non si
stabilizzano. Con il mix la permanenza resta intorno a 8 h fino al 2030.

---

## 8. Versione online (pspratolive.it/gemello/)

Il sito è statico (GitHub Pages): non c'è un server che esegue Python. Per questo:

- **Simulazione nel browser.** Il motore è riscritto in JavaScript (`ui/motore.js`) con la stessa
  logica e gli stessi parametri calibrati (`ui/dati/scenario_*.json`, esportati da
  `modello/esporta.py`). Su 120 giorni simulati dello scenario di riferimento: permanenza
  11,36 h (Python) contro 11,49 h (JavaScript), presenti 125 contro 127, codice 3 15,9 contro
  16,1 h: differenze dentro il rumore statistico. Il calcolo gira in un Web Worker.
- **Previsione pubblicata.** A ogni campione la GitHub Action esegue
  `modello/previsione_pubblica.py` (solo numpy) con la libreria di analoghi dello scenario di
  riferimento (`output/libreria_*.npz`) e pubblica `ui/dati/previsione.json`.
- **"E se" sulle prossime ore.** Online non si ricostruisce una libreria di analoghi per ogni
  scenario: la previsione con i parametri scelti è la previsione pubblicata più la differenza
  di regime (scenario − base) ora per ora, che entra con un'attenuazione esponenziale (tempo
  caratteristico = attesa media della visita per le persone in attesa, permanenza media per i
  presenti). Se cambiano solo i medici, l'effetto parte dalla prima ora in cui il turno è diverso.
- **Ottimizzazione nel browser** con simulazioni più corte (120 giorni × 3 repliche, sezione
  `gemello.web` di `config.yaml`); backtest e validazione storica pubblicati come calcolati in
  locale (`ui/dati/affidabilita.json`); la validazione storica si può rifare nel browser.
- **Esportazioni**: rapporto stampabile (PDF tramite la stampa del browser) e JSON con parametri e
  risultati completi, generati sul dispositivo dell'utente.

## 9. Limiti

1. **Modello aggregato.** Non osserva singoli pazienti, turni effettivi, letti liberi, arrivi
   in ambulanza, giorno della settimana.
2. **Medie annue.** I dati ASL sono medie e quote annue: la forma delle distribuzioni dentro
   l'anno è ricostruita, non misurata.
3. **Periodo delle presenze breve** (autunno 2026): niente stagionalità invernale/estiva.
4. **Ipotesi non verificate**: quota dei ricoveri da PS sui reparti (60%), degenza media (8
   giorni), effetti delle leve "processo", "fast track" e "dimissioni", tutti i costi.
5. **Effetti come tetti massimi**: il carico non spiega da solo le differenze tra anni (§6.1).
6. **Rumore statistico**: differenze sotto 1-2 punti percentuali tra scenari non sono
   significative.

---

## 10. Riproducibilità

```
cd gemello
.venv/bin/python modello/simulazione.py A precedenza                         # calibrazione (~15 min)
.venv/bin/python modello/simulazione.py A precedenza --rifinisci             # rifinitura medici/attese
.venv/bin/python modello/simulazione.py A precedenza --rifinisci --solo-permanenze
.venv/bin/python modello/ottimizza.py --turni A --target 0.30                # report in output/
.venv/bin/python modello/storico.py
```

Dopo ogni calibrazione, per aggiornare il sito:

```
.venv/bin/python modello/esporta.py      # dati/, pagine, libreria analoghi, affidabilità
```

Tutti i parametri sono in `config.yaml` e `leve.yaml`. Gli scenari calibrati e le validazioni
sono in `output/scenario_*.yaml` e `output/validazione_*.json`.
