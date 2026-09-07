# Plano Geral — Corte Político (Clipador)

SaaS que transforma um vídeo bruto (link do YouTube ou upload) em clipes curtos verticais (9:16) e clipes longos horizontais (16:9), com corte automático, thumbnail, título, descrição e hashtags gerados por IA.

Este documento é a fundação arquitetural do projeto: stack, infraestrutura AWS, fluxo de dados, modelo de cobrança e roadmap. Decisões aqui têm precedência sobre suposições feitas durante a implementação; quando um ponto ainda estiver em aberto, está marcado explicitamente na seção 10.

---

## 1. Visão geral do produto

1. Usuário loga (Cognito).
2. Usuário cola um link do YouTube **ou** faz upload de um vídeo bruto.
3. Usuário escolhe parâmetros do job (idioma, quantidade de clipes, formatos desejados — curto 9:16, longo 16:9, ou ambos).
4. Sistema reserva créditos, enfileira o job.
5. O engine (pipeline Python já existente em `engine/`) baixa/lê o vídeo, transcreve, seleciona os melhores trechos, reenquadra, gera legendas, thumbnail e metadados (título/descrição/hashtags via LLM).
6. Clipes prontos aparecem no dashboard do usuário para preview e download.
7. Créditos usados são debitados de acordo com o consumo real (duração processada / clipes gerados).

---

## 2. Arquitetura geral

```
                              ┌─────────────────────┐
                              │   Amazon Route 53      │
                              │  DNS (cortepolitico.com.br) │
                              └──────────┬────────────┘
                                         │
              ┌──────────────────────────┼───────────────────────────┐
              │                                                       │
   ┌──────────▼───────────┐                              ┌───────────▼───────────┐
   │   AWS Amplify Hosting  │                              │   EC2 — Backend API    │
   │   Frontend Angular      │◄──── HTTPS REST ───────────►│   NestJS 11 + Nginx     │
   └──────────────────────┘                              └───────────┬───────────┘
                                                                       │
                       ┌───────────────────────────────────────────────┼──────────────────────────────┐
                       │                                               │                                │
             ┌─────────▼─────────┐                         ┌───────────▼───────────┐        ┌───────────▼───────────┐
             │   Amazon RDS         │                         │  Amazon SQS (fila)      │        │  Amazon Cognito         │
             │   PostgreSQL          │                         │  jobs de clipagem       │        │  User Pool (auth)        │
             └────────────────────┘                         └───────────┬───────────┘        └────────────────────────┘
                                                                          │
                                                              ┌───────────▼───────────┐
                                                              │  EC2 — Engine Worker    │
                                                              │  (GPU, g4dn.xlarge)     │
                                                              │  pipeline clipador       │
                                                              └───────────┬───────────┘
                                                                          │
                                                              ┌───────────▼───────────┐
                                                              │  Amazon S3               │
                                                              │  raw uploads / clipes /  │
                                                              │  thumbnails               │
                                                              └────────────────────────┘

   ┌────────────────────────┐          ┌──────────────────────────┐
   │  Mercado Pago             │◄────────►│  Backend (webhook IPN)     │
   │  Checkout Pro (créditos)  │          │  credita ledger de usuário │
   └────────────────────────┘          └──────────────────────────┘

   ┌────────────────────────┐
   │  AWS Secrets Manager      │  chaves: DB, Cognito, Mercado Pago, Anthropic, YouTube API, AssemblyAI
   └────────────────────────┘
```

Duas EC2 separadas por design (decisão do usuário): uma para o **backend** (leve, sempre ligada, barata) e outra para o **engine** (GPU, cara, só precisa estar de pé processando jobs). Isso permite escalar/desligar o engine independente do backend no futuro sem tocar na API.

---

## 3. Stack por componente

