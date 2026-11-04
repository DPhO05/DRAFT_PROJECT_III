"""Re-derive every boxed answer in 9-he-phuong-trinh-2.tex with sympy."""
from pathlib import Path

from sympy import (Eq, Interval, Matrix, Rational as R, S, Symbol, Abs, expand, factor, linsolve, minimum, oo,
                   simplify, solve, symbols)

TEX = (Path(__file__).resolve().parents[1] / "bank-mo-rong" / "9-he-phuong-trinh-2.tex").read_text()
x, y, m, n, u, v = symbols("x y m n u v")
CHECKED = set()


def boxed(s):
    assert "\\boxed{" + s + "}" in TEX, f"boxed text not in tex: {s}"
    CHECKED.add(s)


def one(eqs):
    s = solve(eqs, [x, y], dict=True)
    assert len(s) == 1, s
    return (s[0][x], s[0][y])


def all_boxed(tex):
    """Every \\boxed{...} body in the problems (header comment excluded), by brace matching."""
    body = tex[tex.index("\\begin{document}"):]
    out, i = [], 0
    while (i := body.find("\\boxed{", i)) != -1:
        j, depth = i + len("\\boxed{"), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(body[j], 0)
            j += 1
        out.append(body[i + len("\\boxed{"):j - 1])
        i = j
    return out


# 032: (1;-2) satisfies both, (3;2) only the first
e1 = lambda X, Y: 2 * X - Y == 4
e2 = lambda X, Y: X + 3 * Y == -5
assert (e1(1, -2), e2(1, -2)) == (True, True) and (e1(3, 2), e2(3, 2)) == (True, False)
assert one([Eq(2 * x - y, 4), Eq(x + 3 * y, -5)]) == (1, -2)
boxed(r"(1; -2) \text{ là nghiệm}"); boxed(r"(3; 2) \text{ không là nghiệm}")

# 033
assert one([Eq(y, 2 * x - 1), Eq(x + y, 8)]) == (3, 5)
assert 3 * 3 - 1 == 8 and 2 * 3 - 1 == 5
boxed(r"(x; y) = (3; 5)")

# 034
assert one([Eq(2 * x + 3 * y, 7), Eq(4 * x - y, 7)]) == (2, 1)
assert expand(3 * (4 * x - y) - (12 * x - 3 * y)) == 0 and 12 * 2 - 3 * 1 == 21
boxed(r"(x; y) = (2; 1)")

# 035
assert one([Eq(R(1, 2) * x + R(2, 5) * y, R(11, 5)), Eq(R(3, 10) * x + R(1, 5) * y, R(6, 5))]) == (2, 3)
assert one([Eq(5 * x + 4 * y, 22), Eq(3 * x + 2 * y, 12)]) == (2, 3)
boxed(r"(x; y) = (2; 3)")

# 036: line through A(2;1) and B(5;0)
a, b = symbols("a b")
assert solve([Eq(1, 2 * a + b), Eq(0, 5 * a + b)], [a, b]) == {a: R(-1, 3), b: R(5, 3)}
f36 = lambda X: R(-1, 3) * X + R(5, 3)
assert f36(2) == 1 and f36(5) == 0
boxed(r"a = -\dfrac{1}{3},\ b = \dfrac{5}{3}")

# 037
big, small = one([Eq(x + y, 45), Eq(x, 2 * y + 3)])
assert (big, small) == (31, 14) and divmod(31, 14) == (2, 3) and big + small == 45 and big > small > 3
boxed(r"\text{Số lớn: } 31;\ \text{số nhỏ: } 14")

# 038
assert solve([Eq(2 * m - n, 4), Eq(2 * n + m, 7)], [m, n]) == {m: 3, n: 2}
assert 3 * 2 + 2 * (-1) == 4 and 2 * 2 - 3 * (-1) == 7
boxed(r"m = 3,\ n = 2")

# 039
assert solve([Eq(3 * u + 4 * v, -1), Eq(6 * u - 2 * v, 3)], [u, v]) == {u: R(1, 3), v: R(-1, 2)}
assert one([Eq(3 / x + 4 / y, -1), Eq(6 / x - 2 / y, 3)]) == (3, -2)
assert 12 * R(1, 3) - 4 * R(-1, 2) == 6
boxed(r"(x; y) = (3; -2)")

