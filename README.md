# Poprire Agent

**Procesarea autonomă a adreselor de poprire într-o bancă** · Hackathon „Agenți AI în Servicii Bancare” · Direcția 2: *AI for Operational Efficiency*

Băncile primesc zilnic adrese de poprire de la executori judecătorești, ANAF și primării, ca PDF-uri în formate diferite, uneori scanate. Azi, un operator le citește manual, caută debitorul, calculează ce sume au voie să fie blocate (alocațiile sunt protejate, din salariu se ia doar o fracție, unele datorii au prioritate), blochează banii și răspunde emitentului.

**Poprire Agent** face acest lucru cu o echipă de agenți AI coordonată de un supervizor. Calculele legale sunt făcute de un motor de reguli determinist, iar un operator uman intervine doar când agentul nu e sigur.

---

## Arhitectura

```
                      ┌────────────────────────────┐
                      │  Dashboard (React, :3000)  │  upload, trace live (SSE), coadă operator
                      └─────────────┬──────────────┘
                                    │ /api  (nginx → orchestrator)
                      ┌─────────────▼──────────────┐
                      │   ORCHESTRATOR (:8000)     │  Claude Opus 5.5 pe Amazon Bedrock
                      │   Supervizor  ─┬─ Citire   │  tool calling, buclă agentică proprie,
                      │                ├─ Identif. │  pauză/reluare pentru operator uman,
                      │                ├─ Juridic  │  blackboard partajat între agenți
                      │                └─ Acțiune  │
                      └──┬─────────┬─────────┬─────┬┘
          ┌──────────────▼─┐ ┌─────▼──────┐ ┌▼──────────┐ ┌▼───────────┐
          │ core-banking   │ │ rules-     │ │ document- │ │ fx-service │
          │ (:8001)        │ │ engine     │ │ service   │ │ (:8004)    │
          │ clienți,conturi│ │ (:8002)    │ │ (:8003)   │ │ curs BNR   │
          │ popriri,blocări│ │ CNP, alocare│ │ PDF→text/ │ │ real + cache│
          │ PostgreSQL     │ │ legală     │ │ imagine,  │ │ + fallback │
          └───────┬────────┘ │ + teste    │ │ scrisori  │ └────────────┘
                  │ webhook  └────────────┘ └───────────┘
                  └──► orchestrator: „a intrat salariul unui debitor” → caz nou, automat
```

### Principii de design (de prezentat juriului)

1. **LLM-ul decide, codul calculează.** Agenții citesc documente dezordonate, investighează și aleg pașii. Sumele vin doar din `rules-engine`, un cod determinist acoperit de teste care rulează la build. Core banking-ul își face propriile verificări (nu poți bloca mai mult decât soldul), indiferent ce decide AI-ul.
2. **Planificare dinamică, nu pipeline fix.** Supervizorul decide ce agent lucrează și când: sare peste citire la evenimente, repetă identificarea după răspunsul operatorului, se oprește la duplicate.
3. **Blackboard.** Agenții nu își copiază cifre între ei prin text. Uneltele citesc și scriu în starea comună a cazului, deci LLM-ul nu poate „transcrie greșit” o sumă.
4. **Human-in-the-loop real.** Când identificarea e ambiguă, cazul intră în pauză, apare în dashboard cu opțiuni, iar răspunsul operatorului reia exact conversația agentului.
5. **Reactiv la evenimente.** Poprirea rămâne activă pe încasări viitoare. Când intră salariul, core banking-ul notifică orchestratorul, iar agentul recalculează singur blocările.
6. **Degradare controlată.** BNR indisponibil → cache → curs static marcat clar. PDF scanat → citire vizuală. Eroare de unealtă → agentul primește eroarea și se adaptează. Refuz al modelului → model de rezervă.

---

## Pornire rapidă

