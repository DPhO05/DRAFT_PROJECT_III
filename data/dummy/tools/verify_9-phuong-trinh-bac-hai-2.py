"""Re-derive every boxed answer of 9-phuong-trinh-bac-hai-2.tex with sympy."""
import re
from pathlib import Path

from sympy import Abs, Interval, Poly, S, discriminant, expand, minimum, oo, real_roots, simplify, solve, solveset, sqrt, symbols
from sympy import Rational as R

TEX = (Path(__file__).resolve().parents[1] / "bank-mo-rong" / "9-phuong-trinh-bac-hai-2.tex").read_text()
x, m, X, t = symbols("x m X t", real=True)
roots = lambda e, v=x: set(solve(e, v))
checked = []


def boxed(s):
    assert "\\boxed{" + s + "}" in TEX, f"boxed text not in tex: {s}"
    checked.append(s)


def all_boxed(src):
    """Contents of every \\boxed{...} outside comment lines (brace matching)."""
    src = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("%"))
    out = []
    for mt in re.finditer(r"\\boxed\{", src):
        i, depth = mt.end(), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        out.append(src[mt.end(): i - 1])
    return out


def two_roots(p, v=x):
    """The two roots (with multiplicity) of a quadratic with real roots."""
    r = solve(p, v)
    return r if len(r) == 2 else r * 2


# 032
assert roots(x**2 + 7*x) == {0, -7} and roots((x - 2)**2 - 9) == {5, -1}
boxed(r"x = 0;\ x = -7"); boxed(r"x = 5;\ x = -1")

# 033
assert 1 - 6 + 5 == 0 and roots(x**2 - 6*x + 5) == {1, 5}
assert 3 - 8 + 5 == 0 and roots(3*x**2 + 8*x + 5) == {-1, R(-5, 3)}
boxed(r"x_1 = 1;\ x_2 = 5"); boxed(r"x_1 = -1;\ x_2 = -\dfrac{5}{3}")

# 034
assert discriminant(3*x**2 + 5*x - 2, x) == 49 and roots(3*x**2 + 5*x - 2) == {R(1, 3), -2}
p34 = x**2 - 2*sqrt(2)*x + 2
assert simplify(discriminant(p34, x)) == 0 and roots(p34) == {sqrt(2)}
assert expand(p34 - (x - sqrt(2))**2) == 0
boxed(r"x = \dfrac{1}{3};\ x = -2"); boxed(r"x_1 = x_2 = \sqrt{2}")

# 035
assert discriminant(2*x**2 - 5*x + 4, x) == -7 and roots(2*x**2 - 5*x + 4) == set()
assert discriminant(9*x**2 - 6*x + 1, x) == 0 and roots(9*x**2 - 6*x + 1) == {R(1, 3)}
assert discriminant(x**2 + x - 5, x) == 21 and len(roots(x**2 + x - 5)) == 2
boxed(r"\text{Vô nghiệm}"); boxed(r"\text{Một nghiệm (nghiệm kép)}"); boxed(r"\text{Hai nghiệm phân biệt}")

# 036
for (a_, b_, c_), (s_, p_) in {(1, -7, 5): (7, 5), (2, 9, -4): (R(-9, 2), -2), (3, 0, -2): (0, R(-2, 3))}.items():
    q = a_*x**2 + b_*x + c_
    assert discriminant(q, x) > 0
    r1, r2 = solve(q, x)
    assert simplify(r1 + r2 - s_) == 0 and simplify(r1*r2 - p_) == 0
assert (49 - 20, 81 + 32, 24) == (29, 113, 24)
boxed(r"S = 7,\ P = 5"); boxed(r"S = -\dfrac{9}{2},\ P = -2"); boxed(r"S = 0,\ P = -\dfrac{2}{3}")

# 037
assert roots(X**2 - 11*X + 24, X) == {3, 8} and 121 - 96 == 25
assert roots(X**2 - 13*X + 40, X) == {5, 8} and 169 - 160 == 9
assert 2*(8 + 5) == 26 and 8*5 == 40 and 26 / 2 == 13
boxed(r"3 \text{ và } 8"); boxed(r"5 \text{ cm và } 8 \text{ cm}")

# 038
e38 = (x - 3)**2 + 5*x - (2*x + 13)
assert expand(e38) == x**2 - 3*x - 4 and roots(e38) == {4, -1}
assert 1 + 3 - 4 == 0 and 3 - 2 - 1 == 0
assert roots(x**2 / 2 - x / 3 - R(1, 6)) == {1, R(-1, 3)} and expand(6*(x**2 / 2 - x / 3 - R(1, 6))) == 3*x**2 - 2*x - 1
boxed(r"x = 4;\ x = -1"); boxed(r"x = 1;\ x = -\dfrac{1}{3}")