| Componente | Tecnologia | Observação |
|---|---|---|
| Frontend | Angular (standalone components) | Já com esqueleto em `frontend/`, hospedado via AWS Amplify |
| Backend | NestJS 11 + TypeORM + PostgreSQL | Já com esqueleto em `backend/` |
| Engine | Python (pipeline já construído) | `engine/`: download, transcribe, select, reframe, subtitles, thumbnail, export, metadata/LLM |
| Banco | Amazon RDS PostgreSQL (single-AZ pra começar) | `db.t3.micro`/`small` |
| Fila de jobs | Amazon SQS (standard queue) | Desacopla backend do engine, com DLQ pra jobs que falham repetido |
| Storage de vídeo/clipes | Amazon S3 | Buckets separados: raw uploads, saídas, thumbnails |
| Auth | Amazon Cognito User Pool | UI de login/cadastro própria (Design System do Clipador), sem Hosted UI |
| Pagamentos | Mercado Pago Checkout Pro | Compra de créditos avulsos (pay-per-use) |
| Segredos | AWS Secrets Manager | Nenhum segredo local, nunca em `.env` de produção |
| DNS | Amazon Route 53 | Hosted zone pública, domínio `cortepolitico.com.br` registrado na Hostinger com nameservers apontando pro Route 53 |
| TLS backend (EC2) | Let's Encrypt via Certbot (plugin `dns-route53`) | ACM não anexa em EC2 puro sem ALB/CloudFront; Certbot com validação DNS na zona Route 53 resolve sem infra extra |
| TLS frontend (Amplify) | Gerenciado automaticamente pelo Amplify Hosting | Basta conectar o domínio custom via Route 53 |
| Compute backend | EC2 (ex: `t3.medium`) + Docker | Nginx como reverse proxy |
| Compute engine | EC2 GPU (ex: `g4dn.xlarge`, 1x T4) | Roda o worker que consome a fila SQS |

Sem API Gateway, sem ALB, sem Fargate no MVP — consciente da decisão de manter a infra simples. Migração pra Fargate/ALB é um passo natural quando o tráfego justificar, não uma dependência do dia 1.

---

## 4. Fluxo de dados detalhado

### 4.1 Ingestão do vídeo

- **Link do YouTube:** backend só grava a URL no job; é o engine (via `yt-dlp`, já em `engine/`) que baixa o vídeo no momento de processar. Nada de baixar no backend.
- **Upload de vídeo bruto:** frontend pede ao backend uma **presigned URL** do S3 (`PUT`, expira em minutos), sobe o arquivo direto pro bucket `clipador-raw-uploads`. O backend nunca recebe o binário — evita gargalo de memória/banda na EC2 do backend.

### 4.2 Criação e execução do job

1. `POST /jobs` no backend: valida créditos disponíveis (estimativa por duração/formatos pedidos), cria linha em `jobs` (status `queued`), grava reserva no ledger de créditos (`job_reserve`).
2. Backend publica mensagem na fila SQS com `jobId` + parâmetros (idioma, formatos, origem do vídeo).
3. Engine worker (processo Python de longa duração na EC2 GPU) faz polling da fila, pega a mensagem, roda o pipeline:
   `ingest → transcribe → select → reframe → subtitles → thumbnail → export → metadata (LLM)`.
4. Engine sobe as saídas (clipes `.mp4`, thumbnails `.jpg`) pro S3 (`clipador-outputs/{userId}/{jobId}/...`).
5. Engine chama um endpoint interno do backend (`PATCH /internal/jobs/:id`) informando conclusão, lista de clipes gerados e consumo real. O engine **nunca** escreve direto no Postgres — mantém o invariante "engine é caixa-preta pro backend".
6. Backend debita o consumo real do ledger (`job_consume`), libera o excedente da reserva (`job_refund` se a reserva foi maior que o gasto real), atualiza status do job (`done`/`failed`).
7. Se falhar: reserva inteira é revertida (`job_refund`), status vira `failed`, motivo do erro fica salvo pro usuário ver.

### 4.3 Consumo do resultado

- Frontend faz polling em `GET /jobs/:id` (ou lista em `GET /jobs`) até status terminal. WebSocket/SSE é um upgrade de UX pra fase 2, não bloqueia o MVP.
- Download/preview de clipe: backend gera presigned `GET` URL do S3 sob demanda, nunca expõe o bucket como público.

---

## 5. Autenticação (Cognito)

**Provisionado (2026-08-17):** User Pool `CortePoliticoUsers` (`us-east-2_DzKB1y9jV`), app client `corte-politico-web` (`6td1s52f2765mui06cbbkds338`, sem client secret, flows `ALLOW_USER_SRP_AUTH` + `ALLOW_REFRESH_TOKEN_AUTH` pro frontend, `ALLOW_ADMIN_USER_PASSWORD_AUTH` pra testes/admin via backend com credencial IAM).

- **User Pool** único, sem federação social no MVP (pode entrar depois: Google/Facebook são plug-and-play no Cognito).
- Frontend usa `amazon-cognito-identity-js` (ou só a camada de Auth do Amplify, não o framework inteiro) pra ter telas de login/cadastro com a cara do Design System do Clipador, em vez do Hosted UI genérico do Cognito.
- Fluxo: `USER_SRP_AUTH`, tokens JWT (id token + access token) guardados em memória/http-only cookie (a definir na fase de implementação, mas nunca em `localStorage` puro pra token sensível sem mitigação de XSS).
- Backend valida o JWT via `passport-jwt` + verificação de assinatura contra o JWKS do User Pool (guard global, com decorator `@Public()` pra rotas abertas, seguindo o mesmo padrão já batido em outros projetos do usuário).

