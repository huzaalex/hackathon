# Cercetare: procesul real al popririlor

Barem: *„Înțelegerea & cercetarea problemei alese”*. Folosiți acest document ca listă de lucru și ca sursă pentru slide-uri.

## 1. De verificat în legislație

Valorile folosite de cod sunt toate în `services/rules-engine/app/legal_config.py`. Bifați fiecare rând după verificare și corectați fișierul dacă e nevoie.

| # | Ce verificăm | Unde | Ce folosește acum codul | Verificat |
|---|---|---|---|---|
| 1 | Limita de poprire din salariu pentru datorii obișnuite | C.proc.civ. art. 729 | 1/3 din venitul periodic | ☐ |
| 2 | Limita pentru pensie de întreținere | C.proc.civ. art. 729 | 1/2 | ☐ |
| 3 | Regim special când venitul e sub salariul minim | C.proc.civ. art. 729 | **neimplementat** | ☐ |
| 4 | Sume care nu pot fi poprite deloc (alocații, ajutoare sociale, indemnizații) | C.proc.civ. art. 729, 781 | alocație, ajutor social, indemnizație creștere copil | ☐ |
| 5 | Dacă limitele se aplică și sumelor din salariu deja virate în cont | C.proc.civ. art. 781 + practică bancară | da, pe încasările din ultimele 30 de zile | ☐ |
| 6 | Ordinea de preferință între creditori | C.proc.civ. art. 867 | întreținere (3) > fiscale (4) > chirografare (8) | ☐ |
| 7 | Creditori de același rang: FIFO sau proporțional? | C.proc.civ. art. 867 | FIFO | ☐ |
| 8 | Reguli specifice pentru popririle ANAF | Legea 207/2015 (Cod proc. fiscală), art. 236 | aceleași limite, rang 4 | ☐ |
| 9 | Termenul în care banca trebuie să răspundă emitentului | C.proc.civ. / Cod proc. fiscală | nu e modelat (SLA) | ☐ |
| 10 | Poprirea se extinde asupra sumelor viitoare? | C.proc.civ. art. 781 | da: reevaluare la fiecare încasare | ☐ |

## 2. Întrebări pentru cineva care lucrează într-o bancă (5 minute la telefon)

- Câte adrese de poprire primiți pe zi sau lună? Pe ce canale (poștă, e-mail, platforme electronice)?
- Cât durează procesarea unei adrese, în medie? Care e partea cea mai lentă?
- Ce greșeli apar cel mai des (omonimi, CNP greșit, sume exceptate blocate din greșeală)?
- Ce se întâmplă când o greșeală ajunge la client sau la executor (reclamații, amenzi, procese)?
- Ce sisteme folosiți azi (manual, semi-automat, OCR)?

Un singur citat real în prezentare valorează mult.

## 3. Structură propusă pentru prezentare (5–7 slide-uri)

1. **Problema:** un operator, o adresă de poprire, 8 pași manuali. Volum și costul unei greșeli (din interviu).
2. **De ce e grea:** formate diferite, scanări, omonimi, CNP-uri greșite, reguli legale cu excepții și priorități.
3. **Soluția:** echipa de agenți (diagrama din README), cu accent pe „LLM-ul decide, codul calculează”.
4. **Demo live** (vezi ordinea recomandată în README).
5. **Inginerie:** microservicii, Docker, teste la build, blackboard, human-in-the-loop, degradare controlată.
6. **Impact și pași următori:** timp economisit, audit complet al fiecărei decizii, integrare cu sistemele reale.
