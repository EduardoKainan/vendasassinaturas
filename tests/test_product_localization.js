const test = require("node:test");
const assert = require("node:assert/strict");
const { applyProductLocale } = require("../web/product-locale.js");

test("localizes approved cards, preserves explicitly unchanged source copy, and suppresses unknown listings", () => {
  const products = [
    { id: "translated", name: "Source title", description: "Original source text" },
    { id: "unchanged", name: "Supplier title", description: "Supplier description" },
    { id: "blocked", name: "Hidden listing", description: "Sensitive source instructions" },
    { id: "untranslated", name: "A title in English", description: "English details" },
  ];
  const result = applyProductLocale(products, {
    locale: "pt-BR",
    hidden_product_ids: ["blocked"],
    unchanged_product_ids: ["unchanged"],
    translations: {
      translated: { name: "Título traduzido", description: "Descrição traduzida" },
    },
  });

  assert.deepEqual(result.products.map((product) => product.id), ["translated", "unchanged"]);
  assert.equal(result.products[0].display_name, "Título traduzido");
  assert.equal(result.products[0].display_description, "Descrição traduzida");
  assert.equal(result.products[0].name, "Source title");
  assert.equal(result.products[0].description, "Original source text");
  assert.equal(result.products[1].display_name, "Supplier title");
  assert.equal(result.products[1].display_description, "Supplier description");
  assert.equal(result.hidden_count, 1);
  assert.equal(result.unchanged_count, 1);
  assert.equal(result.untranslated_count, 1);
  assert.equal(products[0].display_name, undefined);
});

test("rejects translation data for another locale", () => {
  assert.throws(() => applyProductLocale([], { locale: "en-US", translations: {} }), /pt-BR/);
});
