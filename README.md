# Nova Assinaturas — protótipo de loja

Loja responsiva de demonstração para catálogo de assinaturas, quantidade por produto, carrinho e painel de pedidos/estoque. O catálogo é fictício. Checkout não cobra, não entrega assinatura, não reserva nem reduz estoque real.

## Deploy na Vercel

O repositório está preparado para o runtime Python da Vercel com FastAPI. Antes do primeiro deploy, configure no projeto da Vercel (Project Settings → Environment Variables) estas variáveis:

- `DATABASE_URL` — conexão de um PostgreSQL persistente. Para Supabase/serverless, use a connection string do *shared pooler, transaction mode*; mantenha SSL habilitado (`sslmode=require`). A tabela `demo_orders` é criada automaticamente.
- `ADMIN_USER` — usuário para abrir `/admin`.
- `ADMIN_PASSWORD` — senha forte e aleatória com pelo menos 16 caracteres. O painel e as rotas administrativas usam autenticação HTTP Basic; o navegador pedirá usuário e senha.
- `DEMO_CHECKOUT_ENABLED` — opcional; deixe ausente ou `false` por padrão. Use `true` somente para testar pedidos demo. Isso não ativa cobrança nem entrega real.

Defina as variáveis pelo painel seguro da Vercel, nunca no Git nem no chat. Sem `DATABASE_URL`, catálogo e loja abrem, mas criar/listar pedidos retorna indisponível. Sem `DEMO_CHECKOUT_ENABLED=true`, o POST de pedidos demo permanece fechado mesmo que o banco esteja configurado. Sem credenciais de admin válidas, `/admin` fica bloqueado. `DATABASE_URL` não é necessário para construir o deploy, mas é necessário para pedidos persistentes.

Passos:

1. Na Vercel, importe `EduardoKainan/vendasassinaturas` como projeto novo, mantendo a raiz do projeto no repositório (`/`).
2. Adicione as três variáveis obrigatórias acima no ambiente Production antes de concluir o deploy. Mantenha `DEMO_CHECKOUT_ENABLED` ausente/`false` até querer testar pedidos demo. Use valores separados para Preview se for habilitar previews.
3. Faça o deploy. A dependência FastAPI em `requirements.txt` permite à Vercel detectar a aplicação; `app.py` exporta a variável ASGI `app`, e `.python-version` seleciona Python 3.12. A configuração `vercel.json` fica sem mapeamentos manuais de funções.
4. Valide `https://SEU-DOMINIO/api/health` (`database_configured` e `admin_auth_configured` devem ser `true`), abra a loja e teste `/admin` com as credenciais configuradas. `database_configured` só confirma que a variável está definida; para confirmar a conexão real, faça um pedido demo e veja se aparece no painel.

O painel usa HTTP Basic, não um sistema de contas/recuperação de senha; use senha longa e mantenha o HTTPS da Vercel. `.env.example` contém somente campos vazios como referência. Não use credenciais reais nele.

## Rodar localmente

Requer Python 3.11+; o servidor de demonstração usa somente a biblioteca padrão:

```bash
python3 store_app.py
```

Acesse `http://127.0.0.1:8767/` (loja) e `http://127.0.0.1:8767/admin` (painel local). O servidor local escuta somente em `127.0.0.1`; não exponha por túnel ou rede. No Vercel, a rota `/admin` é protegida pelo HTTP Basic do `app.py`.

## Endpoints do deploy

- `GET /` — loja.
- `GET /api/products` — catálogo fictício.
- `POST /api/orders` — registra pedido demo no PostgreSQL; exige `DATABASE_URL`.
- `GET /admin`, `GET /api/admin/orders`, `GET /api/admin/dashboard` — protegidos por HTTP Basic no deploy.
- `GET /api/health` — informa configuração presente, sem revelar valores secretos.

Pedidos continuam marcados como `demo_pending` e `fulfilled: false`. A persistência PostgreSQL é para manter pedidos de teste entre execuções serverless, não habilita venda real.

## Integração do fornecedor

A interface de backend define `CatalogProvider.list_products()` e usa `DemoCatalogProvider` enquanto a API real não está documentada. A integração deve substituir esse adaptador e normalizar a resposta para o contrato-alvo abaixo. **Esse formato é ilustrativo: a versão atual aceita somente o catálogo demo e ainda não chama o fornecedor.**

```json
{
  "mode": "supplier",
  "is_demo": false,
  "currency": "BRL",
  "products": [
    {
      "id": "supplier-id",
      "name": "Nome retornado pelo fornecedor",
      "category": "Categoria",
      "duration_days": 30,
      "description": "Descrição",
      "price_cents": 2990,
      "stock": 12,
      "active": true,
      "featured": false,
      "badge": "30 dias"
    }
  ]
}
```

Para conectar de verdade, ainda preciso da documentação sem segredo: URL base, autenticação exigida, endpoints de produtos/estoque, paginação, limites, exemplos de sucesso/erro e regra para reservar/entregar. A chave deve entrar em variável de ambiente no backend — nunca em HTML, JavaScript ou chat.

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
