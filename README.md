# Nova Assinaturas — protótipo de loja

Loja responsiva para catálogo de assinaturas e painel demo. Sem credenciais do fornecedor, exibe catálogo fictício; com um adaptador configurado, pode exibir o catálogo real em modo somente leitura, com categorias, capas e valores convertidos para BRL. Nenhum checkout real, compra, cobrança, reserva ou entrega está habilitado.

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
- `GET /api/products` — catálogo normalizado pelo adaptador ativo; atualmente Canboso em modo somente leitura quando `CANBOSO_BUYER_KEY` estiver configurada, senão catálogo fictício.
- `POST /api/orders` — registra pedido demo no PostgreSQL; exige `DATABASE_URL`.
- `GET /admin`, `GET /api/admin/orders`, `GET /api/admin/dashboard` — protegidos por HTTP Basic no deploy.
- `GET /api/health` — informa configuração presente, sem revelar valores secretos.

Pedidos continuam marcados como `demo_pending` e `fulfilled: false`. A persistência PostgreSQL é para manter pedidos de teste entre execuções serverless, não habilita venda real.

## Catálogo e apresentação independente do fornecedor

`CanbosoCatalogProvider` é apenas o adaptador atual. Ele converte a resposta da Canboso para um contrato comum (`id`, `name`, `description`, `price_amount`, `price_currency`, `stock`, categoria opcional, `cover_image` e `emoji`). Um próximo fornecedor precisa apenas de um adaptador que implemente `CatalogProvider.list_products()` nesse formato e seja conectado em `create_app`; a vitrine, os filtros, as capas e a conversão continuam iguais.

A camada `enrich_catalog_for_storefront()` aplica categorias úteis quando o fornecedor não as informa e calcula `price_brl_cents` com `FrankfurterRateProvider`. A taxa diária vem de `https://api.frankfurter.dev/v2/rate/{moeda}/brl`, sem chave de API; a data da referência aparece na loja. Os centavos são arredondados para o mais próximo, com metade para cima. Os valores exibidos são apenas a conversão do preço recebido, sem margem ou taxa adicional. Se a cotação falhar ou a moeda não for suportada, o preço daquele produto fica indisponível — nunca mostramos um valor estrangeiro rotulado como R$.

A vitrine usa a imagem/emoji do fornecedor quando disponíveis. Sem imagem, gera uma capa gráfica por categoria; os filtros são montados a partir das categorias presentes no catálogo. A interface não depende de nomes, campos ou endpoints específicos da Canboso.

No adaptador Canboso, `availability.available` é normalizado para `stock`. Se a API devolver `null`, a loja mostra “Estoque não informado” em vez de inventar zero. Há cache em memória de 20 segundos por instância para reduzir chamadas; a Vercel pode iniciar várias instâncias, então o cache não é global nem garante consistência entre elas. As taxas de câmbio também têm cache em memória por seis horas. Respostas 429 passam o `Retry-After` ao cliente, sem tentativas automáticas em loop.

Quando a chave está configurada, a vitrine mostra produtos reais, oculta carrinho e checkout demo e informa que o catálogo é somente leitura. Nenhuma compra, reserva, cobrança ou entrega é executada. Sem chave, a vitrine permanece no catálogo fictício. A tela administrativa de pedidos continua sendo apenas demo.

Configure a chave no painel da Vercel: **Project → Settings → Environment Variables**. Nome: `CANBOSO_BUYER_KEY`; cole o valor no campo *Value*, marque *Production* (e *Preview* se for usar previews), salve e faça *Redeploy*. Não coloque a chave no GitHub, em `.env.example`, no código do frontend nem no chat.

> A chave buyer é usada somente no backend para consultar o catálogo. A API de compra não é chamada por esta integração; preços em BRL são referência convertida sem margem, não preço final de venda.

## Pagamento e produção

Checkout real permanece desativado. Antes de vender de verdade, ainda faltam: fluxo seguro de compra/entrega ao fornecedor, provedor de pagamento, confirmação assíncrona/webhook, regra de reembolso, controles administrativos e política de reserva/reconciliação do estoque. A compra/entrega ao fornecedor só deve ocorrer após a confirmação definida no fluxo de pagamento. Este deploy é apenas demo.

## Testes

Para os testes que exercitam o app Vercel, instale dependências numa virtualenv:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Checagens adicionais:

```bash
python3 -m py_compile app.py canboso_catalog.py storefront_catalog.py postgres_store.py store_app.py tests/*.py
node --check web/store.js
node --check web/admin.js
```

## Arquivos principais

- `app.py` — aplicação FastAPI para Vercel, rotas públicas e autenticação do painel.
- `storefront_catalog.py` — contrato de adaptadores, categorias, capas temáticas e conversão de moeda para BRL.
- `canboso_catalog.py` — adaptador read-only atual da Canboso.
- `postgres_store.py` — persistência de pedidos demo em PostgreSQL.
- `store_app.py` — servidor local e regras comuns de catálogo/pedidos.
- `vercel.json`, `requirements.txt`, `.python-version` — configuração de deploy.
- `data/demo_products.json` — catálogo totalmente fictício.
- `web/` — loja e painel responsivos.
- `tests/` — testes de regras locais, API local e aplicação Vercel.