---

## 6. Pagamentos e créditos (Mercado Pago)

- Modelo: **créditos avulsos**, sem assinatura recorrente no MVP.
- Pacotes de crédito fixos (ex: 10, 30, 100 créditos), preço em BRL, exibidos na tela de billing.
- Fluxo Checkout Pro:
  1. Usuário escolhe pacote → `POST /billing/checkout` → backend cria `preference` na API do Mercado Pago → retorna `init_point` → frontend redireciona.
  2. Usuário paga no Mercado Pago.
  3. Mercado Pago chama o **webhook (IPN)** do backend (`POST /billing/webhook/mercadopago`) avisando o pagamento.
  4. Backend confirma o pagamento consultando a API do Mercado Pago pelo `payment_id` (nunca confia cegamente no payload do webhook), credita o ledger (`purchase`) com **idempotência pelo `payment_id`** — reentrega do webhook não pode creditar duas vezes.
- **Ledger de créditos append-only** (`credit_ledger`): `id, user_id, delta, reason (purchase|job_reserve|job_consume|job_refund|admin_adjustment), reference_id, created_at`. Saldo do usuário é `SUM(delta)`, cacheado em `users.credit_balance` pra leitura rápida, mas o ledger é a fonte da verdade (permite auditoria e reconciliação, evita drift de saldo mutável direto).

---

## 7. Modelo de dados (alto nível)

Tabelas principais (refinar em migrations TypeORM quando começar a implementação):

- `users` — id, email, cognito_sub, credit_balance (cache), created_at
- `jobs` — id, user_id, status (`queued|processing|done|failed`), source_type (`youtube|upload`), source_ref (url ou s3 key), formats_requested, language, error_message, created_at, finished_at
- `clips` — id, job_id, format (`short_9x16|long_16x9`), s3_key_video, s3_key_thumbnail, title, description, hashtags, duration_seconds, created_at
- `credit_ledger` — id, user_id, delta, reason, reference_id, created_at
- `credit_packages` — id, name, credit_amount, price_brl, active

Regras de negócio (limites de duração, custo por minuto processado, quantidade de clipes por job) ficam em **código** (services/validators), não em `CHECK` constraint do banco — são política de produto que muda sem precisar de migration, conforme a convenção do projeto.

---

## 8. Segurança e segredos

- Todas as chaves (RDS, Cognito, Mercado Pago access token, Anthropic API key, YouTube Data API key, AssemblyAI) exclusivamente no **AWS Secrets Manager**, carregadas em runtime via `@nestjs/config` no backend e via variável de ambiente injetada (não commitada) no engine.
- **Provisionado (2026-08-17):** secret `corte-politico/backend-secrets` (placeholder, preencher via `aws secretsmanager put-secret-value` fora do chat) com `anthropicApiKey`, `youtubeApiKey`, `assemblyAiApiKey`, `mercadoPagoAccessToken`.
- Buckets S3 privados por padrão, acesso só via presigned URL com expiração curta.
- Webhook do Mercado Pago: validar assinatura/origem antes de processar (Mercado Pago assina o payload).
- Comunicação backend ↔ engine: mensagens SQS não carregam segredos, só referências (IDs, S3 keys).

---

## 9. Estimativa de custo mensal (ordem de grandeza, revisar antes de provisionar)

| Recurso | Instância/Tier | Custo aproximado (us-east-1) |
|---|---|---|
| EC2 backend | `t3.medium` on-demand | ~US$ 30/mês |
| EC2 engine (GPU) | `g4dn.xlarge` on-demand | ~US$ 380/mês se ligada 24/7 — considerar start/stop sob demanda ou spot na fase 2 |
| RDS PostgreSQL | `db.t3.micro` single-AZ | ~US$ 15/mês |
| S3 | pay-per-use | baixo no início, monitorar egress de download de clipes |
| SQS | pay-per-use | irrelevante em volume baixo |
| Amplify Hosting | build + hosting | baixo, tier gratuito cobre bastante |
| Cognito | até 50k MAU grátis | US$ 0 no início |
| Secrets Manager | por segredo | ~US$ 0,40/segredo/mês |

O item que mais pesa é a EC2 GPU ligada 24/7. Vale já nascer com um mecanismo simples de **start/stop automático** (ex: Lambda agendada ou o próprio backend ligando a instância antes de despachar job e desligando após fila vazia por X minutos) assim que o volume de jobs for baixo/irregular — não precisa ser dia 1, mas é o primeiro corte de custo óbvio.

---

## 10. Decisões em aberto (confirmar antes de implementar)

