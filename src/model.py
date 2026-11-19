from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

PICKUP, UNLOAD, LOAD, DELIVER = "pickup", "unload", "load", "deliver"
OPERACOES = [PICKUP, UNLOAD, LOAD, DELIVER]

FASE_ANTES = {PICKUP: "no produtor", UNLOAD: "no veiculo",
              LOAD: "no armazem", DELIVER: "carregado"}

FASE_DEPOIS = {PICKUP: "no veiculo", UNLOAD: "no armazem",
               LOAD: "carregado", DELIVER: "entregue"}


@dataclass
class Vehicle:
    id: int
    capacity_kg: float


@dataclass
class Request:
    id: int
    order_id: int
    producer_loc: int
    delivery_loc: int
    weight_kg: float
    pickup_start: datetime
    pickup_end: datetime
    delivery_start: datetime
    delivery_end: datetime


class Problem:
    def __init__(self, requests, vehicles, km, minutes, warehouse, rules, names):
        self.requests = {r.id: r for r in requests}
        self.vehicles = {v.id: v for v in vehicles}
        self.km = km
        self.minutes = minutes
        self.warehouse = warehouse
        self.names = names

        self.service = timedelta(minutes=float(rules.get("stop_service_min", 10)))
        self.handling = timedelta(minutes=float(rules.get("warehouse_handling_min", 15)))
        self.max_dwell = timedelta(hours=float(rules.get("max_warehouse_dwell_h", 24)))
        self.start = datetime.fromisoformat(rules.get("start_date", "2026-10-30"))
        self.end = self.start + timedelta(days=int(float(rules.get("horizon_days", 2))))

        self.orders = {}
        for r in requests:
            self.orders.setdefault(r.order_id, []).append(r.id)

    def distance(self, a, b):
        return 0.0 if a == b else self.km[a, b]

    def travel_time(self, a, b):
        return timedelta(minutes=0 if a == b else self.minutes[a, b])

    def location_of(self, op, item_id):
        r = self.requests[item_id]
        if op == PICKUP:
            return r.producer_loc
        if op == DELIVER:
            return r.delivery_loc
        return self.warehouse

    @classmethod
    def from_csv(cls, pasta):
        t = {f.stem: pd.read_csv(f) for f in Path(pasta).glob("*.csv")}
        rules = dict(zip(t["rules"]["rule"], t["rules"]["value"].astype(str)))

        loc = {(row.location_type, row.ref_id): row.location_id
               for row in t["locations"].itertuples()}
        names = dict(zip(t["locations"]["location_id"], t["locations"]["name"]))

        vehicles = [Vehicle(int(row.vehicle_id), float(row.capacity_kg))
                    for row in t["vehicles"].itertuples()]
        center_id = int(t["vehicles"]["center_id"].iloc[0])
        warehouse = loc["collection_center", center_id]

        items = (t["order_items"]
                 .merge(t["products"][["product_id", "producer_id"]], on="product_id")
                 .merge(t["orders"][["order_id", "delivery_location_id"]], on="order_id"))
        requests = []
        for row in items.itertuples():
            requests.append(Request(
                id=int(row.order_item_id),
                order_id=int(row.order_id),
                producer_loc=loc["producer", row.producer_id],
                delivery_loc=loc["delivery_location", row.delivery_location_id],
                weight_kg=float(row.weight_kg),
                pickup_start=datetime.fromisoformat(row.availability_start),
                pickup_end=datetime.fromisoformat(row.availability_end),
                delivery_start=datetime.fromisoformat(row.delivery_start),
                delivery_end=datetime.fromisoformat(row.delivery_end)))

        dm = t["distance_matrix"]
        pares = list(zip(dm["origin_location_id"], dm["destination_location_id"]))
        km = dict(zip(pares, dm["distance_km"]))
        minutes = dict(zip(pares, dm["duration_min"]))

        return cls(requests, vehicles, km, minutes, warehouse, rules, names)


class State:
    def __init__(self, problem):
        self.place = {v: problem.warehouse for v in problem.vehicles}
        self.time = {v: problem.start for v in problem.vehicles}
        self.load = {v: 0.0 for v in problem.vehicles}
        self.km = {v: 0.0 for v in problem.vehicles}
        self.stops = {v: [] for v in problem.vehicles}

        self.phase = {i: "no produtor" for i in problem.requests}
        self.owner = {i: None for i in problem.requests}
        self.arrived_wh = {}
        self.ready_wh = {}


def group_stops(problem, route):
    stops = []
    for op, i in route:
        local = problem.location_of(op, i)
        if stops and stops[-1][0] == op and stops[-1][1] == local:
            stops[-1][2].append(i)
        else:
            stops.append((op, local, [i]))
    return stops