**Cerințe:** doar [Docker Desktop](https://www.docker.com/products/docker-desktop/). Python și Node rulează în containere.

```bash
# 1. Cheia: copiați .env.example în .env și completați BEDROCK_API_KEY (dacă nu există deja)
# 2. Porniți tot sistemul
docker compose up --build

# 3. Deschideți dashboard-ul
#    http://localhost:3000
```

Verificarea conexiunii cu LLM-ul (în alt terminal, utilă la primul start):

```bash
docker compose run --rm orchestrator python -m app.check_llm
```

La fiecare `docker compose up`, `data-generator` regenerează datele sintetice în `./data`, iar core banking-ul pornește din starea inițială. Butonul **Reset demo** din dashboard face același lucru fără restart.

### Servicii și porturi

| Serviciu | Port | Documentație API (Swagger) |
|---|---|---|
| Dashboard | 3000 | – |
| Orchestrator | 8000 | http://localhost:8000/docs |
| Core banking | 8001 | http://localhost:8001/docs |
| Rules engine | 8002 | http://localhost:8002/docs |
| Document service | 8003 | http://localhost:8003/docs |
| FX service | 8004 | http://localhost:8004/docs |

---

## Scenarii de demo

Le găsiți în dashboard, în stânga, cu butonul ▶. PDF-urile sunt în `./data/popriri/`.

| # | Scenariu | Ce demonstrează |
|---|---|---|
| 01 | Poprire simplă de la executor | Fluxul complet, scrisoare de confirmare |
| 02 | ANAF, CNP greșit cu o cifră | Cifra de control CNP → corecții → găsește clientul corect |
| 03 | Salariu + alocație | Alocația protejată, max. 1/3 din salariu, blocare parțială |
| 04 | Pensie alimentară peste o poprire ANAF | Prioritate între creditori, recalcularea tuturor blocărilor |
| 05 | Omonimi „Andrei Popa” | **Pauză pentru operator uman** și reluare |
| 06 | Ridicare de poprire | Alt tip de document → alt flux (deblocare) |
| 07 | Debitorul nu e client | Răspuns „nu deține conturi” |
| 08 | Primărie, cont în EUR | Curs BNR real, conversie |
| 09 | Fonduri insuficiente | Blocare parțială, apoi **Simulează încasare** salariu → agentul se reactivează singur |
| 10 | Document scanat | Fără strat de text → citire vizuală (imagine) |
| 11 | Duplicat primit pe e-mail | Rulați-l după 01: nu blochează de două ori |

**Ordine recomandată la stand (~5 minute):** 01 → 03 → 05 (răspundeți ca operator) → 09 + simulare salariu → 10. Țineți deschis tab-ul „Client & conturi” ca să se vadă cum se schimbă blocările.

---

## Structura repo-ului

```
├── docker-compose.yml
├── .env.example               # configurare LLM (cheia reală stă în .env, ignorat de git)
├── data-generator/            # date sintetice: clienți, conturi, tranzacții, PDF-uri de poprire
├── services/
│   ├── orchestrator/app/
│   │   ├── agents.py          # supervizor + 4 agenți: prompturi, unelte, scheme de rezultat
│   │   ├── runtime.py         # bucla agentică: tool calling, validare, pauză pentru operator
│   │   ├── workflow.py        # coada de cazuri și worker-ul
│   │   ├── main.py            # API + SSE + webhook
│   │   ├── llm.py             # clientul Anthropic SDK → Claude în Amazon Bedrock
│   │   └── check_llm.py
│   ├── core-banking/app/      # banca simulată (FastAPI + SQLAlchemy + PostgreSQL)
│   ├── rules-engine/
│   │   ├── app/legal_config.py # ← parametrii legali, într-un singur loc
│   │   ├── app/allocation.py  # alocarea sumelor între popriri
│   │   ├── app/cnp.py         # validare CNP + sugestii de corecție
│   │   └── tests/             # rulează la `docker compose build`
│   ├── document-service/app/  # PDF → text / imagini; generarea scrisorilor de răspuns
│   └── fx-service/app/        # curs BNR cu cache și fallback
├── dashboard/                 # React + Vite + TypeScript, servit de nginx
└── docs/research.md           # ce trebuie verificat juridic + întrebări pentru bancheri
```

## Lucru în echipă (24h)

| Cine | Zonă | Fișiere principale |
|---|---|---|
| A | Agenți și prompturi, tuning pe scenarii | `services/orchestrator/app/agents.py`, `runtime.py` |
| B | Reguli legale, teste, cercetare juridică | `services/rules-engine/`, `docs/research.md` |
| C | Date sintetice, scenarii noi, documente | `data-generator/`, `services/document-service/` |
| D | Dashboard, demo, prezentare | `dashboard/`, `README.md` |

Contractele dintre servicii sunt API-uri HTTP documentate automat la `/docs`, deci fiecare zonă se poate modifica independent.

**Dezvoltare frontend fără rebuild Docker:** cu Node 20 instalat, rulați `cd dashboard && npm install && npm run dev` (http://localhost:5173, proxy `/api` către orchestratorul din Docker).

**Rularea unui singur serviciu după modificări:** `docker compose up --build orchestrator`.

## Limitări cunoscute și pași următori

- Regulile legale sunt un **model simplificat** (vezi `legal_config.py` și `docs/research.md`) și trebuie verificate.
- Cazurile și trace-ul stau în memoria orchestratorului: un restart al orchestratorului le pierde. Pas următor: persistarea în PostgreSQL ca jurnal de audit.
- Core banking-ul se resetează la fiecare pornire, intenționat, pentru un demo reproductibil.
- Nu există autentificare pe dashboard (prototip local).