# 039
assert roots(x**4 - 13*x**2 + 36) == {2, -2, 3, -3} and roots(t**2 - 13*t + 36, t) == {9, 4}
assert roots(x**4 + 3*x**2 + 2) == set() and roots(t**2 + 3*t + 2, t) == {-1, -2}
assert 2**4 - 13*2**2 + 36 == 0 and 3**4 - 13*3**2 + 36 == 0
boxed(r"x = \pm 2;\ x = \pm 3"); boxed(r"\text{Phương trình vô nghiệm}")

# 040
e40 = 6 / (x - 1) - 5 / (x + 2) - 2
assert roots(e40) == {3, R(-7, 2)}
assert expand(6*(x + 2) - 5*(x - 1) - 2*(x - 1)*(x + 2)) == -(2*x**2 + x - 21)
assert discriminant(2*x**2 + x - 21, x) == 169
assert all(v not in (1, -2) for v in (3, R(-7, 2)))
boxed(r"x = 3;\ x = -\dfrac{7}{2}")

# 041
e41 = 45 / (x + 3) + 45 / (x - 3) - 8
assert roots(e41) == {12, R(-3, 4)} and expand(8*(x**2 - 9) - 90*x) == 8*x**2 - 90*x - 72
assert discriminant(4*x**2 - 45*x - 36, x) == 2601 == 51**2
assert R(45, 15) + R(45, 9) == 8
boxed(r"12 \text{ km/h}")

# 042
p42 = x**2 - 2*x + m - 3
assert roots(p42.subs(m, 3)) == {0, 2}
assert expand(discriminant(p42, x) / 4) == 4 - m and solve(4 - m > 0, m) == (m < 4)
assert solve(4 - m, m) == [4] and roots(p42.subs(m, 4)) == {1}
assert solve(p42.subs(x, 3), m) == [0] and roots(p42.subs(m, 0)) == {3, -1}
boxed(r"x = 0;\ x = 2"); boxed(r"m < 4"); boxed(r"m = 4;\ x_1 = x_2 = 1")
boxed(r"m = 0;\ \text{nghiệm còn lại } x = -1")

# 043
p43 = x**2 - 6*x + 4
assert discriminant(p43, x) / 4 == 5
r1, r2 = solve(p43, x)
assert simplify(r1**2 + r2**2) == 28 and simplify(Abs(r1 - r2) - 2*sqrt(5)) == 0 and simplify(r1**4 + r2**4) == 752
assert 28**2 - 2*4**2 == 752 and 36 - 16 == 20 and sqrt(20) == 2*sqrt(5)
boxed(r"A = 28"); boxed(r"B = 2\sqrt{5}"); boxed(r"C = 752")

# 044
e44 = x**2 + (x + 7)**2 - 13**2
assert expand(e44 / 2) == x**2 + 7*x - 60 and roots(e44) == {5, -12} and discriminant(x**2 + 7*x - 60, x) == 289
assert 5**2 + 12**2 == 13**2 and 12 - 5 == 7
boxed(r"5 \text{ cm và } 12 \text{ cm}")

# 045
p45 = x**2 - 2*(m + 1)*x + m**2 + m - 2
assert expand(discriminant(p45, x) / 4) == m + 3
assert expand(4*(m + 1)**2 - 2*(m**2 + m - 2)) == 2*m**2 + 6*m + 8
assert roots(2*m**2 + 6*m + 8 - 8, m) == {0, -3}
good = []
for mv in [R(k, 2) for k in range(-12, 13)]:
    q = p45.subs(m, mv)
    if discriminant(q, x) > 0:
        r1, r2 = solve(q, x)
        if simplify(r1**2 + r2**2 - 8) == 0:
            good.append(mv)
assert good == [0], good
assert discriminant(p45.subs(m, -3), x) == 0
boxed(r"m > -3"); boxed(r"m = 0")

# 046
p46 = x**2 - (2*m + 1)*x + m**2 + m - 6
assert expand(discriminant(p46, x)) == 25
assert roots(p46) == {m + 3, m - 2} and expand((x - m - 3)*(x - m + 2) - p46) == 0
assert roots(m + 3 - 2*(m - 2), m) == {7} and roots(m - 2 - 2*(m + 3), m) == {-8}
hit = set()
for mv in [R(k, 2) for k in range(-40, 41)]:
    ra, rb = solve(p46.subs(m, mv), x)
    if ra == 2*rb or rb == 2*ra:
        hit.add(mv)
assert hit == {7, -8}, hit
boxed(r"\Delta = 25 > 0 \text{ với mọi } m"); boxed(r"x = m + 3;\ x = m - 2"); boxed(r"m = 7 \text{ hoặc } m = -8")

