(function registerProductLocale(root) {
  function applyProductLocale(products, localeData) {
    if (!localeData || localeData.locale !== "pt-BR") {
      throw new Error("Arquivo de tradução pt-BR ausente ou inválido.");
    }
    if (!Array.isArray(products) || !localeData.translations || typeof localeData.translations !== "object") {
      throw new Error("Formato das traduções pt-BR inválido.");
    }

    const hiddenIds = new Set((localeData.hidden_product_ids || []).map(String));
    const unchangedIds = new Set((localeData.unchanged_product_ids || []).map(String));
    const output = [];
    let hiddenCount = 0;
    let unchangedCount = 0;
    let untranslatedCount = 0;

    for (const product of products) {
      const id = String(product?.id ?? "");
      if (!id || hiddenIds.has(id)) {
        hiddenCount += 1;
        continue;
      }
      if (unchangedIds.has(id)) {
        output.push({
          ...product,
          display_name: String(product.name ?? ""),
          display_description: String(product.description ?? ""),
          display_badge: "",
        });
        unchangedCount += 1;
        continue;
      }
      const translation = localeData.translations[id];
      if (!translation || typeof translation.name !== "string" || !translation.name.trim()
        || typeof translation.description !== "string" || !translation.description.trim()) {
        untranslatedCount += 1;
        continue;
      }
      output.push({
        ...product,
        display_name: translation.name.trim(),
        display_description: translation.description.trim(),
        display_badge: typeof translation.badge === "string" ? translation.badge.trim() : "",
      });
    }
    return { products: output, hidden_count: hiddenCount, unchanged_count: unchangedCount, untranslated_count: untranslatedCount };
  }

  root.NovaProductLocale = { applyProductLocale };
  if (typeof module !== "undefined" && module.exports) module.exports = { applyProductLocale };
})(typeof window !== "undefined" ? window : globalThis);
