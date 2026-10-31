# Nova Assinaturas — protótipo de loja

Loja responsiva de demonstração para catálogo de assinaturas, quantidade por produto, carrinho e painel de pedidos/estoque. O catálogo é fictício. Checkout não cobra, não entrega assinatura, não reserva nem reduz estoque real.

## Deploy na Vercel

O repositório está preparado para o runtime Python da Vercel com FastAPI. Antes do primeiro deploy, configure no projeto da Vercel (Project Settings → Environment Variables) estas variáveis:

- `DATABASE_URL` — conexão de um PostgreSQL persistente. Para Supabase/serverless, use a connection string do *shared pooler, transaction mode*; mantenha SSL habilitado (`sslmode=require`). A tabela `demo_orders` é criada automaticamente.
- `ADMIN_USER` — usuário para abrir `/admin`.
- `ADMIN_PASSWORD` — senha forte e aleatória com pelo menos 16 caracteres. O painel e as rotas administrativas usam autenticação HTTP Basic; o navegador pedirá usuário e senha.
- `DEMO_CHECKOUT_ENABLED` — opcional; deixe ausente ou `false` por padrão. Use `true` somente para testar pedidos demo. Isso não ativa cobrança nem entrega real.
- `CANBOSO_BUYER_KEY` — opcional; chave buyer válida emitida pelo bot da Canboso. Quando presente, o catálogo público consulta produtos e disponibilidade pela API. A consulta é somente leitura; não compra produtos nem debita saldo.

Defina as variáveis pelo painel seguro da Vercel, nunca no Git nem no chat. Sem `DATABASE_URL`, catálogo e loja abrem, mas criar/listar pedidos retorna indisponível. Sem `DEMO_CHECKOUT_ENABLED=true`, o POST de pedidos demo permanece fechado mesmo que o banco esteja configurado. Sem credenciais de admin válidas, `/admin` fica bloqueado. Sem `CANBOSO_BUYER_KEY`, a loja usa o catálogo fictício. `DATABASE_URL` não é necessário para construir o deploy, mas é necessário para pedidos persistentes.

Passos:

1. Na Vercel, importe `EduardoKainan/vendasassinaturas` como projeto novo, mantendo a raiz do projeto no repositório (`/`).
2. Adicione as três variáveis obrigatórias acima no ambiente Production antes de concluir o deploy. Mantenha `DEMO_CHECKOUT_ENABLED` ausente/`false` até querer testar pedidos demo. Use valores separados para Preview se for habilitar previews.
3. Faça o deploy. `vercel.json` fixa o preset FastAPI; `app.py` exporta a variável ASGI `app`, e `.python-version` seleciona Python 3.12. Não há mapeamentos manuais de funções.
4. Valide `https://SEU-DOMINIO/api/health` (`database_configured` e `admin_auth_configured` devem ser `true`; `supplier_catalog_configured` informa apenas se a variável da Canboso está configurada), abra a loja e teste `/admin` com as credenciais configuradas. `database_configured` só confirma que a variável está definida; para confirmar a conexão real, faça um pedido demo e veja se aparece no painel.

O painel usa HTTP Basic, não um sistema de contas/recuperação de senha; use senha longa e mantenha o HTTPS da Vercel. `.env.example` contém somente campos vazios como referência. Não use credenciais reais nele.

## Rodar localmente

Requer Python 3.11+; o servidor de demonstração usa somente a biblioteca padrão:

```bash
python3 store_app.py
```

Acesse `http://127.0.0.1:8767/` (loja) e `http://127.0.0.1:8767/admin` (painel local). O servidor local escuta somente em `127.0.0.1`; não exponha por túnel ou rede. No Vercel, a rota `/admin` é protegida pelo HTTP Basic do `app.py`.

## Endpoints do deploy

- `GET /` — loja.
- `GET /api/products` — catálogo Canboso em modo somente leitura quando `CANBOSO_BUYER_KEY` estiver configurada; caso contrário, catálogo fictício.
- `POST /api/orders` — registra pedido demo no PostgreSQL; exige `DATABASE_URL`.
- `GET /admin`, `GET /api/admin/orders`, `GET /api/admin/dashboard` — protegidos por HTTP Basic no deploy.
- `GET /api/health` — informa configuração presente, sem revelar valores secretos.

Pedidos continuam marcados como `demo_pending` e `fulfilled: false`. A persistência PostgreSQL é para manter pedidos de teste entre execuções serverless, não habilita venda real.

## Catálogo Canboso (somente leitura)

Na aplicação FastAPI da Vercel, `GET /api/products` consulta `GET https://canboso.com/api/v2/telegram-buyer/products` usando `CANBOSO_BUYER_KEY` no backend. A chave nunca é enviada ao navegador nem incluída na resposta. O endpoint público da loja retorna apenas os campos do catálogo normalizados; preços mantêm a moeda informada pelo fornecedor, sem conversão para BRL.

A resposta pública inclui `availability.available` como estoque. Se a Canboso devolver `null`, a loja mostra “Estoque não informado” em vez de inventar zero. Há cache em memória de 20 segundos por instância para reduzir chamadas; a Vercel pode iniciar várias instâncias, então o cache não é global nem garante consistência entre elas. Respostas 429 passam o `Retry-After` ao cliente, sem tentativas automáticas em loop.

Quando a chave está configurada, a vitrine mostra os produtos Canboso, esconde carrinho e checkout demo e informa que o catálogo é somente leitura. Nenhuma compra, reserva, cobrança ou entrega é executada. Sem chave, a vitrine permanece no catálogo fictício. A tela administrativa de pedidos continua sendo apenas demo.

Configure a chave no painel da Vercel: **Project → Settings → Environment Variables**. Nome: `CANBOSO_BUYER_KEY`; cole o valor no campo *Value*, marque *Production* (e *Preview* se for usar previews), salve e faça *Redeploy*. Não coloque a chave no GitHub, em `.env.example`, no código do frontend nem no chat.

> A documentação descreve uma Buyer API com chave emitida por um bot Telegram. A leitura real só pode ser validada depois que uma chave válida for adicionada como variável secreta e o deployment atualizado. A API de compra não é chamada por esta integração.

## Pagamento e produção

Checkout real permanece desativado. Antes de vender de verdade, ainda faltam: API do fornecedor, provedor de pagamento, confirmação assíncrona/webhook, regra de reembolso, controles administrativos e política de reserva/reconciliação do estoque. A compra/entrega ao fornecedor só deve ocorrer após a confirmação definida no fluxo de pagamento. Este deploy é apenas demo.

## Testes

Para os testes que exercitam o app Vercel, instale dependências numa virtualenv:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Checagens adicionais:

```bash
python3 -m py_compile app.py postgres_store.py store_app.py tests/*.py
node --check web/store.js
node --check web/admin.js
```

## Arquivos principais

- `app.py` — aplicação FastAPI para Vercel, rotas públicas e autenticação do painel.
- `postgres_store.py` — persistência de pedidos demo em PostgreSQL.
- `store_app.py` — servidor local e regras comuns de catálogo/pedidos.
- `vercel.json`, `requirements.txt`, `.python-version` — configuração de deploy.
- `data/demo_products.json` — catálogo totalmente fictício.
- `web/` — loja e painel responsivos.
- `tests/` — testes de regras locais, API local e aplicação Vercel.
