# sistema-correcao-cpe

Correção automática de provas por OMR (Optical Mark Recognition) e dashboards de
desempenho para professores. O sistema lê folhas de resposta escaneadas, corrige
contra o gabarito, guarda tudo em um banco de dados e mostra o desempenho por
aluno, turma, área e ao longo do tempo.

## Arquitetura

Três camadas, com fronteiras claras:

```
┌─────────────┐      HTTP/JSON      ┌──────────────────────────────┐
│   front/    │ ──────────────────> │            back/             │
│  Streamlit  │                     │                              │
│  (UI fina)  │ <────────────────── │  api/     FastAPI (HTTP)     │
└─────────────┘   long-format rows  │  grading/ pipeline OMR +     │
                                    │           ingestão           │
                                    │  data/    SQLAlchemy + banco │
                                    │  src/     motor OMR (core)   │
                                    └────────────────┬─────────────┘
                                                     │
                                              ┌──────┴───────┐
                                              │  Banco de    │
                                              │  dados       │
                                              │ (SQLite /    │
                                              │  PostgreSQL) │
                                              └──────────────┘
``

- **`front/`** — aplicativo Streamlit voltado ao professor. Não acessa o banco
  direto: fala com o backend pela API HTTP. Contém os quatro gráficos de sempre
  (desempenho por área, por subárea, taxa de acerto por questão, ranking por
  aluno) mais a aba de evolução da turma no tempo.
- **`back/api/`** — serviço FastAPI. Expõe correção, resultados em formato longo
  e as respostas para as perguntas dos professores.
- **`back/grading/`** — roda o pipeline OMR sobre as imagens e transforma a
  planilha `ResultsByQuestion` em registros do banco.
- **`back/data/`** — modelos SQLAlchemy, sessão e camada de repositório
  (reutilizável pela API e por scripts). Migrações via Alembic.
- **`back/src/`** — o motor OMR (fork do OMRChecker), praticamente intocado.

### Modelo de dados

Relacional. As entidades: `Class` (turma) → `Student`; `Exam` (simulado, com data
e sequência para o eixo do tempo) → `Question` (carrega o gabarito + área/subárea)
e `Sheet` (a prova de um aluno) → `Answer` (o que o aluno marcou + veredito
correct/incorrect/unmarked). O gabarito mora junto das questões, não em um CSV.

As perguntas frequentes dos professores viram consultas diretas:

| Pergunta | Endpoint |
| --- | --- |
| Desempenho de um aluno numa área | `GET /performance/student-subject` |
| Desempenho de um aluno num simulado | `GET /performance/student-exam` |
| Desempenho da turma num simulado | `GET /performance/class-exam` |
| A turma está melhorando com o tempo? | `GET /trends/class/{class_id}` |

## Como rodar

Pré-requisitos: Python 3.9+ e o stack do OMRChecker (OpenCV etc.) para a correção
de imagens. Ver `back/README.md` para as dependências de sistema do OpenCV.

O backend e o frontend são serviços separados e cada um usa seu próprio ambiente
virtual (eles pedem versões incompatíveis de `starlette`, então não compartilham
o mesmo venv). Os exemplos usam [`uv`](https://docs.astral.sh/uv/); com o `venv`
padrão do Python funciona igual (`python3 -m venv .venv` + `pip install`), desde
que o pacote `python3-venv` esteja instalado.

### 1. Backend (API + banco)

```bash
cd back
uv venv .venv                       # cria o ambiente isolado (sem mexer no Python do sistema)
source .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt

# Cria/atualiza o banco. Sem CPE_DATABASE_URL, usa um SQLite local (back/cpe_omr.db)
alembic upgrade head

# Sobe a API em http://localhost:8001 (porta padrão do projeto)
python -m api.app
# ou, escolhendo a porta explicitamente:
#   uvicorn api.app:app --reload --port 8001
```

Para usar PostgreSQL em vez de SQLite, basta apontar a variável de ambiente antes
de rodar o Alembic e o uvicorn (nenhuma mudança de código):

```bash
export CPE_DATABASE_URL="postgresql+psycopg://user:senha@host:5432/cpe"
```

### 2. Frontend (Streamlit)

Em outro terminal, com seu próprio ambiente:

```bash
cd front
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt

# A API padrão é http://localhost:8001. Se usar outra, informe aqui:
#   export CPE_API_URL="http://localhost:8001"

streamlit run app.py
```

No app: aba **Correção** para enviar o gabarito e as imagens das provas; aba
**Dashboard** para o desempenho do simulado escolhido; aba **Evolução** para
acompanhar a turma ao longo dos simulados; aba **Dados e downloads** para as
tabelas e exportações.

## Variáveis de ambiente

| Variável | Onde | Padrão | Para quê |
| --- | --- | --- | --- |
| `CPE_DATABASE_URL` | back | `sqlite:///back/cpe_omr.db` | Conexão do banco (troque para PostgreSQL sem mexer no código) |
| `CPE_API_HOST` | back | `127.0.0.1` | Host em que a API escuta (`python -m api.app`) |
| `CPE_API_PORT` | back | `8001` | Porta em que a API escuta (`python -m api.app`) |
| `CPE_API_URL` | front | `http://localhost:8001` | URL do backend que o Streamlit consome |

## Testes

Com cada venv ativado (ver acima):

```bash
# Backend (dados, grading, api)
cd back && python -m pytest data/tests grading/tests api/tests

# Frontend (gráficos + app)
cd front && python -m pytest tests

# Suite do motor OMR (precisa do stack OpenCV)
cd back && python -m pytest src/tests
```

> As amostras em `src/tests/test_all_samples.py` comparam a saída do pipeline com
> snapshots gravados numa combinação específica de OpenCV/numpy e são sensíveis a
> mudanças de versão. Como o repositório não versiona um lockfile, elas podem
> divergir fora do ambiente de CI original. As suítes `data/`, `grading/`, `api/`
> e `front/` não dependem disso.

## Migrações do banco

O schema é gerenciado **exclusivamente** pelo Alembic. A API nunca cria tabelas
sozinha, então `alembic upgrade head` é sempre a forma de preparar o banco.

```bash
cd back
alembic upgrade head                         # aplica as migrações
alembic revision --autogenerate -m "mudança" # gera uma nova após editar data/models.py
alembic downgrade -1                          # desfaz a última
```

### "table ... already exists" ao rodar upgrade

Se você tem um banco criado por uma versão antiga (quando a API ainda criava as
tabelas na inicialização), ele tem as tabelas mas a `alembic_version` vazia.
Marque-o como já migrado uma única vez e siga normalmente:

```bash
alembic stamp head
alembic upgrade head
```
