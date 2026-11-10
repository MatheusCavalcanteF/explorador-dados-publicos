// Testes da busca por município (web/busca.js), fora do navegador. Roda pelo pytest: tests/test_busca.py.
const assert = require('node:assert/strict');
const { indexar, procurar } = require('../web/busca.js');

// Nomes reais; os códigos são inventados e a lista é só o que os testes usam.
const municipios = indexar([
  ['1', 'Santos', 'SP'], ['2', 'Santos Dumont', 'MG'], ['3', 'Sento Sé', 'BA'], ['4', 'Santa Fé', 'PR'],
  ['5', 'Santa Fé do Sul', 'SP'], ['6', 'Bonito de Santa Fé', 'PB'], ['7', 'Santa Rosa de Lima', 'SE'],
  ['8', 'Campo Alegre', 'AL'], ['9', 'Campo Alegre', 'SC'], ['10', 'Campo Grande', 'AL'], ['11', 'Campo Grande', 'MS'],
  ['12', 'Porto Xavier', 'RS'], ['13', 'Porto Alegre', 'RS'], ['14', 'Bom Jesus', 'PI'], ['15', 'Bom Jesus', 'RS'],
]);
const nomes = (texto) => procurar(municipios, texto).map((m) => `${m.nome} (${m.uf})`);

// As duas últimas letras não são sigla de UF: fazem parte do nome.
assert.deepEqual(nomes('Santa Fé'), ['Santa Fé (PR)', 'Santa Fé do Sul (SP)', 'Bonito de Santa Fé (PB)']);
assert.deepEqual(nomes('santa fe'), nomes('Santa Fé'));
assert.deepEqual(nomes('Porto Xa'), ['Porto Xavier (RS)']);

// São uma sigla que existe, mas fazem parte do nome: SE é Sergipe, e Sento Sé fica na Bahia.
assert.deepEqual(nomes('Sento Sé'), ['Sento Sé (BA)']);
assert.deepEqual(nomes('sento se'), ['Sento Sé (BA)']);
// "Campo Al": o começo de Campo Alegre, em qualquer UF, e também "Campo" em Alagoas. O nome inteiro vem antes.
assert.deepEqual(nomes('Campo Al'), ['Campo Alegre (AL)', 'Campo Alegre (SC)', 'Campo Grande (AL)']);

// A sigla no fim continua filtrando pela UF, com espaço, vírgula, barra ou hífen.
for (const texto of ['Santos SP', 'santos, sp', 'Santos/SP', 'Santos - SP']) {
  assert.deepEqual(nomes(texto), ['Santos (SP)'], texto);
}
assert.deepEqual(nomes('Bom Jesus RS'), ['Bom Jesus (RS)']);
assert.deepEqual(nomes('Santa SE'), ['Santa Rosa de Lima (SE)']);
assert.deepEqual(nomes('Santos'), ['Santos (SP)', 'Santos Dumont (MG)']);

// Nenhum município aparece duas vezes, e pouco texto não procura nada.
const repetidos = procurar(municipios, 'Campo Al').map((m) => m.codigo);
assert.equal(new Set(repetidos).size, repetidos.length);
assert.equal(procurar(municipios, 's'), null);
assert.equal(procurar(municipios, ' '), null);
assert.deepEqual(nomes('a SP'), []);
assert.deepEqual(nomes('Xique-Xique'), []);
