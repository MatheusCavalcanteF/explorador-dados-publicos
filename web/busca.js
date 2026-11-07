// Busca por nome de município, sem acento e sem diferença de maiúsculas.
// "Santos SP" filtra pela UF. A lista só é baixada quando a pessoa começa a usar o campo.
(() => {
  const form = document.querySelector('.busca');
  const campo = document.getElementById('busca');
  const lista = document.getElementById('resultados');
  const aviso = document.getElementById('busca-aviso');
  if (!form || !campo || !lista || !aviso) return;
  form.hidden = false;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const primeiro = lista.querySelector('a');
    if (primeiro) primeiro.focus();
  });

  const normalizar = (texto) => texto.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();
  let municipios = null;
  let carregando = null;

  const carregar = () => {
    carregando ??= fetch('dados/municipios.json')
      .then((r) => {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then((dados) => {
        municipios = dados.map(([codigo, nome, uf]) => ({ codigo, nome, uf, chave: normalizar(nome) }));
      })
      .catch(() => {
        aviso.textContent = 'Não foi possível carregar a lista de municípios. Use a lista por estado abaixo.';
      });
    return carregando;
  };

  const mostrar = () => {
    if (!municipios) return;
    let consulta = normalizar(campo.value);
    let uf = null;
    const final = consulta.match(/^(.+?)[\s,/-]+([a-z]{2})$/);
    if (final) {
      [, consulta, uf] = final;
      uf = uf.toUpperCase();
    }
    lista.replaceChildren();
    if (consulta.length < 2) {
      aviso.textContent = '';
      return;
    }
    const candidatos = municipios.filter((m) => (!uf || m.uf === uf) && m.chave.includes(consulta));
    candidatos.sort((a, b) => (b.chave.startsWith(consulta) - a.chave.startsWith(consulta)) || a.chave.localeCompare(b.chave));
    for (const m of candidatos.slice(0, 20)) {
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.href = `municipio/${m.codigo}/`;
      const nome = document.createElement('span');
      nome.textContent = m.nome;
      const sigla = document.createElement('span');
      sigla.className = 'escudo';
      sigla.textContent = m.uf;
      link.append(nome, sigla);
      item.append(link);
      lista.append(item);
    }
    const total = candidatos.length;
    aviso.textContent = total === 0
      ? 'Nenhum município com esse nome. Confira a grafia ou procure na lista por estado.'
      : total > 20
        ? `${total} municípios encontrados. Mostrando os 20 primeiros; digite mais letras para refinar.`
        : `${total} ${total === 1 ? 'município encontrado' : 'municípios encontrados'}.`;
  };

  campo.addEventListener('focus', carregar, { once: true });
  campo.addEventListener('input', () => carregar().then(mostrar));
})();
