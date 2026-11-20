"""运输问题精确求解：二部图最小费用流（SSP 连续最短路）。

网络结构：源点 -> 年龄段行（容量=行占比，费用0），
行 -> 来访方式列（容量无限，费用=单元代价，仅可行组合），
列 -> 汇点（容量=列占比，费用0）。
每次增广至少饱和一条源边或汇边，故增广轮数不超过 行数+列数；
初始零流无负环，沿最短路增广保持最优性（SSP 定理）。
同时提供最大流可行性判定与最小割，用于定位不可行构成的冲突。
"""
EPS = 1e-9
INF = float('inf')


def _build(supplies, demands, costs):
    rows, cols = len(supplies), len(demands)
    source, sink = 0, rows + cols + 1
    graph = [[] for _ in range(rows + cols + 2)]

    def add(u, v, cap, cost):
        graph[u].append([v, cap, cost, len(graph[v])])
        graph[v].append([u, 0.0, -cost, len(graph[u]) - 1])

    for i, s in enumerate(supplies):
        if s > EPS:
            add(source, 1 + i, s, 0.0)
    cell_edge = {}
    for (i, j), c in costs.items():
        add(1 + i, 1 + rows + j, INF, c)
        cell_edge[(i, j)] = (1 + i, len(graph[1 + i]) - 1)
    for j, d in enumerate(demands):
        if d > EPS:
            add(1 + rows + j, sink, d, 0.0)
    return graph, source, sink, cell_edge


def _augment(graph, source, sink, total):
    """连续最短路增广，返回 (流量, 费用)。费用沿原向边累计。"""
    n = len(graph)
    flow = cost = 0.0
    while flow < total - EPS:
        dist = [INF] * n
        prev = [None] * n
        dist[source] = 0.0
        for _ in range(n - 1):  # Bellman-Ford，允许负费用边
            updated = False
            for u in range(n):
                if dist[u] == INF:
                    continue
                for k, e in enumerate(graph[u]):
                    if e[1] > EPS and dist[u] + e[2] < dist[e[0]] - EPS:
                        dist[e[0]] = dist[u] + e[2]
                        prev[e[0]] = (u, k)
                        updated = True
            if not updated:
                break
        if prev[sink] is None:
            break  # 残余网络中无可增广路：已达最大流
        bottleneck, v = total - flow, sink
        while v != source:
            u, k = prev[v]
            bottleneck = min(bottleneck, graph[u][k][1])
            v = u
        v = sink
        while v != source:
            u, k = prev[v]
            e = graph[u][k]
            e[1] -= bottleneck
            graph[v][e[3]][1] += bottleneck
            cost += bottleneck * e[2]
            v = u
        flow += bottleneck
    return flow, cost


def min_cost_flow(supplies, demands, costs):
    """求最小费用构成。返回 (实际流量, 最小费用, {(行,列): 份额})。

    实际流量 < 供给合计 即不可行；调用方应先做可行性判定。
    """
    graph, source, sink, cell_edge = _build(supplies, demands, costs)
    flow, cost = _augment(graph, source, sink, sum(supplies))
    plan = {}
    for (i, j), (u, k) in cell_edge.items():
        used = graph[graph[u][k][0]][graph[u][k][3]][1]  # 反向边容量即已用流量
        if used > EPS:
            plan[(i, j)] = used
    return flow, cost, plan


def feasibility_cut(supplies, demands, allowed):
    """最大流可行性判定。返回 (可行?, 源点可达行集合, 源点可达列集合)。

    不可行时，可达行集合与其可行列集合构成 Hall 冲突证据：
    可达行的占比合计 > 其可行列的占比合计（最小割）。
    """
    graph, source, sink, _ = _build(supplies, demands, {(i, j): 0.0 for (i, j) in allowed})
    flow, _ = _augment(graph, source, sink, sum(supplies))
    if flow >= sum(supplies) - EPS:
        return True, set(), set()
    rows, cols = len(supplies), len(demands)
    seen, stack = {source}, [source]
    while stack:  # 残余网络中从源点可达的节点 = 最小割的源侧
        u = stack.pop()
        for e in graph[u]:
            if e[1] > EPS and e[0] not in seen:
                seen.add(e[0])
                stack.append(e[0])
    reach_rows = {v - 1 for v in seen if 1 <= v <= rows}
    reach_cols = {v - 1 - rows for v in seen if rows + 1 <= v <= rows + cols}
    return False, reach_rows, reach_cols
