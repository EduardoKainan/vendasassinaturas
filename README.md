# Nova Assinaturas — protótipo local

Loja responsiva de demonstração para catálogo de assinaturas, quantidade por produto, carrinho e painel de pedidos/estoque. A interface usa um catálogo fictício e registra pedidos apenas em SQLite local para validar o fluxo.

## Rodar

Requer Python 3.11+; não usa dependências externas.

```bash
python3 store_app.py
```

Acesse:

- Loja: http://127.0.0.1:8767/
- Painel local: http://127.0.0.1:8767/admin
- Saúde: http://127.0.0.1:8767/api/health

O servidor escuta somente em `127.0.0.1`. O painel administrativo desta versão não tem autenticação; **não exponha, publique em túnel ou implante na internet**. A base `data/orders-demo.sqlite3` é local e fica fora do ZIP.

## O que funciona nesta demo

- Lista os produtos fictícios de `data/demo_products.json`, com duração, preço e unidades disponíveis.
- Busca, ordenação, seleção de quantidades, carrinho e total em centavos.
- `POST /api/orders` valida produto, estoque, quantidade e chave de idempotência.
- Pedidos de demonstração ficam salvos em SQLite e aparecem em `/admin`.
- Pedido demo não cobra, não entrega e não reserva nem reduz estoque.
- O painel separa produtos, unidades de estoque e pedidos de demonstração.

Os preços e saldos são inventados para testar a interface — não representam oferta real.

## Integração do fornecedor

A interface de backend define `CatalogProvider.list_products()` e usa `DemoCatalogProvider` enquanto a API real não está documentada. A integração deve substituir esse adaptador e normalizar a resposta para o contrato-alvo abaixo. **Esse formato é ilustrativo: a versão atual aceita somente o catálogo demo e ainda não chama o fornecedor.** Ao receber a documentação, implemento e valido o adaptador de verdade.

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

Para conectar de verdade, preciso da documentação sem segredo: URL base, autenticação exigida, endpoints de produtos/estoque, paginação, limites, exemplos de sucesso/erro e regra para reservar/entregar. A chave deve entrar depois em variável de ambiente no backend — nunca em HTML, JavaScript ou chat.

## Pagamento e produção

Checkout real está intencionalmente desativado. Antes de vender de verdade, ainda faltam: provedor de pagamento, confirmação assíncrona/webhook, regra de reembolso, autenticação administrativa, banco persistente de produção e política de reserva/reconciliação do estoque do fornecedor. A compra/entrega ao fornecedor só deve ocorrer após a confirmação definida no fluxo de pagamento.

## Testes

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile store_app.py tests/test_store.py tests/test_http_api.py
node --check web/store.js
node --check web/admin.js
```

## Arquivos principais

- `store_app.py` — API local, validação de pedidos e persistência demo.
- `data/demo_products.json` — catálogo totalmente fictício.
- `web/index.html` — loja pública de demonstração.
- `web/admin.html` — painel local de pedidos e estoque.
- `web/app.css` — layout responsivo.
- `web/store.js`, `web/admin.js` — interações do navegador.
- `tests/` — testes de validação, persistência, idempotência e fluxo HTTP.
