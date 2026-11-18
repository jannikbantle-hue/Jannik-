#!/usr/bin/env python3
"""Erzeugt die Demo-Kursreihen fuer bot.py (reproduzierbar, keine echten Kurse)."""
import csv


def write(path: str, rows: list[tuple[int, float]]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "close"])
        for i, p in rows:
            w.writerow([i, round(p, 2)])


# BOOM: anhaltender Aufwaertstrend -> Bot soll sich "vermehren".
rows, p = [], 100.0
import random
rng = random.Random(1)
for i in range(600):
    p *= 1 + rng.gauss(0.004, 0.010)
    rows.append((i, p))
write("demo_boom.csv", rows)

# BULLENFALLE: kleine Anstiege (bullische Signale), dann harte Abverkaeufe
# -> wiederholte Stop-Outs -> Ruin. Zeigt die "Sterben"-Mechanik.
rows, p, i = [], 100.0, 0
for _ in range(40):
    for _ in range(8):
        p *= 1.015
        rows.append((i, p)); i += 1
    for _ in range(5):
        p *= 0.94
        rows.append((i, max(1.0, p))); i += 1
write("demo_trap.csv", rows)

print("demo_boom.csv und demo_trap.csv erstellt.")
