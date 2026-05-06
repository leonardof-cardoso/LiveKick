# LiveKick (Futebol24hrs)

Bot de Discord 24/7 focado em **futebol brasileiro e europeu**, otimizado para
rodar com **pouco consumo de RAM/CPU** em hospedagem como o **Discloud**.

Cobertura: **Brasileirão Série A**, **Libertadores**, **Sul-Americana** e
**UEFA Champions League**.

## Recursos

| Comando            | Descrição                                                       |
|--------------------|------------------------------------------------------------------|
| `!jogos`           | Jogos do dia (todas as competições monitoradas)                  |
| `!aovivo`          | Apenas partidas em andamento agora                               |
| `!proximos`        | Próximos jogos (até 7 dias)                                      |
| `!tabela <comp>`   | Classificação. Ex: `!tabela brasileirao`, `!tabela champions`    |
| `!noticias [busca]`| Notícias recentes (Google News RSS + GE)                         |
| `!time <nome>`     | Próximos jogos, últimos resultados, posição na tabela            |
| `!ondeassistir A x B` | Onde assistir (TV / streaming)                                |
| `!setalerts #canal`| Define o canal para alertas automáticos                          |
| `!alerts`          | Mostra o canal de alertas atual                                  |
| `!favoritos`       | Lista, adiciona ou remove times favoritos                        |

Equivalentes em **slash commands** também são registrados (`/jogos`, `/aovivo`,
`/proximos`, `/tabela`, `/noticias`, `/time`).

### Alertas automáticos
O bot envia automaticamente no canal configurado:
- 🟢 **Início** da partida
- ⚽ **Gols**
- ⏸️ **Intervalo**
- ⏹️ **Fim de jogo**

Os alertas são **deduplicados em SQLite** para nunca repetirem.

## Tecnologias

