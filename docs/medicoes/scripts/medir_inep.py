"""Examina o .zip do Censo Escolar e a planilha do IDEB."""
import sys, zipfile, time, io, re
import duckdb, openpyxl
z_path, x_path, tmp = sys.argv[1:4]
z = zipfile.ZipFile(z_path)
for i in z.infolist()[:40]:
    print(i.filename.encode('ascii','replace').decode(), i.file_size, i.compress_size)
csvs=[i for i in z.infolist() if i.filename.lower().endswith('.csv') and 'ed_basica' in i.filename.lower()]
print('csv alvo', [c.filename.encode('ascii','replace').decode() for c in csvs])
c=csvs[0]
dest=z.extract(c, tmp)
con=duckdb.connect()
q=f"read_csv('{dest.replace(chr(92),'/')}', delim=';', header=true, encoding='latin-1', all_varchar=true, sample_size=-1)"
cols=[r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {q}").fetchall()]
print('colunas',len(cols),cols[:30])
print('com _AI:',[x for x in cols if x.endswith('_AI')][:8])
print('linhas, escolas, municipios, ufs', con.execute(f"SELECT count(*),count(distinct CO_ENTIDADE),count(distinct CO_MUNICIPIO),count(distinct SG_UF) FROM {q}").fetchone())
print('anos', con.execute(f"SELECT NU_ANO_CENSO,count(*) FROM {q} GROUP BY 1").fetchall())
print('situacao', con.execute(f"SELECT TP_SITUACAO_FUNCIONAMENTO,count(*) FROM {q} GROUP BY 1 ORDER BY 2 DESC").fetchall())
print('dep', con.execute(f"SELECT TP_DEPENDENCIA,count(*) FROM {q} GROUP BY 1 ORDER BY 2 DESC").fetchall())
print('santos', con.execute(f"""SELECT count(*), sum(QT_MAT_BAS::BIGINT), sum(QT_DOC_BAS::BIGINT), sum(QT_MAT_FUND_AI::BIGINT), sum(QT_MAT_MED::BIGINT) FROM {q} WHERE CO_MUNICIPIO='3548500'""").fetchone())
print('brasil mat', con.execute(f"SELECT sum(QT_MAT_BAS::BIGINT), count(*) FILTER (QT_MAT_BAS IS NULL) FROM {q}").fetchone())
cat=[r[0] for r in con.execute(f"SELECT DISTINCT TP_CATEGORIA_ESCOLA_PRIVADA FROM {q}").fetchall()] if 'TP_CATEGORIA_ESCOLA_PRIVADA' in cols else []
print('qt colunas QT_',sum(1 for x in cols if x.startswith('QT_')),'IN_',sum(1 for x in cols if x.startswith('IN_')))
# Agregado municipal
for nome, dims, extra in [("mun_dep",["CO_MUNICIPIO","TP_DEPENDENCIA"],""),("mun",["CO_MUNICIPIO"],"")]:
    medidas=",".join(f"sum(try_cast({x} AS BIGINT)) {x}" for x in cols if x.startswith('QT_MAT') or x.startswith('QT_DOC') or x.startswith('QT_TUR'))
    con.execute(f"COPY (SELECT {','.join(dims)},count(*) escolas,{medidas} FROM {q} GROUP BY {','.join(dims)} ORDER BY 1) TO '{tmp}/inep_{nome}.parquet' (FORMAT parquet,COMPRESSION zstd,COMPRESSION_LEVEL 9)")
    print(nome,'linhas',con.execute(f"SELECT count(*) FROM '{tmp}/inep_{nome}.parquet'").fetchone()[0])
import os
for n in ("mun_dep","mun"): print(n, round(os.path.getsize(f"{tmp}/inep_{n}.parquet")/1e6,2),'MB')
t=time.perf_counter()
wb=openpyxl.load_workbook(x_path, read_only=True, data_only=True)
print('abas',wb.sheetnames)
ws=wb[wb.sheetnames[0]]
linhas=list(ws.iter_rows(values_only=True))
print('linhas planilha',len(linhas),round(time.perf_counter()-t,1),'s')
for i,l in enumerate(linhas[:12]):
    print(i,str([x for x in l if x is not None][:14]).encode('ascii','replace').decode()[:260])
cab=next(i for i,l in enumerate(linhas) if l and l[0] in ('SG_UF','Sigla da UF'))
print('cabecalho na linha',cab,len(linhas[cab]))
h=linhas[cab]; idx={v:i for i,v in enumerate(h)}
col_obs=[v for v in h if v and str(v).startswith('VL_OBSERVADO')]
print('colunas obs',col_obs)
dados=[l for l in linhas[cab+1:] if l and l[0] and re.fullmatch('[A-Z]{2}',str(l[0]))]
print('linhas dados',len(dados),'municipios',len({l[idx['CO_MUNICIPIO']] for l in dados}))
print('redes',{r:sum(1 for l in dados if l[idx['REDE']]==r) for r in {l[idx['REDE']] for l in dados}})
v=col_obs[-1]
print('valores nao numericos em',v,{str(x):sum(1 for l in dados if l[idx[v]]==x) for x in {l[idx[v]] for l in dados} if not isinstance(x,(int,float))})
print('santos',[(l[idx['REDE']],l[idx[v]]) for l in dados if str(l[idx['CO_MUNICIPIO']])=='3548500'])
print('notas no fim',[str(l[0])[:200].encode('ascii','replace').decode() for l in linhas[-8:] if l and l[0]])
