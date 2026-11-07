# Modello PS Santo Stefano: obiettivo -30% di permanenza

Dati ASL 2025 (accesso civico prot. 158918/2026) + presenze misurate ogni 15 minuti (2026-09-09 → 2026-11-07, 5788 rilevazioni). Turni medici: lettura A (rivalutazione con precedenza). Simulazione: 182 giorni × 6 repliche per scenario.

## 1. Dove sta il tempo (bilancio ore-paziente)

Ore-paziente 2025: 1.075.694 (= 123 presenti in media. permanenza media 11.1h)
Obiettivo -30%: togliere 322.708 ore-paziente/anno (permanenza media da 11.1h a 7.8h)

| Codice | Accessi | Ore-paziente | Quota | Attesa visita | Processo | Boarding |
|---|---|---|---|---|---|---|
| 1 Emergenza | 1.736 | 32.463 | 3% | 0.0% | 1.9% | 1.1% |
| 2 Urg. indifferibile | 7.337 | 173.520 | 16% | 0.4% | 12.0% | 3.8% |
| 3 Urg. differibile | 47.190 | 730.658 | 68% | 8.8% | 53.1% | 6.0% |
| 4 Urg. minore | 29.494 | 113.552 | 11% | 3.3% | 6.9% | 0.4% |
| 5 Non urgenza | 11.250 | 25.500 | 2% | 0.4% | 1.9% | 0.0% |
| **Totale** | 97.007 | 1.075.694 | 100% | **13%** | **76%** | **11%** |

Tetto teorico per ogni fase (se la si azzerasse del tutto):
- attesa: -13% → NON basta da sola per il -30%
- processo: -76% → basta da sola per il -30%
- boarding: -11% → NON basta da sola per il -30%
- tutti i codici 4-5 insieme (fast track, CAU, see & treat): al massimo -13%

## 2. Il modello riproduce la realtà?

| Indicatore | Simulato | Reale |
|---|---|---|
| Permanenza media | 11.4 h | 11.1 h |
| Presenti medi | 126 | 123 |
| Persone in attesa visita | 12.8 | 15.8 |
| Boarding / anno | 9.129 | 9.149 |
| Attesa boarding | 13.6 h | 13.2 h |
| Abbandoni | 5.1% | 4.7% |
| Codice 1: permanenza / >24h / attesa visita | 18.4h / 23% / 4′ | 18.7h / 22% / 5′ |
| Codice 2: permanenza / >24h / attesa visita | 23.9h / 35% / 29′ | 23.6h / 28% / 33′ |
| Codice 3: permanenza / >24h / attesa visita | 16.0h / 23% / 98′ | 15.5h / 16% / 126′ |
| Codice 4: permanenza / >24h / attesa visita | 3.8h / 4% / 53′ | 3.9h / 2% / 74′ |
| Codice 5: permanenza / >24h / attesa visita | 2.2h / 2% / 24′ | 2.3h / 1% / 27′ |

Test indipendenti (curve orarie non usate per calibrare): correlazione presenti per ora **0.89**, persone in attesa per ora **0.73** (errore medio 3.9 persone).

## 3. Ogni leva da sola (ordinate per efficienza)

| Leva | Effetto su permanenza | Costo/anno | Costo per punto % | Attesa visita | Tempo con >83 presenti |
|---|---|---|---|---|---|
| Protocolli consulenze specialistiche con tempi garantiti | -2.9% | 120 k€ | 42 k€ | 71′ | 99% |
| Bed manager + discharge room (dimissioni entro le 11, anche nel weekend) | -4.8% | 250 k€ | 53 k€ | 72′ | 99% |
| +1 medico fascia 14-20 | -2.5% | 165 k€ | 66 k€ | 45′ | 99% |
| +1 medico fascia 20-02 | -2.3% | 165 k€ | 71 k€ | 50′ | 99% |
| +1 medico fascia 08-14 | -2.0% | 165 k€ | 81 k€ | 54′ | 99% |
| +1 medico fascia 02-08 | -1.9% | 165 k€ | 86 k€ | 54′ | 100% |
| Diagnostica dedicata al PS H24 (TAC + refertazione) | -6.7% | 600 k€ | 89 k€ | 73′ | 98% |
| Fast track codici 4-5 (medico + infermiere, 8-20) | -2.9% | 475 k€ | 164 k€ | 36′ | 100% |
| +10 letti di area medica | -4.5% | 2.190 k€ | 489 k€ | 72′ | 99% |
| CAU / casa di comunità per codici minori | +3.7% | 900 k€ | — | 47′ | 99% |

Base: permanenza 11.4h, attesa visita 72′, oltre 83 presenti il 100% del tempo. Rumore statistico tipico: ±1-2 punti.

## 4. Su cosa investire: mix minimo per -30%

