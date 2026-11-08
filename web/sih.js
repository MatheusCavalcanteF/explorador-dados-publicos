// Internações na página do município: troca de ano, dica nas marcas e exportação para CSV e PNG.
// Sem este script a página continua completa: os dois anos aparecem um abaixo do outro e cada gráfico
// tem a tabela equivalente logo abaixo dele.
(function () {
  "use strict";
  var secao = document.querySelector(".sih");
  if (!secao) return;

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
    };
    anos.addEventListener("change", mostrar);
    mostrar();
  }

  // Dica: o valor primeiro, depois a situação. O texto entra por textContent.
  var dica = document.createElement("div");
  dica.className = "dica";
  dica.hidden = true;
  document.body.appendChild(dica);
  secao.addEventListener("pointermove", function (e) {
    var alvo = e.target.closest && e.target.closest("[data-tip]");
    if (!alvo) { dica.hidden = true; return; }
    dica.textContent = alvo.getAttribute("data-tip");
    dica.hidden = false;
    var x = Math.min(e.clientX + 14, window.innerWidth - dica.offsetWidth - 8);
    dica.style.left = Math.max(8, x) + "px";
    dica.style.top = (e.clientY + 16) + "px";
  });
  secao.addEventListener("pointerleave", function () { dica.hidden = true; });

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
        linhas.push([secao.dataset.municipio, secao.dataset.codigo, tabela.dataset.csvNome, rotulo, cabecalho[k],
          celulas[k].getAttribute("data-v"), celulas[k].getAttribute("data-s") || "exato",
          secao.dataset.fonte, secao.dataset.acesso, secao.dataset.coleta, secao.dataset.ressalva]);
      }
    }
    return "﻿" + linhas.map(function (l) { return l.map(campo).join(";"); }).join("\r\n") + "\r\n";
  }

  var PROPS = ["fill", "fill-opacity", "stroke", "stroke-width", "opacity", "font-size", "font-family", "font-weight"];

  // PNG: o SVG com os estilos calculados copiados, título no alto e fonte, legenda e endereço embaixo.
  function png(svg) {
    var clone = svg.cloneNode(true);
    var originais = svg.querySelectorAll("*");
    var copias = clone.querySelectorAll("*");
    for (var i = 0; i < originais.length; i++) {
      var estilo = getComputedStyle(originais[i]);
      var inline = "";
      for (var p = 0; p < PROPS.length; p++) inline += PROPS[p] + ":" + estilo.getPropertyValue(PROPS[p]) + ";";
      copias[i].setAttribute("style", inline);
    }
    var caixa = svg.viewBox.baseVal;
    var escala = 2;
    clone.setAttribute("width", caixa.width * escala);
    clone.setAttribute("height", caixa.height * escala);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    var fundo = getComputedStyle(document.body).backgroundColor;
    var tinta = getComputedStyle(document.body).color;
    var imagem = new Image();
    imagem.onload = function () {
      var topo = 56, rodape = 96, margem = 24;
      var tela = document.createElement("canvas");
      tela.width = caixa.width * escala + margem * 2;
      tela.height = caixa.height * escala + topo + rodape;
      var ctx = tela.getContext("2d");
      ctx.fillStyle = fundo;
      ctx.fillRect(0, 0, tela.width, tela.height);
      ctx.fillStyle = tinta;
      ctx.font = "700 26px Overpass, system-ui, sans-serif";
      ctx.fillText(svg.dataset.titulo, margem, 36);
      ctx.drawImage(imagem, margem, topo);
      ctx.font = "20px Overpass, system-ui, sans-serif";
      var y = topo + caixa.height * escala + 30;
      ctx.fillText("Barra atenuada: preliminar, arredondado para múltiplo de 5. Anel: oculto pela regra de privacidade.", margem, y);
      ctx.fillText("Fonte: " + secao.dataset.fonte + ". Processado em " + secao.dataset.coleta.slice(0, 10) + ".", margem, y + 28);
      ctx.fillText(location.href.split("#")[0], margem, y + 56);
      tela.toBlob(function (blob) { baixar(svg.id + ".png", blob); });
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
      png(document.getElementById(botao.dataset.png));
    }
  });
})();
