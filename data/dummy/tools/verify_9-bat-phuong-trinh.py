from pathlib import Path
"""Re-derive every boxed answer of 9-bat-phuong-trinh.tex."""
from sympy import Eq, diff, Rational as R, S, Symbol, expand, factor, floor, ceiling, Interval, oo, reduce_inequalities, simplify, symbols
from sympy.solvers.inequalities import solve_univariate_inequality as sui

x = Symbol("x", real=True)
a, b, c = symbols("a b c", real=True)

def sol(ineq):
    return sui(ineq, x, relational=False)

# 001: a<b => a-7<b-7 ; -2a+1 > -2b+1 (differences signed by b-a>0)
assert simplify((b - 7) - (a - 7)) == b - a
assert expand((-2 * a + 1) - (-2 * b + 1)) == 2 * (b - a)

# 002: 3-4x >= 11 -> x <= -2 (both methods)
assert sol(3 - 4 * x >= 11) == Interval(-oo, -2)
assert sol(3 - 11 >= 4 * x) == Interval(-oo, -2)

# 003: (x+2)^2-(x-1)(x+1) <= 2x+17 -> x <= 6
assert expand((x + 2) ** 2 - (x - 1) * (x + 1)) == 4 * x + 5
assert sol((x + 2) ** 2 - (x - 1) * (x + 1) <= 2 * x + 17) == Interval(-oo, 6)

# 004: (x-2)/4-(2x+1)/3 >= 1/2 -> x <= -16/5
assert expand(12 * ((x - 2) / 4 - (2 * x + 1) / 3)) == -5 * x - 10
assert sol((x - 2) / 4 - (2 * x + 1) / 3 >= R(1, 2)) == Interval(-oo, R(-16, 5))

# 005: largest integer with (3x+2)/5 - x > (x-4)/2 ; x < 8/3 -> 2
s5 = sol((3 * x + 2) / 5 - x > (x - 4) / 2)
assert s5 == Interval.open(-oo, R(8, 3))
assert max(n for n in range(-50, 50) if n in s5) == 2

# 006: 20 questions, +5/-2, >=70 -> at least 16
assert sol(5 * x - 2 * (20 - x) >= 70) == Interval(R(110, 7), oo)
ok6 = [n for n in range(0, 21) if 5 * n - 2 * (20 - n) >= 70]
assert min(ok6) == 16 and 5 * 16 - 2 * 4 == 72 and 5 * 15 - 2 * 5 == 65

# 007: taxi tiers, budget 200 000 -> 22 km (brute force over km)
def fare(k):
    return 12000 * min(k, 1) + 10000 * max(0, min(k, 10) - 1) + 8000 * max(0, k - 10)
assert fare(10) == 102000 and fare(22) == 198000 and fare(23) == 206000
assert max(k for k in range(1, 100) if fare(k) <= 200000) == 22
assert sol(102000 + 8000 * (x - 10) <= 200000) == Interval(-oo, R(89, 4))

# 008: a^2+b^2-2ab=(a-b)^2 ; 2(a^2+b^2+c^2-ab-bc-ca) = sum of squares
assert expand(a**2 + b**2 - 2 * a * b - (a - b) ** 2) == 0
assert expand(2 * (a**2 + b**2 + c**2 - a * b - b * c - c * a) - ((a - b) ** 2 + (b - c) ** 2 + (c - a) ** 2)) == 0

# 009: (x+m)/2-(x-1)/3=1 -> x=4-3m ; integer m with 1 < x <= 7 -> {-1, 0}
m = Symbol("m", real=True)
from sympy import solve
xs = solve((x + m) / 2 - (x - 1) / 3 - 1, x)
assert xs == [4 - 3 * m]
assert sui(1 < 4 - 3 * m, m, relational=False).intersect(sui(4 - 3 * m <= 7, m, relational=False)) == Interval.Ropen(-1, 1)
assert [k for k in range(-20, 20) if 1 < 4 - 3 * k <= 7] == [-1, 0]

# 010: a^2/b - (2a-b) = (a-b)^2/b ; cyclic sum of (2a-b) = a+b+c ; numeric spot-check
assert simplify(a**2 / b - (2 * a - b) - (a - b) ** 2 / b) == 0
assert expand((2 * a - b) + (2 * b - c) + (2 * c - a)) == a + b + c
import random
random.seed(1)
for _ in range(2000):
    p, q, r = (random.uniform(0.01, 10) for _ in range(3))
    assert p * p / q + q * q / r + r * r / p >= p + q + r - 1e-9