# 047
e47 = (x**2 - 2*x)**2 - 3*(x**2 - 2*x) - 4
assert roots(e47) == {1, 1 + sqrt(5), 1 - sqrt(5)}
assert roots(t**2 - 3*t - 4, t) == {-1, 4} and 1 + 3 - 4 == 0
assert roots(x**2 - 2*x - 4) == {1 + sqrt(5), 1 - sqrt(5)} and roots(x**2 - 2*x + 1) == {1}
boxed(r"x = 1;\ x = 1 + \sqrt{5};\ x = 1 - \sqrt{5}")

# 048
k48 = (m - 1)*x + 4
hd = x**2 - k48  # hoành độ giao điểm
assert expand(discriminant(hd, x) - ((m - 1)**2 + 16)) == 0
assert roots(hd.subs(m, 4)) == {-1, 4} and {(v, v**2) for v in roots(hd.subs(m, 4))} == {(-1, 1), (4, 16)}
assert all(k48.subs({m: 4, x: v}) == v**2 for v in (-1, 4))
assert expand(((m - 1)**2 + 16) - 25 - ((m - 1)**2 - 9)) == 0 and roots((m - 1)**2 - 9, m) == {4, -2}
hit = set()
for mv in range(-30, 31):
    ra, rb = solve(hd.subs(m, mv), x)
    if Abs(ra - rb) == 5:
        hit.add(mv)
assert hit == {4, -2}, hit
boxed(r"\Delta = (m - 1)^2 + 16 > 0 \text{ với mọi } m"); boxed(r"(-1; 1) \text{ và } (4; 16)")
boxed(r"m = 4 \text{ hoặc } m = -2")

# 049
e49 = R(180, 1) / x - (120 / x + 60 / (x + 10)) - R(3, 10)
assert roots(e49) == {40, -50}
assert expand(600*10 - 3*x*(x + 10) + 3*(x**2 + 10*x - 2000)) == 0 and discriminant(x**2 + 10*x - 2000, x) / 4 == 2025
assert R(180, 40) - (R(120, 40) + R(60, 50)) == R(3, 10) == R(18, 60)
boxed(r"40 \text{ km/h}")

# 050
p50 = x**2 - 2*(m + 1)*x + m**2 + 2
assert expand(discriminant(p50, x) / 4) == 2*m - 1 and solveset(2*m - 1 >= 0, m, domain=S.Reals) == Interval(R(1, 2), oo)
A50 = 4*(m + 1)**2 - 2*(m**2 + 2)
assert expand(A50) == 2*m**2 + 8*m
for mv in (R(1, 2), 1, 2, 5):
    r1, r2 = two_roots(p50.subs(m, mv))
    assert simplify(r1**2 + r2**2 - A50.subs(m, mv)) == 0
assert expand(2*m**2 + 8*m - R(9, 2) - (2*m - 1)*(2*m + 9) / 2) == 0
assert minimum(2*m**2 + 8*m, m, Interval(R(1, 2), oo)) == R(9, 2)
assert (2*m**2 + 8*m).subs(m, -2) == -8 and -2 < R(1, 2)  # unconstrained vertex is not allowed
assert two_roots(p50.subs(m, R(1, 2))) == [R(3, 2), R(3, 2)]
boxed(r"m \geq \dfrac{1}{2}"); boxed(r"A = 2m^2 + 8m"); boxed(r"A_{\min} = \dfrac{9}{2} \text{ khi } m = \dfrac{1}{2}")

# 051
p51 = lambda mv: Poly(x**4 - (mv + 3)*x**2 + 3*mv, x)
assert expand(t**2 - (m + 3)*t + 3*m - (t - 3)*(t - m)) == 0
assert roots(p51(4).as_expr()) == {sqrt(3), -sqrt(3), 2, -2}
cnt = {}
for mv in [R(k, 2) for k in range(-20, 21)]:
    cnt[mv] = len(set(real_roots(p51(mv))))
assert {mv for mv, c in cnt.items() if c == 3} == {0}, cnt
assert {mv for mv, c in cnt.items() if c == 4} == {mv for mv in cnt if mv > 0 and mv != 3}
assert all(cnt[mv] == 2 for mv in cnt if mv < 0 or mv == 3)
assert roots(x**4 - 3*x**2) == {0, sqrt(3), -sqrt(3)}
boxed(r"x = \pm\sqrt{3};\ x = \pm 2"); boxed(r"m = 0"); boxed(r"m > 0 \text{ và } m \neq 3")

assert sorted(all_boxed(TEX)) == sorted(checked), "some \\boxed answer is not verified"
ids = re.findall(r"\\begin\{problem\}\[9DS-PT2-(\d{3})\]", TEX)
assert ids == [f"{i:03d}" for i in range(32, 52)], ids
print("9-phuong-trinh-bac-hai-2: all 20 problems verified OK")
