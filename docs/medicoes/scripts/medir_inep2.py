import sys, re, zipfile, hashlib
import openpyxl
x_path, z_path, tmp = sys.argv[1:4]
wb=openpyxl.load_workbook(x_path, read_only=True, data_only=True)
linhas=list(wb[wb.sheetnames[0]].iter_rows(values_only=True))
cab=next(i for i,l in enumerate(linhas) if l and l[0]=='SG_UF')
h=linhas[cab]; idx={v:i for i,v in enumerate(h)}
print('cabecalho',cab,'colunas',len(h))
col_obs=[v for v in h if v and str(v).startswith('VL_OBSERVADO')]; print(col_obs)
print('metas',[v for v in h if v and 'PROJ' in str(v)][:9])
dados=[l for l in linhas[cab+1:] if l and l[0] and re.fullmatch('[A-Z]{2}',str(l[0]))]
print('linhas',len(dados),'municipios',len({l[idx['CO_MUNICIPIO']] for l in dados}))
print('redes',{r:sum(1 for l in dados if l[idx['REDE']]==r) for r in {l[idx['REDE']] for l in dados}})
for v in col_obs[-2:]:
    print(v,'nao numericos',{str(x):sum(1 for l in dados if l[idx[v]]==x) for x in {l[idx[v]] for l in dados} if not isinstance(x,(int,float))}, 'numericos',sum(1 for l in dados if isinstance(l[idx[v]],(int,float))))
mun_com=len({l[idx['CO_MUNICIPIO']] for l in dados if isinstance(l[idx[col_obs[-1]]],(int,float))})
print('municipios com IDEB 2023 numerico em ao menos uma rede',mun_com)
print('santos',[(l[idx['REDE']],l[idx[col_obs[-2]]],l[idx[col_obs[-1]]]) for l in dados if str(l[idx['CO_MUNICIPIO']])=='3548500'])
print('notas:')
for l in linhas[cab+1+len(dados):]:
    if l and l[0]: print(' ',str(l[0])[:240].encode('ascii','replace').decode())
print('--- nota no titulo:', str(linhas[4][0])[:600].encode('ascii','replace').decode())
z=zipfile.ZipFile(z_path)
for i in z.infolist():
    if i.filename.lower().endswith('.txt'):
        print('md5 declarado:',z.read(i).decode('latin-1').strip()[:136])
    if i.filename.lower().endswith('leia-me.pdf'):
        z.extract(i,tmp); print('leia-me',i.filename.encode('ascii','replace').decode())
    if i.filename.lower().endswith('microdados_ed_basica_2024.csv'):
        h5=hashlib.md5()
        with z.open(i) as f:
            for b in iter(lambda:f.read(1<<20),b''): h5.update(b)
        print('md5 calculado:',h5.hexdigest())
        with z.open(i) as f: amostra=f.read(1<<22)
        for enc in ('utf-8','latin-1'):
            try: amostra.decode(enc); print('decodifica como',enc); break
            except Exception as e: print('nao e',enc)