t = R(7, 3)
assert t**2 / t * 3 == 3 * t  # equality at a=b=c

# 011: 3x-4 > x+2 <=> x > 3 ; among -2,3,4,7 -> 4, 7
s11 = sol(3 * x - 4 > x + 2)
assert s11 == Interval.open(3, oo)
assert [n for n in (-2, 3, 4, 7) if 3 * n - 4 > n + 2] == [4, 7] and [n for n in (-2, 3, 4, 7) if n in s11] == [4, 7]

# 012: sqrt(6-3x) -> x <= 2 ; 1/sqrt(2x+5) -> x > -5/2
from sympy import sqrt, Min, minimum
assert sol(6 - 3 * x >= 0) == Interval(-oo, 2)
assert sol(2 * x + 5 > 0) == Interval.open(R(-5, 2), oo)

# 013: a<b => 2a-3 < 2b-1 ; difference = 2(b-a)+2
assert expand((2 * b - 1) - (2 * a - 3) - (2 * (b - a) + 2)) == 0
t = Symbol("t", positive=True)  # t = b - a > 0
assert (2 * t + 2).is_positive

# 014: elevator 75 + 40x <= 600 -> 13
assert sol(75 + 40 * x <= 600) == Interval(-oo, R(105, 8))
assert max(n for n in range(0, 100) if 75 + 40 * n <= 600) == 13 and 75 + 40 * 13 == 595 and 75 + 40 * 14 == 635

# 015: 3(x-2)-1 < x+5 and (5x-1)/4 >= (x+3)/2 -> {3,4,5}
s15a, s15b = sol(3 * (x - 2) - 1 < x + 5), sol((5 * x - 1) / 4 >= (x + 3) / 2)
assert s15a == Interval.open(-oo, 6) and s15b == Interval(R(7, 3), oo)
assert s15a.intersect(s15b) == Interval.Ropen(R(7, 3), 6)
assert [n for n in range(-50, 50) if n in s15a and n in s15b] == [3, 4, 5]

# 016: x^2-6x+10 = (x-3)^2+1 > 0, min 1 at x=3
assert expand(x**2 - 6 * x + 10 - ((x - 3) ** 2 + 1)) == 0
assert minimum(x**2 - 6 * x + 10, x) == 1 and solve(x**2 - 6 * x + 10 - 1, x) == [3]

# 017: 49000 + 600x < 1300x -> x > 70 -> 71
assert sol(49000 + 600 * x < 1300 * x) == Interval.open(70, oo)
assert min(n for n in range(0, 1000) if 49000 + 600 * n < 1300 * n) == 71
assert 49000 + 600 * 71 == 91600 and 1300 * 71 == 92300 and 49000 + 600 * 70 == 1300 * 70 == 91000

# 018: P = (sqrt(x)+3)/(sqrt(x)-1) > 2, x>=0, x!=1 -> 1 < x < 25
st = Symbol("st", nonnegative=True)  # st = sqrt(x)
assert simplify((st + 3) / (st - 1) - 2 - (5 - st) / (st - 1)) == 0
s18 = sui((st + 3) / (st - 1) > 2, st, relational=False).intersect(Interval(0, oo))
assert s18 == Interval.open(1, 5), s18  # sqrt(x) in (1,5) -> x in (1,25)
xs18 = [k for k in range(0, 200) if k != 1 and (sqrt(k) + 3) / (sqrt(k) - 1) > 2]
assert xs18 == list(range(2, 25)), xs18
assert (sqrt(R(1, 4)) + 3) / (sqrt(R(1, 4)) - 1) < 2 and (sqrt(R(9, 4)) + 3) / (sqrt(R(9, 4)) - 1) > 2

# 019: 2(x-m) <= 3-x -> x <= (2m+3)/3 ; exactly 4 positive integer solutions <=> 9/2 <= m < 6
mm = Symbol("mm", real=True)
assert sol(2 * (x - 3) <= 3 - x) == Interval(-oo, 3)
assert solve(Eq(3 * x, 2 * mm + 3), x) == [(2 * mm + 3) / 3]
def npos(mv):
    return len([k for k in range(1, 100) if 2 * (k - mv) <= 3 - k])
assert npos(R(9, 2)) == 4 and npos(R(9, 2) - R(1, 1000)) == 3 and npos(6) == 5 and npos(6 - R(1, 1000)) == 4
assert all((npos(R(n, 100)) == 4) == (R(9, 2) <= R(n, 100) < 6) for n in range(0, 1000))