- **Python 3.11+**
- [`discord.py`](https://github.com/Rapptz/discord.py) – cliente Discord
- [`APScheduler`](https://apscheduler.readthedocs.io/) – agendamento assíncrono
- [`httpx`](https://www.python-httpx.org/) – cliente HTTP async com pooling
- [`aiosqlite`](https://aiosqlite.omnilib.dev/) – SQLite async (cache)
- [`feedparser`](https://feedparser.readthedocs.io/) – RSS
- `asyncio` puro – sem Selenium, sem navegador, sem deps pesadas

## APIs gratuitas usadas

- [Football-Data.org](https://www.football-data.org/) (com chave gratuita)
- [TheSportsDB](https://www.thesportsdb.com/) (sem chave – fallback)
- Google News RSS + globoesporte.globo.com RSS

## Estrutura

```
.
├── main.py                # entrypoint
├── config.py              # variaveis de ambiente, competicoes, RSS
├── discloud.config        # config do Discloud
├── requirements.txt       # dependencias
├── Dockerfile             # build alternativo
├── .env.example           # template de variaveis
├── .discloudignore        # arquivos ignorados pelo upload
├── .gitignore
├── README.md
├── cogs/
│   ├── matches.py         # !jogos, !aovivo, !proximos, !ondeassistir
│   ├── news.py            # !noticias
│   ├── standings.py       # !tabela
│   ├── alerts.py          # alertas automaticos + !setalerts
│   └── teams.py           # !time, !favoritos
├── services/
│   ├── football_service.py
│   ├── news_service.py
│   ├── standings_service.py
│   └── broadcast_service.py
├── database/
│   ├── db.py              # SQLite WAL + cache + dedupe alertas
│   └── models.py
├── cache/                 # criado em runtime (SQLite + cache)
├── logs/                  # criado em runtime (rotativo, 512KB x 2)
└── utils/
    └── helpers.py
```

## Configuração local

```bash
git clone https://github.com/leonardof-cardoso/LiveKick.git
cd LiveKick

python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux/Mac

pip install -r requirements.txt

copy .env.example .env            # Windows
# cp .env.example .env            # Linux/Mac
# preencha DISCORD_TOKEN e FOOTBALL_API_KEY

python main.py
```

### Variáveis de ambiente (.env)

```env
DISCORD_TOKEN=seu_token_aqui
FOOTBALL_API_KEY=sua_chave_football_data
COMMAND_PREFIX=!
TIMEZONE=America/Sao_Paulo
LOG_LEVEL=INFO
LIVE_INTERVAL_MIN=2
NEWS_INTERVAL_MIN=15
STANDINGS_INTERVAL_MIN=60
EMBED_COLOR=0x00A859
```

### Como obter o token do Discord

1. Acesse https://discord.com/developers/applications
2. **New Application** → dê um nome (ex: Futebol24hrs)
3. Aba **Bot** → **Reset Token** → copie em `DISCORD_TOKEN`
4. Em **Privileged Gateway Intents**, ative **MESSAGE CONTENT INTENT**
5. Aba **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissões: `Send Messages`, `Embed Links`, `Read Message History`,
     `View Channels`, `Use Slash Commands`
6. Copie a URL gerada e use para convidar o bot ao seu servidor.

### Como obter a Football-Data API Key

1. Acesse https://www.football-data.org/client/register
2. Cadastre-se com seu e-mail (plano gratuito serve)
3. Cole a chave em `FOOTBALL_API_KEY`

> Sem essa chave o bot continua funcionando — apenas usa o TheSportsDB como
> fonte única e tabela de classificação fica indisponível para Brasileirão e
> Champions.

## Deploy no Discloud

> O Discloud roda apps Python 24h com recursos limitados.
> O `discloud.config` na raiz do projeto:
>
> ```ini
> NAME=LiveKick
> MAIN=main.py
> TYPE=bot
> RAM=100
> VERSION=latest
> APT=tools
> ```

### 1. Preparar o ZIP

Na raiz do projeto, selecione **todo o conteúdo** e zipe (o `discloud.config`
deve ficar na raiz do ZIP):

- `main.py`, `config.py`
- `cogs/`, `services/`, `database/`, `utils/`
- `requirements.txt`
- `discloud.config`, `.discloudignore`
- `.env`  ← já com seus tokens preenchidos (ou configure pela aba ENV depois)

No Windows (PowerShell), na raiz do projeto:

```powershell
Compress-Archive -Path * -DestinationPath ..\livekick.zip -Force
```

### 2. Subir no Discloud

Pelo painel web:
1. Acesse https://discloud.com → faça login
2. **Upload** → selecione `futebol24.zip`
3. Confirme: o painel lerá o `discloud.config` e iniciará o bot.

Pelo bot oficial do Discloud no Discord:
```
.up
```
e anexe o ZIP na mensagem.

### 3. Configurar variáveis (alternativa ao .env no zip)

No painel do Discloud:
- App → **ENV** → adicione `DISCORD_TOKEN`, `FOOTBALL_API_KEY`, etc.
- Salve e reinicie a aplicação.

### 4. Verificar logs

```
.logs <ID_DA_APP>
```
ou pelo painel web → aba **Logs**.

## Otimizações para uptime contínuo

- Cliente HTTP **httpx.AsyncClient** único, com pool de conexões e keep-alive.
- **Cache em SQLite** com TTL para fixtures (10 min), live (90s), tabela (1h),
  notícias (10 min) — evita rate limit das APIs.
- **WAL** habilitado no SQLite (`journal_mode=WAL`) para escrita não bloqueante.
- Rotação de logs em **512KB x 2 backups** — sem inflar disco.
- **Reconnect automático** do Discord (`reconnect=True`) + retry com
  backoff exponencial caso o login falhe por queda de rede.
- Tratamento explícito de **timeout, rate limit (429) e erros 5xx** —
  o bot **continua rodando mesmo se uma API cair**.
- APScheduler com `coalesce=True` e `max_instances=1`, evitando jobs sobrepostos.
- Limpeza periódica de alertas antigos (>7 dias) e cache expirado.
- Sem Selenium, sem Chromium, sem deps nativas pesadas → cabe em 100MB de RAM.

## Solução de problemas

- **Bot conecta mas não responde a comandos**: verifique se `MESSAGE CONTENT
  INTENT` está habilitado no Developer Portal.
- **Slash commands não aparecem**: aguarde alguns minutos ou use `/` em outro
  servidor — o sync global pode levar até 1h. Para testes locais, force sync
  por guild.
- **Tabela do Brasileirão / Champions vazia**: confira a `FOOTBALL_API_KEY`.
- **Notícias vazias**: pode ser bloqueio temporário do Google News — o cache
  de 10 min já mitiga, mas tente novamente.

## Licença

Uso livre, sem garantia. As fontes (Football-Data, TheSportsDB, Google News,
GE) têm termos próprios — respeite-os.