# 040: ages
pa, ch = one([Eq(x - 5, 7 * (y - 5)), Eq(x + 5, 3 * (y + 5))])
assert (pa, ch) == (40, 10) and pa > ch > 5
assert (pa - 5, ch - 5) == (35, 5) and (pa + 5, ch + 5) == (45, 15)
boxed(r"\text{Bố: } 40 \text{ tuổi; con: } 10 \text{ tuổi}")

# 041: opposite directions meet after 1 h, same direction catch up after 3 h
va, vb = one([Eq(1 * (x + y), 60), Eq(3 * x - 3 * y, 60)])
assert (va, vb) == (40, 20) and va > vb > 0
boxed(r"\text{Xe từ } A \text{: } 40 \text{ km/h; xe từ } B \text{: } 20 \text{ km/h}")

# 042
p1, p2 = one([Eq(x + y, 800), Eq(R(6, 100) * x + R(8, 100) * y, 58)])
assert (p1, p2) == (300, 500) and one([Eq(x + y, 800), Eq(3 * x + 4 * y, 2900)]) == (300, 500)
assert R(6, 100) * 300 + R(8, 100) * 500 == 58
boxed(r"\text{Ngân hàng I: } 300 \text{ triệu đồng; ngân hàng II: } 500 \text{ triệu đồng}")

# 043
s43 = solve([Eq(x + y, 2 * m), Eq(x - 2 * y, 3 - m)], [x, y], dict=True)[0]
assert s43 == {x: m + 1, y: m - 1}
assert solve(Eq(2 * s43[x] - 3 * s43[y], 7), m) == [-2]
assert (s43[x].subs(m, -2), s43[y].subs(m, -2)) == (-1, -3)
boxed(r"m = -2")

# 044
M44 = one([Eq(2 * x + y, 5), Eq(x - y, 1)])
assert M44 == (2, 1)
assert solve(Eq(m * M44[0] + 2 * M44[1], 6), m) == [2]
boxed(r"m = 2")

# 045
s45 = solve([Eq(x + 2 * y, m), Eq(2 * x - y, 3)], [x, y], dict=True)[0]
assert simplify(s45[x] - (m + 6) / 5) == 0 and simplify(s45[y] - (2 * m - 3) / 5) == 0
mr = Symbol("mr", real=True)
region = (s45[x].subs(m, mr) > 0) & (s45[y].subs(m, mr) < 0)
assert region.as_set() == Interval.open(-6, R(3, 2)), region.as_set()
assert s45[x].subs(m, 0) == R(6, 5) and s45[y].subs(m, 0) == R(-3, 5)
boxed(r"-6 < m < \dfrac{3}{2}")

# 046
assert solve([Eq(2 * u + 4 * v, 2), Eq(6 * u - 8 * v, 1)], [u, v]) == {u: R(1, 2), v: R(1, 4)}
assert one([Eq(2 / (x - 1) + 4 / (y + 2), 2), Eq(6 / (x - 1) - 8 / (y + 2), 1)]) == (3, 2)
assert 3 != 1 and 2 != -2
boxed(r"(x; y) = (3; 2)")

# 047
assert solve([Eq(u + v, R(1, 6)), Eq(3 * u + 6 * v, R(7, 10))], [u, v]) == {u: R(1, 10), v: R(1, 15)}
X47, Y47 = 10, 15
assert X47 > 6 and Y47 > 6
assert R(1, X47) + R(1, Y47) == R(1, 6) and 3 * R(1, X47) + 6 * R(1, Y47) == R(7, 10)  # direct story check
assert R(7, 10) - R(1, 2) == R(1, 5)
boxed(r"\text{Vòi I: } 10 \text{ giờ; vòi II: } 15 \text{ giờ}")