1. ~~**Conta AWS / profile / região**~~ — **Resolvido (2026-08-17).** Conta dedicada `229446391137` ("Corte Politico"), IAM Identity Center em `us-east-2`, profile CLI `CortePoliticoAdmin` (`aws sso login --profile CortePoliticoAdmin`), admin via SSO, root reservado pra recuperação de conta.
2. **Start/stop da EC2 GPU** — sempre ligada (mais simples, mais caro) vs. liga sob demanda (mais barato, mais lógica). Pode ficar "sempre ligada" no MVP e revisar depois.
3. ~~**Domínio**~~ — **Resolvido (2026-08-17).** `cortepolitico.com.br`, registrado na Hostinger, hosted zone pública criada no Route 53 (`Z0632079ZY10FTS83F50`), nameservers sendo trocados na Hostinger pros 4 NS do Route 53.
4. **Retenção de arquivos no S3** — por quanto tempo manter vídeo bruto e clipes gerados antes de expirar via lifecycle rule (custo de storage vs. usuário poder reprocessar).
5. **Limite de créditos por formato/duração** — regra de precificação (quantos créditos por minuto de vídeo, por clipe gerado) ainda não definida, fica pra fase de design de produto.
6. **Notificação de job concluído** — só polling no MVP, ou já entra email (SES) / push?

---

## 10.1 Ambiente de desenvolvimento local

Antes de provisionar RDS/EC2 (Fase 0 de infra), o desenvolvimento roda inteiramente local:

- `docker-compose.yml` na raiz sobe **Postgres** (porta `5433` no host, pra não colidir com outros projetos) e o **backend NestJS** (porta `3000`), com hot-reload via bind mount + `tsconfig.json` com `watchOptions` de polling (necessário no Docker Desktop/Windows, `fsevents` nativo não atravessa bind mount).
- O container do backend monta `~/.aws` (somente leitura) e usa `AWS_PROFILE=CortePoliticoAdmin`, então já acessa Cognito e Secrets Manager de verdade em dev local, sem duplicar segredo nenhum em `.env`. Exige `aws sso login --profile CortePoliticoAdmin` ativo no host (token expira, relogar quando necessário).
- **Frontend roda fora do Docker**, via `npm start` (`ng serve`) direto no terminal, como decidido pelo usuário.
- Subir: `docker compose up -d` (raiz do repo). Logs: `docker logs cortepolitico-backend -f`.

---

## 11. Roadmap por fases

### Fase 0 — Fundação (infra + esqueleto)
- Provisionar RDS, S3 (buckets), Cognito User Pool, Secrets Manager, as duas EC2 (backend e engine), SQS + DLQ.
- TypeORM configurado no backend com as entidades da seção 7 e primeira migration.
- Cognito plugado no backend (guard JWT) e no frontend (telas de login/cadastro com Design System).
- Deploy do frontend no Amplify (domínio custom via Route 53), backend rodando na EC2 atrás do Nginx com TLS via Certbot (`dns-route53`).

### Fase 1 — Job de clipagem ponta a ponta (MVP funcional)
- `POST /jobs` com link do YouTube (upload por presigned URL fica pra logo em seguida, mas pode entrar na mesma fase).
- Integração backend → SQS → engine worker → volta pro backend via endpoint interno.
- Dashboard simples: lista de jobs, status, preview/download de clipes prontos.
- Sem cobrança ainda: créditos infinitos/mock pra validar o pipeline de ponta a ponta.

### Fase 2 — Créditos e pagamento
- Ledger de créditos, telas de billing, integração Checkout Pro + webhook do Mercado Pago.
- Bloqueio de criação de job sem saldo suficiente.

### Fase 3 — Robustez e UX
- Retry/DLQ de jobs travados, mensagens de erro claras pro usuário.
- Upload de vídeo bruto via presigned URL (se não entrou na fase 1).
- Notificação por email (SES) de job concluído.
- Ajuste fino de custo: start/stop da EC2 GPU sob demanda.

### Fase 4 — Escala (só quando o volume pedir)
- Avaliar migração backend/engine pra ECS Fargate ou auto scaling group.
- Multi-AZ no RDS, cache (ElastiCache) se necessário.
- Métricas/observabilidade (CloudWatch dashboards, alarmes de fila presa, alarmes de custo).

---

## 12. Próximos passos imediatos

1. ~~Confirmar conta/perfil/região AWS e registrar na ai-memory.~~ Feito.
2. ~~Decidir o domínio.~~ Feito, `cortepolitico.com.br` no Route 53, propagação de nameservers em andamento.
3. Desenhar o schema de créditos (custo por minuto/formato) com o usuário.
4. Começar pela Fase 0: provisionar infra base via AWS CLI (nunca CDK/console manual), documentando cada comando.
