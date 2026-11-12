// Internações na página do município. Os gráficos são desenhados aqui, a partir das tabelas da página, na
// largura disponível e com texto de 12 px; a tabela continua sendo a forma acessível dos mesmos valores.
// Também: troca de ano, dica nas marcas e exportação para CSV e PNG. Sem este script, a página tem as
// tabelas completas e os anos do detalhe um abaixo do outro.
(function () {
  "use strict";
  var secao = document.querySelector(".sih");
  if (!secao) return;
  var SVG = "http://www.w3.org/2000/svg";
  var FONTE = 12;
  var OCULTO = "oculto", ARREDONDADO = "preliminar, arredondado", NAO_PUBLICADO = "não publicado";
  var listras = 0;

  function numero(n) { return Math.round(n).toLocaleString("pt-BR"); }

  function el(nome, atributos, pai, texto) {
    var e = document.createElementNS(SVG, nome);
    for (var k in atributos) e.setAttribute(k, atributos[k]);
    if (texto != null) e.textContent = texto;
    if (pai) pai.appendChild(e);
    return e;
  }

  // Valor e situação de uma célula da tabela: oculta não tem valor.
  function celula(td) {
    var v = td.getAttribute("data-v");
    return { v: v === "" ? null : Number(v), s: td.getAttribute("data-s") || "" };
  }

  function dica(rotulo, c) {
    return rotulo + ": " + (c.v === null ? OCULTO : numero(c.v)) + (c.s ? " (" + c.s + ")" : "");
  }

  // Topo e marcas do eixo em números redondos.
  function escala(maximo) {
    if (maximo <= 0) return { topo: 5, marcas: [0, 5] };
    var bruto = maximo / 4, potencia = Math.pow(10, Math.floor(Math.log10(bruto)));
    var passo = [1, 2, 2.5, 5, 10].map(function (p) { return p * potencia; }).find(function (p) { return p >= bruto; });
    passo = Math.max(1, Math.round(passo));
    var topo = passo * Math.ceil(maximo / passo), marcas = [];
    for (var m = 0; m <= topo; m += passo) marcas.push(m);
    return { topo: topo, marcas: marcas };
  }

  function marcaEixo(n) { return n < 10000 ? numero(n) : (n / 1000).toLocaleString("pt-BR") + " mil"; }

  // Cada gráfico leva o próprio padrão de listras: o preliminar é a barra na cor cheia da série, com listras
  // a 45 graus na cor do fundo por cima. A cor cheia mantém o contraste de 3:1 com o fundo nos dois temas, e
  // as listras distinguem o preliminar do exato sem depender de cor.
  function svgNovo(largura, altura) {
    var svg = el("svg", { viewBox: "0 0 " + largura + " " + altura, width: largura, height: altura, "aria-hidden": "true",
      class: "grafico" });
    var id = "listras-" + (++listras);
    var padrao = el("pattern", { id: id, patternUnits: "userSpaceOnUse", width: 5, height: 5, patternTransform: "rotate(45)" },
      el("defs", {}, svg));
    el("rect", { class: "listra", x: 0, y: 0, width: 2, height: 5 }, padrao);
    svg.dataset.listras = id;
    return svg;
  }

  // Marca de preliminar: o mesmo desenho da barra, coberto pelas listras.
  function marcar(svg, forma, atributos, serie) {
    el(forma, Object.assign({}, atributos, { class: "hachura", fill: "url(#" + svg.dataset.listras + ")",
      stroke: "var(--" + (serie || "serie") + ")" }), svg);
  }

  // Coluna com o canto de cima arredondado, crescendo da linha de base.
  function coluna(pai, x, base, largura, altura, prelim, texto) {
    var r = Math.min(4, largura / 2, altura);
    var d = "M" + x + "," + base + "v" + (-(altura - r)) + "q0," + (-r) + " " + r + "," + (-r) +
      "h" + (largura - 2 * r) + "q" + r + ",0 " + r + "," + r + "v" + (altura - r) + "z";
    el("path", { class: "barra", "data-tip": texto, d: d }, pai);
    if (prelim) marcar(pai, "path", { d: d, "data-tip": texto });
  }

  function anel(pai, x, y, raio, texto) {
    el("circle", { class: "oculta", cx: x, cy: y, r: raio, "data-tip": texto }, pai);
  }

  function colunas(caixa, tabela) {
    var linhas = tabela.querySelectorAll("tbody tr");
    var pontos = Array.prototype.map.call(linhas, function (tr) {
      var c = celula(tr.cells[1]);
      c.rotulo = tr.cells[0].textContent.trim();
      c.mes = Number(tr.cells[0].getAttribute("data-v"));
      c.prelim = tr.hasAttribute("data-p");
      return c;
    });
    var W = Math.floor(caixa.getBoundingClientRect().width), H = 230, esq = 44, dir = 4, topo = 22, base = H - 24;
    var passo = (W - esq - dir) / Math.max(pontos.length, 1);
    var largura = Math.max(1, Math.min(24, passo - 2));
    var maximo = Math.max.apply(null, pontos.map(function (p) { return p.v || 0; }));
    var e = escala(maximo), y = function (v) { return base - (base - topo) * v / e.topo; };
    var svg = svgNovo(W, H);
    e.marcas.forEach(function (m) {
      el("line", { class: "grade", x1: esq, x2: W - dir, y1: y(m), y2: y(m) }, svg);
      el("text", { class: "eixo", x: esq - 6, y: y(m) + 4, "text-anchor": "end" }, svg, marcaEixo(m));
    });
    var prelim = pontos.map(function (p, i) { return p.prelim ? i : -1; }).filter(function (i) { return i >= 0; });
    if (prelim.length) {
      var x0 = esq + prelim[0] * passo, x1 = esq + (prelim[prelim.length - 1] + 1) * passo;
      el("rect", { class: "faixa", x: x0, y: topo - 16, width: x1 - x0, height: base - topo + 16 }, svg);
      var rot = el("text", { class: "eixo", x: x1 - 4, y: topo - 4, "text-anchor": "end" }, svg, "preliminar");
      if (x1 - x0 < 70) rot.setAttribute("x", x1);
    }
    var raio = Math.max(2, Math.min(4, (passo - 1) / 2));
    var anos = pontos.filter(function (p) { return p.mes % 100 === 1; }).length;
    var cada = passo * 12 < 34 ? 2 : 1, contados = 0;
    pontos.forEach(function (p, i) {
      var x = esq + i * passo + (passo - largura) / 2;
      // Mês de cruzamento não publicado no ano fica sem marca: não é célula oculta, e a tabela diz por quê.
      if (p.v === null && p.s !== NAO_PUBLICADO) anel(svg, x + largura / 2, base - raio - 1, raio, dica(p.rotulo, p));
      else if (p.v > 0) coluna(svg, x, base, largura, base - y(p.v), p.s === ARREDONDADO, dica(p.rotulo, p));
      if (p.mes % 100 === 1 && (contados++ % cada === 0 || anos === 1)) {
        el("text", { class: "eixo", x: esq + i * passo, y: base + 17 }, svg, String(Math.floor(p.mes / 100)));
      }
    });
    el("line", { class: "base", x1: esq, x2: W - dir, y1: base, y2: base }, svg);
    return svg;
  }

  function barras(caixa, tabela) {
    var itens = Array.prototype.map.call(tabela.querySelectorAll("tbody tr"), function (tr) {
      var c = celula(tr.cells[1]);
      c.rotulo = tr.cells[0].getAttribute("data-curto") || tr.cells[0].textContent.trim();
      return c;
    });
    var W = Math.floor(caixa.getBoundingClientRect().width), estreito = W < 520, esq = estreito ? 0 : 168, valor = 56;
    var linha = estreito ? 40 : 24, H = linha * itens.length + 6;
    var maximo = Math.max.apply(null, itens.map(function (i) { return i.v || 0; })) || 1;
    var util = W - esq - valor, svg = svgNovo(W, H);
    itens.forEach(function (item, k) {
      var y = 4 + k * linha, yBarra = estreito ? y + 18 : y + 3;
      el("text", { class: "rotulo", x: estreito ? 0 : esq - 8, y: estreito ? y + 13 : y + 15, "text-anchor": estreito ? "start" : "end" },
        svg, item.rotulo);
      if (item.v === null) {
        anel(svg, esq + 5, yBarra + 8, 4, dica(item.rotulo, item));
        el("text", { class: "valor", x: esq + 16, y: yBarra + 12 }, svg, OCULTO);
        return;
      }
      var w = item.v ? Math.max(1, util * item.v / maximo) : 0;
      if (w) {
        var r = Math.min(4, w);
        var d = "M" + esq + "," + yBarra + "h" + (w - r) + "q" + r + ",0 " + r + "," + r + "v" + (16 - 2 * r) + "q0," + r + " " + (-r) + "," + r +
          "h" + (-(w - r)) + "z";
        el("path", { class: "barra", "data-tip": dica(item.rotulo, item), d: d }, svg);
        if (item.s === ARREDONDADO) marcar(svg, "path", { d: d, "data-tip": dica(item.rotulo, item) });
      }
      el("text", { class: "valor", x: esq + w + 6, y: yBarra + 12 }, svg, numero(item.v));
    });
    if (!estreito) el("line", { class: "base", x1: esq + 0.5, x2: esq + 0.5, y1: 2, y2: H - 2 }, svg);
    return svg;
  }

  function piramide(caixa, tabela) {
    var cab = tabela.querySelectorAll("thead th"), col = {};
    Array.prototype.forEach.call(cab, function (th, i) { if (th.dataset.serie) col[th.dataset.serie] = i; });
    var linhas = Array.prototype.map.call(tabela.querySelectorAll("tbody tr"), function (tr) {
      return { faixa: tr.cells[0].textContent.trim(), M: celula(tr.cells[col.M]), F: celula(tr.cells[col.F]) };
    });
    var W = Math.floor(caixa.getBoundingClientRect().width), calha = W < 520 ? 106 : 124, meio = W / 2, linha = 22, topo = 30;
    var H = topo + linha * linhas.length + 4, util = meio - calha / 2 - 4, svg = svgNovo(W, H);
    var maximo = Math.max.apply(null, linhas.map(function (l) { return Math.max(l.M.v || 0, l.F.v || 0); })) || 1;
    el("rect", { class: "serie-1", x: meio - calha / 2 - 84, y: 6, width: 10, height: 10, rx: 2 }, svg);
    el("text", { class: "rotulo", x: meio - calha / 2 - 70, y: 15 }, svg, "Masculino");
    el("rect", { class: "serie-2", x: meio + calha / 2 + 4, y: 6, width: 10, height: 10, rx: 2 }, svg);
    el("text", { class: "rotulo", x: meio + calha / 2 + 18, y: 15 }, svg, "Feminino");
    linhas.forEach(function (l, k) {
      var y = topo + k * linha;
      el("text", { class: "eixo", x: meio, y: y + 14, "text-anchor": "middle" }, svg, l.faixa);
      [[l.M, -1, "serie-1", "masculino"], [l.F, 1, "serie-2", "feminino"]].forEach(function (lado) {
        var c = lado[0], sentido = lado[1], inicio = meio + sentido * calha / 2;
        var texto = dica(l.faixa + ", " + lado[3], c);
        if (c.v === null) { anel(svg, inicio + sentido * 6, y + 10, 4, texto); return; }
        var w = c.v ? util * c.v / maximo : 0;
        if (!w) return;
        var caixa = { x: sentido > 0 ? inicio : inicio - w, y: y + 3, width: w, height: 15, rx: 3, "data-tip": texto };
        el("rect", Object.assign({ class: lado[2] }, caixa), svg);
        if (c.s === ARREDONDADO) marcar(svg, "rect", caixa, lado[2]);
      });
    });
    return svg;
  }

  var DESENHOS = { colunas: colunas, barras: barras, piramide: piramide };

  function desenhar() {
    Array.prototype.forEach.call(secao.querySelectorAll(".grafico-sih"), function (caixa) {
      if (!caixa.offsetParent) return;   // escondido (outro ano, detalhe fechado): desenha quando aparecer
      var largura = Math.floor(caixa.getBoundingClientRect().width);
      if (caixa.dataset.largura === String(largura)) return;
      caixa.dataset.largura = largura;
      var svg = DESENHOS[caixa.dataset.tipo](caixa, document.getElementById(caixa.dataset.tabela));
      caixa.replaceChildren(svg);
    });
  }

  var botoes = secao.querySelectorAll(".exportar");
  for (var i = 0; i < botoes.length; i++) botoes[i].hidden = false;

  // Ano dos painéis de diagnóstico, idade e sexo.
  var anos = secao.querySelector("fieldset.anos");
  if (anos) {
    anos.hidden = false;
    var mostrar = function () {
      var marcado = anos.querySelector("input:checked");
      var paineis = secao.querySelectorAll(".painel");
      for (var j = 0; j < paineis.length; j++) paineis[j].hidden = paineis[j].dataset.ano !== marcado.value;
      desenhar();
    };
    anos.addEventListener("change", mostrar);
    mostrar();
  }
  desenhar();
  secao.addEventListener("toggle", desenhar, true);
  var espera;
  window.addEventListener("resize", function () { clearTimeout(espera); espera = setTimeout(desenhar, 150); });

  // Dica: o valor primeiro, depois a situação. O texto entra por textContent.
  var balao = document.createElement("div");
  balao.className = "dica";
  balao.hidden = true;
  document.body.appendChild(balao);
  secao.addEventListener("pointermove", function (e) {
    var alvo = e.target.closest && e.target.closest("[data-tip]");
    if (!alvo) { balao.hidden = true; return; }
    balao.textContent = alvo.getAttribute("data-tip");
    balao.hidden = false;
    var x = Math.min(e.clientX + 14, window.innerWidth - balao.offsetWidth - 8);
    balao.style.left = Math.max(8, x) + "px";
    balao.style.top = (e.clientY + 16) + "px";
  });
  secao.addEventListener("pointerleave", function () { balao.hidden = true; });

  function baixar(nome, blob) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  function campo(texto) {
    texto = String(texto == null ? "" : texto);
    return /[";\n]/.test(texto) ? '"' + texto.replace(/"/g, '""') + '"' : texto;
  }

  // CSV em formato longo: uma linha por valor, com a situação dele e a fonte em todas as linhas.
  function csv(tabela) {
    var cabecalho = [];
    var ths = tabela.querySelectorAll("thead th");
    for (var c = 0; c < ths.length; c++) cabecalho.push(ths[c].textContent.trim());
    var linhas = [["municipio", "codigo_ibge", "tabela", "linha", "coluna", "valor", "situacao", "fonte", "acesso", "coleta", "ressalva"]];
    var trs = tabela.querySelectorAll("tbody tr");
    for (var r = 0; r < trs.length; r++) {
      var celulas = trs[r].children;
      var rotulo = celulas[0].getAttribute("data-v") || celulas[0].textContent.trim();
      for (var k = 1; k < celulas.length; k++) {
        if (!celulas[k].hasAttribute("data-v")) continue;
        var situacao = celulas[k].getAttribute("data-s") || "exato", motivo = celulas[k].getAttribute("data-motivo");
        if (motivo) situacao += ": " + motivo;
        linhas.push([secao.dataset.municipio, secao.dataset.codigo, tabela.dataset.csvNome, rotulo, cabecalho[k],
          celulas[k].getAttribute("data-v"), situacao,
          secao.dataset.fonte, secao.dataset.acesso, secao.dataset.coleta, secao.dataset.ressalva]);
      }
    }
    return "﻿" + linhas.map(function (l) { return l.map(campo).join(";"); }).join("\r\n") + "\r\n";
  }

  var PROPS = ["fill", "fill-opacity", "stroke", "stroke-width", "opacity", "font-size", "font-family", "font-weight"];

  // A hachura aponta para o padrão do próprio gráfico pelo atributo fill: o estilo copiado não o substitui.
  function estiloInline(original, copia) {
    var estilo = getComputedStyle(original), inline = "";
    for (var p = 0; p < PROPS.length; p++) {
      if (PROPS[p] === "fill" && original.getAttribute("fill")) continue;
      inline += PROPS[p] + ":" + estilo.getPropertyValue(PROPS[p]) + ";";
    }
    copia.setAttribute("style", inline);
  }

  // PNG: o gráfico desenhado, com os estilos calculados copiados, título no alto e fonte, legenda e endereço embaixo.
  function png(caixa) {
    var svg = caixa.querySelector("svg");
    var clone = svg.cloneNode(true);
    var originais = svg.querySelectorAll("*"), copias = clone.querySelectorAll("*");
    for (var i = 0; i < originais.length; i++) estiloInline(originais[i], copias[i]);
    var caixaSvg = svg.viewBox.baseVal, escala2 = 2;
    clone.setAttribute("width", caixaSvg.width * escala2);
    clone.setAttribute("height", caixaSvg.height * escala2);
    clone.setAttribute("xmlns", SVG);
    var fundo = getComputedStyle(document.body).backgroundColor, tinta = getComputedStyle(document.body).color;
    var imagem = new Image();
    imagem.onload = function () {
      var margem = 24, topo = 56, titulo = "700 26px Overpass, system-ui, sans-serif", corpo = "20px Overpass, system-ui, sans-serif";
      var notas = ["Barra listrada: preliminar, arredondado para múltiplo de 5.", "Anel: oculto pela regra de privacidade.",
        "Fonte: " + secao.dataset.fonte + ". Processado em " + secao.dataset.coleta + ".", location.href.split("#")[0]];
      var tela = document.createElement("canvas"), ctx = tela.getContext("2d");
      // A largura cabe o gráfico e cada linha de texto, medida antes de desenhar.
      ctx.font = titulo;
      var largura = Math.max(caixaSvg.width * escala2, ctx.measureText(caixa.dataset.titulo).width);
      ctx.font = corpo;
      notas.forEach(function (n) { largura = Math.max(largura, ctx.measureText(n).width); });
      tela.width = Math.ceil(largura) + margem * 2;
      tela.height = caixaSvg.height * escala2 + topo + 28 * notas.length + 24;
      ctx.fillStyle = fundo;
      ctx.fillRect(0, 0, tela.width, tela.height);
      ctx.fillStyle = tinta;
      ctx.font = titulo;
      ctx.fillText(caixa.dataset.titulo, margem, 36);
      ctx.drawImage(imagem, margem, topo);
      ctx.font = corpo;
      var y = topo + caixaSvg.height * escala2 + 30;
      notas.forEach(function (n, i) { ctx.fillText(n, margem, y + 28 * i); });
      tela.toBlob(function (blob) { baixar(caixa.id + ".png", blob); });
    };
    imagem.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(clone));
  }

  secao.addEventListener("click", function (e) {
    var botao = e.target.closest("button");
    if (!botao) return;
    if (botao.dataset.csv) {
      var tabela = document.getElementById(botao.dataset.csv);
      baixar(secao.dataset.codigo + "-" + tabela.dataset.csvNome + ".csv", new Blob([csv(tabela)], { type: "text/csv;charset=utf-8" }));
    } else if (botao.dataset.png) {
      var caixa = document.getElementById(botao.dataset.png);
      desenhar();
      if (caixa.querySelector("svg")) png(caixa);
    }
  });
})();