# 048
s48 = solve([Eq(x + y, 2 * m - 2), Eq(2 * x - y, m + 5)], [x, y], dict=True)[0]
assert s48 == {x: m + 1, y: m - 3}
assert simplify(s48[x] - s48[y]) == 4
P48 = expand(s48[x] * s48[y])
assert P48 == m**2 - 2 * m - 3 and expand(P48 - ((m - 1)**2 - 4)) == 0
assert solve(P48.diff(m), m) == [1] and P48.subs(m, 1) == -4 and minimum(P48, m, S.Reals) == -4
assert (s48[x].subs(m, 1), s48[y].subs(m, 1)) == (2, -2)
boxed(r"(x; y) = (m + 1; m - 3)"); boxed(r"x - y = 4"); boxed(r"\min P = -4 \text{ khi } m = 1")

# 049
A49 = one([Eq(y, x + 2), Eq(y, -2 * x + 8)])
assert A49 == (2, 4) and -2 * 2 + 8 == 4
xB, xC = solve(x + 2, x)[0], solve(-2 * x + 8, x)[0]
assert (xB, xC) == (-2, 4) and R(1, 2) * abs(xC - xB) * A49[1] == 12
assert Matrix([[xB, 0, 1], [xC, 0, 1], [A49[0], A49[1], 1]]).det() / 2 in (12, -12)  # shoelace cross-check
boxed(r"A(2; 4)"); boxed(r"S = 12\ \text{cm}^2")

# 050
a50 = Matrix([[1, m], [m, 4]])
assert a50.det() == 4 - m**2
s50 = solve([Eq(x + m * y, m + 1), Eq(m * x + 4 * y, 2 * m + 2)], [x, y], dict=True)[0]
assert simplify(s50[x] - 2 * (m + 1) / (m + 2)) == 0 and simplify(s50[y] - (m + 1) / (m + 2)) == 0
assert expand((4 - m**2) - (2 - m) * (2 + m)) == 0 and expand(2 * m + 2 - m * (m + 1) - (2 - m) * (m + 1)) == 0
# m = 2: infinitely many (x = 3 - 2y); m = -2: none
g2 = linsolve([x + 2 * y - 3, 2 * x + 4 * y - 6], [x, y])
((gx, gy),) = g2
assert gy == y and simplify(gx - (3 - 2 * y)) == 0
assert linsolve([x - 2 * y + 1, -2 * x + 4 * y + 2], [x, y]).is_empty and (2 - (-2)) * (-2 + 1) == -4
# c) x + y integer, m integer, m != +-2
ints = [k for k in range(-1000, 1001) if k not in (2, -2) and (s50[x] + s50[y]).subs(m, k).is_integer]
assert ints == [-5, -3, -1, 1], ints
assert simplify(s50[x] + s50[y] - (3 - 3 / (m + 2))) == 0
assert [(s50[x] + s50[y]).subs(m, k) for k in ints] == [4, 6, 0, 2]
boxed(r"m \neq \pm 2,\ (x; y) = \left(\dfrac{2(m + 1)}{m + 2}; \dfrac{m + 1}{m + 2}\right)")
boxed(r"m = 2 \text{: vô số nghiệm; } m = -2 \text{: vô nghiệm}")
boxed(r"m \in \{-5;\ -3;\ -1;\ 1\}")

# 051
assert solve([Eq(3 * u + 2 * v, -1), Eq(6 * u - v, 3)], [u, v]) == {u: R(1, 3), v: -1}
assert one([Eq(2 * x - y, 3), Eq(x + 2 * y, -1)]) == (1, -1)
assert one([Eq(3 / (2 * x - y) + 2 / (x + 2 * y), -1), Eq(6 / (2 * x - y) - 1 / (x + 2 * y), 3)]) == (1, -1)
assert 2 * 1 - (-1) == 3 and 1 + 2 * (-1) == -1
boxed(r"(x; y) = (1; -1)")

N_PROBLEMS = 20
assert TEX.count(r"\begin{problem}[9DS-HPT-0") == N_PROBLEMS
for k in range(32, 52):
    assert TEX.count(f"\\begin{{problem}}[9DS-HPT-{k:03d}]") == 1, k
assert set(all_boxed(TEX)) == CHECKED, set(all_boxed(TEX)) ^ CHECKED  # every boxed answer was verified
print(f"verify_9-he-phuong-trinh-2: all {N_PROBLEMS} OK")