| Ordine | Leva | Guadagno | Cumulato | Costo/anno | Costo cumulato |
|---|---|---|---|---|---|
| 1 | Protocolli consulenze specialistiche con tempi garantiti | -2.9% | -2.9% | 120 k€ | 0.12 M€ |
| 2 | Bed manager + discharge room (dimissioni entro le 11, anche nel weekend) | -4.8% | -7.7% | 250 k€ | 0.37 M€ |
| 3 | +1 medico fascia 20-02 (unità 1) | -2.6% | -10.3% | 165 k€ | 0.54 M€ |
| 4 | +1 medico fascia 14-20 (unità 1) | -1.8% | -12.1% | 165 k€ | 0.70 M€ |
| 5 | Diagnostica dedicata al PS H24 (TAC + refertazione) | -6.2% | -18.3% | 600 k€ | 1.30 M€ |
| 6 | +1 medico fascia 14-20 (unità 2) | -0.7% | -19.0% | 165 k€ | 1.47 M€ |
| 7 | +1 medico fascia 08-14 | -0.8% | -19.8% | 165 k€ | 1.63 M€ |
| 8 | +1 medico fascia 20-02 (unità 2) | -0.3% | -20.0% | 165 k€ | 1.79 M€ |
| 9 | +1 medico fascia 02-08 | -0.3% | -20.3% | 165 k€ | 1.96 M€ |
| 10 | Fast track codici 4-5 (medico + infermiere, 8-20) | -0.7% | -21.1% | 475 k€ | 2.44 M€ |
| 11 | +10 letti di area medica (unità 1) | -1.8% | -22.9% | 2.190 k€ | 4.62 M€ |
| 12 | +10 letti di area medica (unità 2) | -1.0% | -23.9% | 2.190 k€ | 6.82 M€ |
| 13 | +10 letti di area medica (unità 3) | -0.7% | -24.6% | 2.190 k€ | 9.01 M€ |

Obiettivo NON raggiunto con le leve disponibili: -24.6%. Permanenza 11.4h → 8.6h, attesa visita 72′ → 5′, >24h 15.8% → 13.7%, tempo oltre 83 presenti 100% → 77%.

## 5. Quando, nella giornata: +1 medico per 2 ore

| Fascia | Effetto su attesa visita | Effetto su permanenza |
|---|---|---|
| 14-16 | -19.0% | -1.0% |
| 16-18 | -18.3% | -0.9% |
| 22-00 | -15.8% | -1.5% |
| 06-08 | -15.1% | -0.9% |
| 18-20 | -14.9% | -0.5% |
| 04-06 | -14.7% | -1.4% |
| 12-14 | -12.9% | -0.6% |
| 00-02 | -12.8% | -0.7% |
| 10-12 | -11.8% | -0.8% |
| 20-22 | -11.8% | -1.2% |
| 02-04 | -9.8% | -0.8% |
| 08-10 | -6.9% | +0.1% |

## 6. Quando, negli anni: crescita accessi per codice (media 2022-2025: cod. 1 +0.9%, cod. 2 +1.8%, cod. 3 +1.6%, cod. 4 +5.4%, cod. 5 +18.3%)

| Anno | Accessi | Senza interventi (letti invariati) | Con il mix, letti invariati | Con il mix + letti in proporzione ai ricoveri |
|---|---|---|---|---|
| 2026 | 101.584 | 11.8h (boarding 18h, +3.7%) | 8.5h (boarding 4h, -25.8%) | 8.5h (boarding 3h, -26.0%) |
| 2027 | 106.640 | 12.7h (boarding 27h, +10.9%) | 8.3h (boarding 4h, -27.5%) | 8.2h (boarding 3h, -27.9%) |
| 2028 | 112.247 | 15.4h (boarding 60h, +35.2%) | 8.2h (boarding 4h, -28.3%) | 8.1h (boarding 3h, -29.0%) |
| 2029 | 118.492 | **instabile** (code in crescita) | 8.0h (boarding 5h, -29.8%) | 7.9h (boarding 3h, -30.8%) |
| 2030 | 125.477 | **instabile** (code in crescita) | 7.8h (boarding 5h, -31.4%) | 7.7h (boarding 3h, -32.7%) |

Tra parentesi: attesa media di boarding e variazione della metrica rispetto al 2025.

## Avvertenze

- Costi ed effetti delle leve di tipo *processo* e *fast track* sono ipotesi (vedi `leve.yaml`): il modello dice cosa succede SE l'ipotesi è vera.
- Il boarding ufficiale (ASL) conta solo l'attesa dopo la decisione di ricovero. Parte delle permanenze lunghe nel 'processo' (OBI, attese di consulenze e posti letto prima della disposizione) potrebbe essere boarding non dichiarato: in quel caso le leve sui letti valgono più di quanto stimato qui.
- I dati ASL sono medie annue; le presenze misurate coprono solo l'autunno 2026 e non distinguono giorni feriali/festivi nel modello.

_Tempo di calcolo: 1090s._