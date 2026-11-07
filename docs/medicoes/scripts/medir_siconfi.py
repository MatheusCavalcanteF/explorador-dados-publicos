"""Cobertura do Siconfi numa amostra aleatória de municípios, respeitando 1 requisição por segundo."""
import json, random, sys, time, urllib.request, collections
from pathlib import Path
saida=Path(sys.argv[1]); dados=Path(sys.argv[2])
B="https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
entes=json.load(open(dados/'entes.json',encoding='utf-8'))['items']
mun=[e for e in entes if e['esfera']=='M']
random.seed(20261106)
amostra=random.sample(mun,60)
def get(url):
    for t in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"medicao-etapa0"}),timeout=60) as r:
                b=r.read(); return r.status,json.loads(b),len(b)
        except Exception as e:
            err=e; time.sleep(3)
    return 0,{"erro":str(err)},0
res=[];t_ini=time.perf_counter()
for e in amostra:
    id_=e['cod_ibge']; lin={'id':id_,'uf':e['uf'],'pop':e['populacao']}
    for ano in (2023,2024,2025):
        s,d,b=get(f"{B}/dca?an_exercicio={ano}&id_ente={id_}"); time.sleep(1.05)
        lin[f'dca{ano}']=len(d.get('items',[])); lin[f'bytes{ano}']=b; lin[f'status{ano}']=s
    s,d,b=get(f"{B}/rreo?an_exercicio=2025&nr_periodo=6&co_tipo_demonstrativo=RREO&id_ente={id_}"); time.sleep(1.05)
    lin['rreo2025_6']=len(d.get('items',[])); lin['bytes_rreo']=b
    res.append(lin)
(saida/'siconfi_amostra.json').write_text(json.dumps(res,indent=0),encoding='utf-8')
print('tempo',round(time.perf_counter()-t_ini),'s')
for a in (2023,2024,2025):
    c=sum(1 for r in res if r[f'dca{a}']>0); bs=sorted(r[f'bytes{a}'] for r in res if r[f'dca{a}']>0)
    print(f'DCA {a}: {c}/60 com dados; bytes p50 {bs[len(bs)//2] if bs else 0} max {bs[-1] if bs else 0}; linhas p50',sorted(r[f"dca{a}"] for r in res)[30])
print('RREO 2025/6:',sum(1 for r in res if r['rreo2025_6']>0),'/60')
print('status',collections.Counter(r['status2024'] for r in res))
# Sem pacing: a API responde 429?
print('rajada 15 chamadas sem espera:')
cont=collections.Counter(); hdr=None
for i in range(15):
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{B}/extrato_entregas?id_ente=3548500&an_referencia=2024",headers={"User-Agent":"medicao-etapa0"}),timeout=30) as r:
            cont[r.status]+=1
    except urllib.error.HTTPError as e:
        cont[e.code]+=1; hdr=dict(e.headers)
print(cont,hdr)
