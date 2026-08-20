# SOO/PROENG Rewrite

Primeira versao local do novo sistema SOO/PROENG.

## O que ja faz

- Le os DBFs antigos da pasta `SOO-PRONEG`.
- Importa a base para SQLite.
- Normaliza servicos em:
  - servicos
  - insumos do servico
  - taxas do servico
- Mostra cadastros de insumos, taxas, servicos e obras.
- Calcula o preco unitario do servico pela composicao antiga.
- Compara o calculo atual com o `SERPRECO` gravado no DBF.
- Cria um catalogo unificado para varias bases.
- Importa o SINAPI existente como uma base separada.
- Mantem o SOO/PROENG legado como outra base.
- Aplica uma primeira classificacao gerencial automatica: tipo de custo, etapa, familia e origem.

## Como abrir

Clique duas vezes em:

```text
Abrir SOO PROENG.bat
```

Ou rode pelo PowerShell:

```powershell
cd "C:\Users\Neverton\Documents\New project\soo-proneg-rewrite"
& "C:\Users\Neverton\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" app.py
```

Depois abra:

```text
http://127.0.0.1:8775
```

## Observacoes importantes

- O banco novo fica em `data/soo_proneg.sqlite`.
- A importacao ignora arquivos `- Copia.DBF` para evitar duplicidade.
- Existem 54 referencias de insumos em servicos que nao encontram cadastro correspondente nos DBFs enviados.
- Os DBFs de orcamento por obra, como `ORCAME20.DBF`, ainda nao estao na pasta. Sem eles, a primeira etapa fica concentrada em cadastros e composicoes.

## Catalogo unificado

Bases importadas no nucleo gerencial:

- SINAPI 04/2026: 4.855 insumos, 10.378 composicoes, precos por UF e itens analiticos.
- SOO/PROENG legado: 2.117 insumos, 1.343 servicos/composicoes e composicoes antigas.

O objetivo e que toda base futura entre no mesmo modelo e receba a mesma camada de inteligencia gerencial.
