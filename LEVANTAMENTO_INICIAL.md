# Levantamento inicial - SOO/PROENG

Origem analisada: `C:\Users\Neverton\Documents\New project\SOO-PRONEG`

## Conclusao inicial

Vale reconstruir do zero usando os fontes Clipper como especificacao de negocio. A versao nova nao deve copiar a estrutura antiga de arquivos por obra e campos repetidos, mas deve preservar as regras principais, principalmente composicao de servicos, taxas, orcamento e relatorios.

## Escopo encontrado

Menu principal (`PRO100.PRG`):

- Manutencao de cadastros
- Emissao de relatorios dos cadastros
- Orcamento de obras
- Planejamento de obras
- Controle de obras
- Folha de pagamento
- Rotinas especiais

Menus secundarios encontrados:

- Cadastros: insumos, taxas, descricao orcamentaria, servicos
- Relatorios de cadastros: insumos, taxas, descricao, servicos
- Orcamento: obras, orcamento, relatorio resumido, detalhado, percentuais, curva ABC de insumos, curva ABC de servicos, planilha de insumos da obra
- Planejamento: cronograma, relatorio do cronograma, relatorios periodicos de insumos/servicos, dimensionamento de mao de obra
- Controle: estoque, insumos adquiridos, insumos utilizados, servicos executados, transferencia, relatorios planejado x realizado
- Rotinas especiais: parametros, copia/recuperacao de orcamento, alteracao de preco dos insumos, reindexacao

## DBFs enviados

Atualizacao em 2026-06-16: foram adicionados DBFs de obras e estruturas auxiliares:

- `INFORMA.DBF`
- `SISTEMA.DBF`
- `CRONOG20.DBF`
- `PERIOD20.DBF`
- `DIMENS20.DBF`
- `EXESER20.DBF`
- `RELMO.DBF`
- `RELORCRE.DBF`

Os arquivos `- Copia.DBF` foram ignorados na importacao para evitar duplicidade.

### Insumos

Arquivo: `1781550392981_INSUMOS.DBF`

Registros: 2348

Campos:

- `INSCODIGO` texto(4)
- `INSNOME` texto(40)
- `INSACESSO` texto(4)
- `INSPRECO` numerico(12,2)
- `INSUNIDADE` texto(3)
- `INSDATA` data

### Servicos

Arquivo: `1781550436649_SERVICOS.DBF`

Registros: 1343

Campos principais:

- `SERCODIGO` texto(4)
- `SERITEM` texto(5)
- `SERNOME` texto(30)
- `SERACESSO` texto(4)
- `SERUNIDADE` texto(3)
- `SERPRECO` numerico(13,2)

Composicao antiga:

- Ate 15 insumos por servico: `SERINS01` a `SERINS15`
- Quantidades correspondentes: `SERQTD01` a `SERQTD15`
- Ate 5 taxas por servico: `SERTAX01` a `SERTAX05`

Na versao nova isso deve virar tabelas relacionadas:

- `services`
- `service_inputs`
- `service_taxes`

### Descricao orcamentaria

Arquivo: `1781550456810_DESCRICA.DBF`

Registros: 130

Campos:

- `DESCODIGO` texto(3)
- `DESITEM` texto(4)
- `DESNOME` texto(30)

### Taxas

Arquivo: `1781550477018_TAXAS.DBF`

Registros: 6

Campos:

- `TAXCODIGO` texto(2)
- `TAXNOME` texto(30)
- `TAXACESSO` texto(4)
- `TAXPERC` numerico(6,2)

### Parametros

Arquivo: `PARAMETR.DBF`

Registros: 2

Campos:

- `PARUNIDADE` texto(5)
- `PARVALOR` numerico(11,3)

## Regra critica de calculo

Fonte: `PROCEDUR.PRG`, procedimento `CALCULO`.

Resumo da regra:

1. Para cada item do orcamento, busca o servico.
2. Carrega as taxas do servico.
3. Para cada insumo do servico:
   - busca o preco do insumo;
   - verifica se cada taxa se aplica pelo codigo de acesso;
   - soma taxas acumuladas;
   - calcula valor do insumo com taxa;
   - separa custo entre material/produto e mao de obra pelo primeiro caractere de `INSACESSO`.
4. Divide pelos parametros de unidade/valor.
5. Multiplica pela quantidade orcada.
6. Arredonda valores parciais.
7. Gera totais por item, por servico, mao de obra, material e total geral.

Essa rotina deve ser portada primeiro e coberta por testes, pois e o coracao do sistema.

## Arquivos/tabelas mencionados nos fontes, mas nao enviados como DBF nesta pasta

Os fontes citam estruturas criadas por obra ou temporarias:

- `INFORMA`
- `SISTEMA`
- `ORCAME`
- `RELORC`
- `RELORCRE`
- `RELINS`
- `RELMO`
- `CRONOG`
- `PERIOD`
- `DIMENS`
- `ESTINS`
- `ADQINS`
- `UTIINS`
- `EXESER`
- `COMPLEME`
- `AUXILIAR`

Precisamos reconstruir estes modelos pelos fontes e, se possivel, receber exemplos desses DBFs quando existirem em outro backup.

## Arquitetura recomendada

Para Windows local:

- Aplicacao desktop moderna
- Banco SQLite em arquivo unico
- Importador de DBF
- Camada de calculo testavel separada da interface
- Relatorios exportaveis em PDF/Excel

Stack sugerida:

- Backend/local: Python ou Node.js
- Interface desktop: Electron/Tauri ou app web local
- Banco: SQLite

Minha preferencia tecnica para este caso: app local com SQLite e interface web/desktop, porque facilita telas ricas, relatorios e manutencao futura.

## Primeira entrega recomendada

MVP 1:

- Importar DBFs enviados
- Criar banco SQLite normalizado
- Tela de insumos
- Tela de taxas
- Tela de servicos com composicao de insumos e taxas
- Calculo de preco unitario do servico
- Conferencia contra `SERPRECO` do DBF antigo

Status: iniciado em `C:\Users\Neverton\Documents\New project\soo-proneg-rewrite`.

Arquivos principais:

- `app.py`
- `db.py`
- `import_dbf.py`
- `static/index.html`
- `static/app.css`
- `static/app.js`

Banco gerado:

- `data/soo_proneg.sqlite`

Importacao validada:

- 2117 insumos ativos
- 1343 servicos
- 126 descricoes ativas
- 6 taxas
- 20 obras com nome

Observacao: existem 54 referencias de insumos em composicoes de servicos que nao encontram cadastro correspondente nos DBFs enviados. A interface preserva essas referencias em vez de falhar.

MVP 2:

- Cadastro de obras
- Orcamento por obra
- Calculo completo do orcamento
- Relatorio resumido/detalhado
- Curvas ABC

MVP 3:

- Cronograma
- Planejado x executado
- Estoque/controle de obras
- Relatorios finais