# 020: a+b=1, a,b>0: ab <= 1/4 ; (1+1/a)(1+1/b) = 1 + 2/(ab) >= 9, equality a=b=1/2
ap = Symbol("ap", positive=True)
bb = 1 - ap
assert simplify((1 + 1 / ap) * (1 + 1 / bb) - (1 + 2 / (ap * bb))) == 0
assert expand((ap + bb) ** 2 - 4 * ap * bb - (ap - bb) ** 2) == 0
assert sui(ap * bb <= R(1, 4), ap, relational=False).contains(R(1, 3))
f20 = (1 + 1 / ap) * (1 + 1 / bb)
assert solve(diff(f20, ap), ap) == [R(1, 2)] and f20.subs(ap, R(1, 2)) == 9
for _ in range(2000):
    p = random.uniform(0.001, 0.999)
    assert p * (1 - p) <= 0.25 + 1e-12 and (1 + 1 / p) * (1 + 1 / (1 - p)) >= 9 - 1e-9

# 021: x=-2 in 3x+5<0 (yes), 4-x>=6 (yes, equality), x^2+1>5 (no, equality with strict sign)
v = -2
assert (3 * v + 5 < 0, 4 - v >= 6, v**2 + 1 > 5) == (True, True, False)
assert 3 * v + 5 == -1 and 4 - v == 6 and v**2 + 1 == 5

# 022: (3b-2)-(3a-2) = 3(b-a) -> a <= b ; (-4a+7)-(-4b+7) = 4(b-a) > 0 -> a < b
assert expand((3 * b - 2) - (3 * a - 2)) == 3 * (b - a)
assert expand((-4 * a + 7) - (-4 * b + 7)) == expand(4 * (b - a))

# 023: 2x-6>0 <=> x>3 ; a) same set ; b) [3,oo) differs ; c) x<3 differs
s23 = sol(2 * x - 6 > 0)
assert s23 == Interval.open(3, oo)
assert sol(15 - 5 * x < 0) == s23
assert sol(4 * x >= 12) == Interval(3, oo) and Interval(3, oo) != s23
assert sol(7 - 3 * x > -2) == Interval.open(-oo, 3) and 7 - 3 * 4 == -5

# 024: a) after *6, LHS-RHS == 2 (0x <= -2) -> empty ; b) (x+3)^2-(x-1)(x+7) == 16 > 15 -> all reals
assert expand(6 * ((x - 1) / 2 - (x + 1) / 3) - (x - 7)) == 2
assert sol((x - 1) / 2 - (x + 1) / 3 <= (x - 7) / 6) == S.EmptySet
assert expand((x - 1) * (x + 7)) == x**2 + 6 * x - 7
assert expand((x + 3) ** 2 - (x - 1) * (x + 7)) == 16
assert sol((x + 3) ** 2 - (x - 1) * (x + 7) > 15) == S.Reals

# 025: {x : -7 <= 5-3x < 11} == (-2, 4] ; hieu: (5-3x)+7 = 3(4-x), 11-(5-3x) = 3(x+2)
assert sol(5 - 3 * x >= -7).intersect(sol(5 - 3 * x < 11)) == Interval.Lopen(-2, 4)
assert expand((5 - 3 * x) + 7 - 3 * (4 - x)) == 0 and expand(11 - (5 - 3 * x) - 3 * (x + 2)) == 0

# 026: (2-sqrt5)x + 3 <= x + sqrt5 -> x >= (sqrt5-1)/2
r5 = sqrt(5)
s26 = sol((2 - r5) * x + 3 <= x + r5)
assert s26.is_Interval and simplify(s26.inf - (r5 - 1) / 2) == 0 and s26.sup == oo and not s26.left_open, s26
assert (1 - r5).is_negative and simplify((r5 - 3) / (1 - r5) - (r5 - 1) / 2) == 0
assert expand((3 - r5) * (r5 + 1)) == 2 * r5 - 2 and expand((r5 - 1) * (r5 + 1)) == 4
assert expand((2 - r5) * (r5 - 1) / 2 + 3 - (3 * r5 - 1) / 2) == 0 and expand((r5 - 1) / 2 + r5 - (3 * r5 - 1) / 2) == 0

