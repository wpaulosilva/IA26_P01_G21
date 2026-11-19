# IA26_P01_G21 - Agente de rotas para produtos locais

Inteligência Artificial 2026/27, Licenciatura em Engenharia de Sistemas Informáticos

| Nome | Número |
|---|---|
| João Pereira | 31505 |
| Paulo Silva | 31506 |
| Vítor Rezende | 31521 |
| Leonardo Costa | 31528 |
| Simão Vidal | 29369 |

## Problema

Os veículos saem de um armazém, recolhem produtos em produtores locais, levam-nos ao armazém
e depois entregam-nos aos clientes (produtor, armazém, cliente).

Regras: janelas de tempo de recolha e de entrega, capacidade dos veículos, máximo de 24 h no
armazém, horizonte de 2 dias e tempos de serviço (10 min por paragem e 15 min no armazém).
O objetivo é minimizar o total de km.

## Estado do trabalho

- [x] Parte 1 (entrega preliminar): introdução, EDA (`02_eda_tiny.ipynb`) e modelação (`src/model.py`)
- [ ] Parte 2: Greedy e A*, Hill-Climbing, CSP e análise de resultados

## Estrutura

```text
├── data_tiny/                   dataset tiny (12 CSV)
├── data_small/                  dataset small (12 CSV)
├── src/
│   └── model.py                 Problem, Request, Vehicle, State, check_solution, cost
├── notebooks/
│   ├── 01_Project01_G21.ipynb   notebook principal
│   └── 02_eda_tiny.ipynb        análise exploratória dos dados
├── requirements.txt
└── readme.txt
```

## Execução

```bash
python -m pip install -r requirements.txt
jupyter notebook
```

Abrir `notebooks/02_eda_tiny.ipynb` e depois `notebooks/01_Project01_G21.ipynb` e correr
todas as células (Kernel > Restart & Run All).

## Modelo

Uma solução é um dicionário `{veículo: [(operação, item), ...]}`. Cada item passa por 4 operações,
por esta ordem: `pickup` (produtor), `unload` (armazém), `load` (armazém) e `deliver` (cliente).

```python
from model import Problem, check_solution, cost

problem = Problem.from_csv("data_tiny")
valida, km, mensagem, estado = check_solution(problem, solucao)
```

O `check_solution` simula o plano paragem a paragem e verifica a ordem das operações, as janelas
de tempo, a capacidade, o tempo máximo no armazém, o horizonte e o regresso ao armazém. Quando
o plano falha, a mensagem indica a regra que não foi cumprida.
