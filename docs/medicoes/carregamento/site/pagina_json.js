window.pagina = async (id) => {
  const t = performance.now();
  const r = await fetch(`/json/${id}.json`); const d = await r.json();
  const m = document.getElementById('m'); m.textContent = '';
  const h = document.createElement('h1'); h.textContent = `${d.nome} (${d.uf})`; m.append(h);
  for (const [nome, linhas] of Object.entries({ ...d.sih, ...d.caged })) {
    if (!Array.isArray(linhas)) continue;
    const tab = document.createElement('table'); tab.createCaption().textContent = nome;
    for (const l of linhas) { const tr = tab.insertRow(); for (const v of l) tr.insertCell().textContent = v === null ? '<5' : v; }
    m.append(tab);
  }
  await new Promise(requestAnimationFrame);
  return { ms: performance.now() - t, celulas: m.querySelectorAll('td').length };
};