# 027: x=1 solution & x=4 not of 3x-2m < x+4 ; -1 < m <= 2 ; integers {0,1,2}
mq = Symbol("mq", real=True)
c1 = sui(3 * 1 - 2 * mq < 1 + 4, mq, relational=False)
c2 = sui(3 * 4 - 2 * mq >= 4 + 4, mq, relational=False)
assert c1 == Interval.open(-1, oo) and c2 == Interval(-oo, 2) and c1.intersect(c2) == Interval.Lopen(-1, 2)
assert [k for k in range(-20, 20) if 3 - 2 * k < 5 and not (12 - 2 * k < 8)] == [0, 1, 2]
assert solve(Eq(3 * x - 2 * mq, x + 4), x) == [mq + 2]  # bpt <=> x < m + 2
assert sol(3 * x - 2 * 2 < x + 4) == Interval.open(-oo, 4) and sol(3 * x + 2 < x + 4) == Interval.open(-oo, 1) and sol(3 * x - 6 < x + 4) == Interval.open(-oo, 5)

# 028: (1) x < 2m+1, (2) x > m-2 ; a) m=1 -> (-1,3) ; b) common solution <=> m > -3
assert sol(x - 2 * 1 < 1).intersect(sol(3 * x + 2 > 2 * x + 1)) == Interval.open(-1, 3)
def common28(mv):
    return sol(x - 2 * mv < 1).intersect(sol(3 * x + 2 > 2 * x + mv))
assert all((common28(R(n, 4)) != S.EmptySet) == (R(n, 4) > -3) for n in range(-24, 8))
assert common28(-3) == S.EmptySet and 0 in common28(0)
assert sui(mq - 2 < 2 * mq + 1, mq, relational=False) == Interval.open(-3, oo)

# 029: P = (sqrt x - 1)/(sqrt x + 2) < 1/3, x >= 0, x != 4 -> sqrt x < 5/2 -> integers {0,1,2,3,5,6}
st29 = Symbol("st29", nonnegative=True)  # st29 = sqrt(x)
assert sui((st29 - 1) / (st29 + 2) < R(1, 3), st29, relational=False).intersect(Interval(0, oo)) == Interval.Ropen(0, R(5, 2))
assert [k for k in range(0, 100) if k != 4 and (sqrt(k) - 1) / (sqrt(k) + 2) < R(1, 3)] == [0, 1, 2, 3, 5, 6]
assert R(5, 2) ** 2 == R(25, 4) and 4 * 6 < 25 < 4 * 7

# 030: (1) x < 2m+1, (2) x < 5 ; every solution of (1) solves (2) <=> m <= 2
assert sol((x + 1) / 2 > x - 2) == Interval.open(-oo, 5) and sol(3 * x - 2 < 13) == Interval.open(-oo, 5)
assert sol((x + 1) / 2 > x - 3) == Interval.open(-oo, 7) and not (3 * 6 - 2 < 13)
def incl30(mv):
    return sol((x + 1) / 2 > x - mv).is_subset(sol(3 * x - 2 < 13))
assert all(incl30(R(n, 4)) == (R(n, 4) <= 2) for n in range(-12, 20))

# 031: LHS - RHS == k*(x - 2026) with k < 0 -> x >= 2026
k31 = R(1, 2025) + R(1, 2024) - R(1, 2023) - R(1, 2022)
assert k31 < 0
d31 = (x - 1) / 2025 + (x - 2) / 2024 - (x - 3) / 2023 - (x - 4) / 2022
assert expand(d31 - k31 * (x - 2026)) == 0
assert sol((x - 1) / 2025 + (x - 2) / 2024 <= (x - 3) / 2023 + (x - 4) / 2022) == Interval(2026, oo)
assert d31.subs(x, 0) > 0 and d31.subs(x, 2026) == 0

# rule 7: in multi-part problems every solution step starts with "a) ", "b) ", ...
import re
tex = open(Path(__file__).resolve().parents[1] / "bank" / "9-bat-phuong-trinh.tex", encoding="utf-8").read()
for pid, body in re.findall(r"\\begin\{problem\}\[(\S+?)\](.*?)\\end\{problem\}", tex, re.S):
    stmt, _, rest = body.partition("\\begin{solution}")
    if not re.search(r"^a\) ", stmt, re.M):
        continue
    for blk in re.findall(r"\\begin\{solution\}(?:\[[^\]]*\])?(.*?)\\end\{solution\}", "\\begin{solution}" + rest, re.S):
        steps = [s.strip() for s in blk.strip().split("\n\n") if s.strip()]
        bad = [s[:40] for s in steps if not s.startswith("Đáp số") and not re.match(r"[a-z]\) ", s)]
        assert not bad, (pid, bad)

print("verify_9-bat-phuong-trinh: all 31 OK")