def do_stop(problem, state, v, op, local, items):
    reqs = [problem.requests[i] for i in items]

    arrival = state.time[v] + problem.travel_time(state.place[v], local)
    km = problem.distance(state.place[v], local)

    if op == PICKUP:
        opens = max(r.pickup_start for r in reqs)
        closes = min(r.pickup_end for r in reqs)
    elif op == DELIVER:
        opens = max(r.delivery_start for r in reqs)
        closes = min(r.delivery_end for r in reqs)
    elif op == LOAD:
        opens = max(state.ready_wh[i] for i in items)
        closes = None
    else:
        opens, closes = arrival, None

    start = max(arrival, opens)
    if closes is not None and start > closes:
        return (f"janela de tempo falhada em {problem.names[local]} "
                f"(início {start:%d/%m %H:%M} > fecho {closes:%d/%m %H:%M})")

    if op == LOAD:
        for i in items:
            if start - state.arrived_wh[i] > problem.max_dwell:
                return f"item {i} ficou mais de {problem.max_dwell} no armazém"

    peso = sum(r.weight_kg for r in reqs)
    nova_carga = state.load[v] + (peso if op in (PICKUP, LOAD) else -peso)
    if nova_carga > problem.vehicles[v].capacity_kg + 1e-6:
        return (f"capacidade excedida no veículo {v} "
                f"({nova_carga:.1f} kg > {problem.vehicles[v].capacity_kg:.1f} kg)")

    duracao = problem.service if op in (PICKUP, DELIVER) else problem.handling
    finish = start + duracao
    if finish > problem.end:
        return "fora do horizonte de planeamento"

    state.place[v], state.time[v] = local, finish
    state.load[v] = nova_carga
    state.km[v] += km
    state.stops[v].append((op, local, list(items), arrival, start, finish, km))
    for i in items:
        state.phase[i] = FASE_DEPOIS[op]
        state.owner[i] = v if op in (PICKUP, LOAD) else None
        if op == UNLOAD:
            state.arrived_wh[i] = arrival
            state.ready_wh[i] = finish
    return None


def check_solution(problem, solution, require_all=True):
    vistos = [(op, i) for rota in solution.values() for op, i in rota]
    if len(vistos) != len(set(vistos)):
        return False, 0.0, "há operações repetidas", None
    usados = {i for _, i in vistos}
    for i in usados:
        feitas = [(op, i) in vistos for op in OPERACOES]
        if require_all and not all(feitas):
            return False, 0.0, f"faltam operações no item {i}", None
        if feitas != sorted(feitas, reverse=True):
            return False, 0.0, f"operações fora de ordem no item {i}", None
    if require_all and usados != set(problem.requests):
        faltam = len(set(problem.requests) - usados)
        return False, 0.0, f"faltam {faltam} itens por entregar", None

    state = State(problem)
    stops = {v: group_stops(problem, solution.get(v, [])) for v in problem.vehicles}
    pos = {v: 0 for v in problem.vehicles}

    while any(pos[v] < len(stops[v]) for v in stops):
        avancou = False
        for v in stops:
            while pos[v] < len(stops[v]):
                op, local, items = stops[v][pos[v]]
                if any(state.phase[i] != FASE_ANTES[op] for i in items):
                    break
                if op in (UNLOAD, DELIVER) and any(state.owner[i] != v for i in items):
                    return False, 0.0, f"veículo {v} não transporta os itens {items}", state
                erro = do_stop(problem, state, v, op, local, items)
                if erro:
                    return False, 0.0, f"veículo {v}, {op} {items}: {erro}", state
                pos[v] += 1
                avancou = True
        if not avancou:
            return False, 0.0, "ordem das operações impossível", state

    for v in problem.vehicles:
        km = problem.distance(state.place[v], problem.warehouse)
        chegada = state.time[v] + problem.travel_time(state.place[v], problem.warehouse)
        if chegada > problem.end:
            return False, 0.0, f"veículo {v} regressa fora do horizonte", state
        if km > 0:
            state.stops[v].append(("return", problem.warehouse, [], chegada, chegada, chegada, km))
        state.km[v] += km
        state.place[v], state.time[v] = problem.warehouse, chegada

    total = round(sum(state.km.values()), 2)
    return True, total, "solução válida", state


def cost(problem, solution):
    valida, km, _, _ = check_solution(problem, solution)
    return km if valida else float("inf")


def print_solution(problem, solution):
    valida, km, msg, state = check_solution(problem, solution, require_all=False)
    print(f"{msg} | total: {km} km")
    if not state:
        return
    for v, paragens in state.stops.items():
        print(f"\nVeículo {v} (capacidade {problem.vehicles[v].capacity_kg:.0f} kg)")
        for op, local, items, _, start, _, d in paragens:
            print(f"  {start:%d/%m %H:%M}  {op:<8} {problem.names[local]:<22} "
                  f"{len(items):>2} itens  +{d:.1f} km")
