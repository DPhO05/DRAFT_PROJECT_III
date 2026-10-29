"""Re-derive every boxed answer in 8-phuong-trinh-bac-nhat.tex with sympy."""
from pathlib import Path

import sympy as sp

TEX = (Path(__file__).resolve().parents[1] / "bank" / "8-phuong-trinh-bac-nhat.tex").read_text()
x, m, v = sp.symbols("x m v")
R = sp.Rational


def boxed(s):
    assert "\\boxed{" + s + "}" in TEX, f"boxed text not in tex: {s}"


def sol(lhs, rhs, var=x):
    return set(sp.solve(sp.Eq(lhs, rhs), var))


# 001
assert sol(4*x - 20, 0) == {5} and sol(5*x + 8, 3*x - 4) == {-6}
boxed(r"x = 5"); boxed(r"x = -6")

# 002
f = lambda t: (3*t + 5) - (t + 1)
assert f(-2) == 0 and f(1) != 0
assert sol(2*3 + m, 5 - 3, m) == {-4}
assert sol(2*x - 4, 5 - x) == {3}
boxed(r"x = -2 \text{ là nghiệm; } x = 1 \text{ không là nghiệm}"); boxed(r"m = -4")

# 003
assert sol(3*(x - 2) - 2*(x + 1), 5 - x) == {R(13, 2)}
boxed(r"x = \dfrac{13}{2}")

# 004
assert sol((2*x - 1) / 3 - (x + 2) / 4, (x - 1) / 6) == {R(8, 3)}
boxed(r"x = \dfrac{8}{3}")

# 005
assert sol((x + 2)**2 - (x - 3)*(x + 3), 5*x + 1) == {12}
boxed(r"x = 12")

# 006
assert sol(3*x + 12, 2*(x + 12)) == {12} and 3*12 == 36
boxed(r"\text{Con } 12 \text{ tuổi, mẹ } 36 \text{ tuổi}")

# 007: both methods, plus a joint system check
assert sol(x / 4 - x / 5, 4) == {80}
assert sol(4*(v + 2), 5*(v - 2), v) == {18} and 4*(18 + 2) == 80
d = sp.symbols("d")
assert sp.solve([sp.Eq(d, 4*(v + 2)), sp.Eq(d, 5*(v - 2))], [d, v]) == {d: 80, v: 18}
assert TEX.count(r"\boxed{80 \text{ km}}") == 2

# 008
assert sol(x / 50 - (x + 13) / 57, 1) == {500}
assert 500 / 50 == 10 and 513 / 57 == 9
boxed(r"500 \text{ sản phẩm}")

# 009
assert sol(2*x - 3, x + 1) == {4}
eq2 = lambda mm: sp.Eq((mm + 1)*x - 3*(mm - x), mm**2 + 10)
assert set(sp.solve(eq2(m).subs(x, 4), m)) == {3, -2}
assert sp.expand((m + 2)*(m - 3)) == m**2 - m - 6
for mm in (3, -2):
    assert set(sp.solve(eq2(mm), x)) == {4}
    assert sp.expand((eq2(mm).lhs - eq2(mm).rhs)).coeff(x) != 0  # truly first-degree, unique root
assert (3 + 4, 3**2 + 3*3 + 10) == (7, 28) and (-2 + 4, 4 - 6 + 10) == (2, 8)
boxed(r"x = 4"); boxed(r"m = 3 \text{ hoặc } m = -2")
boxed(r"\text{Với } m = 3 \text{ và với } m = -2, \text{ phương trình (2) đều có nghiệm duy nhất } x = 4")

# 010
lhs = (x + 1) / 2025 + (x + 2) / 2024
rhs = (x + 3) / 2023 + (x + 4) / 2022
assert sol(lhs, rhs) == {-2026}
a = R(1, 2025) + R(1, 2024) - R(1, 2023) - R(1, 2022)
assert a < 0
boxed(r"x = -2026")

# 011
assert sol(2*x - 7, 0) == {R(7, 2)} and sol(3 - R(1, 2)*x, 0) == {6}
assert sp.Poly(x**2 - 4, x).degree() == 2 and sp.Poly(0*x + 5, x).degree() == 0
assert sp.Poly(3 - R(1, 2)*x, x).all_coeffs() == [R(-1, 2), 3] and sp.Poly(2*x - 7, x).all_coeffs() == [2, -7]
boxed(r"\text{là phương trình bậc nhất một ẩn},\ a = 2,\ b = -7,\ x = \dfrac{7}{2}")
boxed(r"\text{là phương trình bậc nhất một ẩn},\ a = -\dfrac{1}{2},\ b = 3,\ x = 6")
assert TEX.count(r"\boxed{\text{không là phương trình bậc nhất một ẩn}}") == 2

# 012
C = sp.symbols("C")
assert sol(R(9, 5)*C + 32, 95, C) == {35}
assert sol(x, R(9, 5)*x + 32) == {-40}
boxed(r"35^\circ\text{C}"); boxed(r"-40^\circ\text{C (tức là } -40^\circ\text{F)}")

# 013
assert sol(2*(x + 3) - 5, 2*x + 4) == set()  # no solution
assert sp.expand(3*(x - 1) + 2 - (3*x - 1)) == 0  # identity
boxed(r"\text{Phương trình vô nghiệm}"); boxed(r"\text{Phương trình nghiệm đúng với mọi } x")

# 014
e14 = (m - 3)*x + 2*m - 1
assert sp.solve(sp.Poly(e14, x).coeff_monomial(x), m) == [3]
assert sol(e14.subs(m, 1), 0) == {R(1, 2)}
assert e14.subs(m, 3) == 5 and sol(e14.subs(m, 3), 0) == set()
boxed(r"m \neq 3"); boxed(r"x = \dfrac{1}{2}")
boxed(r"\text{Không, vì phương trình trở thành } 0x = -5 \text{ nên vô nghiệm}")

# 015: brute force over all two-digit numbers
hits = [n for n in range(10, 100) if n // 10 == 2*(n % 10) and n - (10*(n % 10) + n // 10) == 36]
assert hits == [84] and sol(21*x - 12*x, 36) == {4}
boxed(r"84")

# 016
assert sol(R(4, 5)*x + R(9, 10)*(750000 - x), 630000) == {450000}
assert R(4, 5)*450000 + R(9, 10)*300000 == 630000
boxed(r"\text{Áo } 450\,000 \text{ đồng, quần } 300\,000 \text{ đồng}")

# 017: both methods
t = sp.symbols("t")
assert sol(40*t + 60*(t - 1), 190, t) == {R(5, 2)}
assert sol(x / 40 - (190 - x) / 60, 1) == {100} and R(100, 40) == R(5, 2)
assert 7 + R(5, 2) == R(19, 2)  # 9h30
assert TEX.count(r"\boxed{9 \text{ giờ } 30 \text{ phút}}") == 2

# 018
assert sol((x + 4)*(24 - x), x*(28 - x) + 8) == {11}
assert 2*(11 + 17) == 56 and 15*13 - 11*17 == 8
boxed(r"\text{Chiều dài } 17 \text{ m, chiều rộng } 11 \text{ m}")

# 019
e19 = sp.Eq(m**2*x + 2, 4*x + m)
assert sp.expand((m**2*x + 2 - 4*x - m) - ((m**2 - 4)*x - (m - 2))) == 0
assert set(sp.solve(e19.subs(m, 1), x)) == {R(1, 3)}
d19 = m**2*x + 2 - (4*x + m)
assert sp.expand(d19.subs(m, -2)) == 4 and e19.subs(m, -2) == sp.false  # 0x = -4: no solution
assert sp.expand(d19.subs(m, 2)) == 0 and e19.subs(m, 2) == sp.true  # 0x = 0: every x
assert sp.simplify(sp.solve(e19, x)[0] - 1 / (m + 2)) == 0  # generic m
boxed(r"x = \dfrac{1}{3}"); boxed(r"m = -2"); boxed(r"m = 2")

# 020: equation + full simulation
assert sol(1 + (x - 1) / 8, 2 + ((7*(x - 1) / 8) - 2) / 8) == {49}
left, shares, k = R(49), [], 1
while left > 0:
    s = k + (left - k) / 8
    shares.append(s); left -= s; k += 1
assert shares == [7]*7 and left == 0
boxed(r"\text{Tổng } 49 \text{ triệu đồng, } 7 \text{ nhân viên, mỗi người } 7 \text{ triệu đồng}")

# 021: angle sum
assert sol(x + (x + 20) + (2*x - 40), 180) == {50} and (50, 70, 60) == (50, 50 + 20, 2*50 - 40) and 50 > 20
boxed(r"x = 50;\ \widehat{A} = 50^\circ,\ \widehat{B} = 70^\circ,\ \widehat{C} = 60^\circ")

# 022: student's wrong step 1 gives 4x = 6
L22, R22 = 7*x - 5, 3*x + 11
assert L22.subs(x, R(3, 2)) == R(11, 2) and R22.subs(x, R(3, 2)) == R(31, 2)
assert sol(7*x - 3*x, 11 - 5) == {R(3, 2)} and sol(L22, R22) == {4} and L22.subs(x, 4) == 23
boxed(r"x = \dfrac{3}{2} \text{ không là nghiệm}"); boxed(r"\text{Sai ở Bước 1; nghiệm đúng là } x = 4")

# 023: decimals / percent
assert (R("0.6"), R("1.5"), R(15, 100), R("1.2")) == (R(3, 5), R(3, 2), R(3, 20), R(6, 5))
assert sol(R("0.6")*x - R("1.5"), R(15, 100)*x + R("1.2")) == {6}
assert R(3, 5) - R(3, 20) == R(9, 20) and R(6, 5) + R(3, 2) == R(27, 10)
boxed(r"x = 6")

# 024: equivalence by root sets
assert sol(2*x - 4, 0) == {2} and sol(x**2 - 2*x, 0) == {0, 2}
assert sol(x / 3 + 1, 0) == {-3} == sol(5*x + 15, 0)
boxed(r"\text{Không tương đương, vì } x = 0 \text{ là nghiệm của phương trình thứ hai nhưng không là nghiệm của phương trình thứ nhất}")
boxed(r"\text{Tương đương, vì cùng có tập nghiệm } \{-3\}")

# 025: odd coefficients 1..19
odds = list(range(1, 20, 2))
assert len(odds) == 10 == (19 - 1) // 2 + 1 and sum(odds) == 100 == 5*20
assert sol(sum(k*x for k in odds) - 120, 4*x + 360) == {5} and 100*5 - 120 == 380 == 4*5 + 360
boxed(r"x = 5")

# 026: A = B, A + B = 0
A26, B26 = 2*x + 5, 17 - x
assert sol(A26, B26) == {4} and A26.subs(x, 4) == 13 == B26.subs(x, 4)
assert sol(A26 + B26, 0) == {-22} and A26.subs(x, -22) == -39 and B26.subs(x, -22) == 39
assert TEX.count(r"\boxed{x = 4}") == 3  # 009a, 026a, 027
boxed(r"x = -22")

# 027: nested fractions
L27 = (x - (x - 2) / 4) / 3
R27 = (((2*x + 1) / 3 - 1) / 2) + R(1, 6)
assert sp.simplify(L27 - (3*x + 2) / 12) == 0 and sp.simplify(R27 - (2*x - 1) / 6) == 0
assert sol(L27, R27) == {4} and L27.subs(x, 4) == R(7, 6) == R27.subs(x, 4)

# 028: unique root for every m
e28 = sp.Eq((m**2 + 3)*x - 3, 2*m*(x + 1))
assert sp.expand((e28.lhs - e28.rhs) - ((m**2 - 2*m + 3)*x - (2*m + 3))) == 0
assert sp.expand((m - 1)**2 + 2 - (m**2 - 2*m + 3)) == 0
assert sp.solve(m**2 - 2*m + 3, m) and all(not r.is_real for r in sp.solve(m**2 - 2*m + 3, m))
assert sp.simplify(sp.solve(e28, x)[0] - (2*m + 3) / (m**2 - 2*m + 3)) == 0
assert set(sp.solve(e28.subs(x, 1), m)) == {0, 4}
for mm in (0, 4):
    assert set(sp.solve(e28.subs(m, mm), x)) == {1}
boxed(r"\text{Vì } m^2 - 2m + 3 = (m - 1)^2 + 2 > 0 \text{ nên phương trình luôn có nghiệm duy nhất } x = \dfrac{2m + 3}{m^2 - 2m + 3}")
boxed(r"m = 0 \text{ hoặc } m = 4")

# 029: integer roots, brute force over a wide m range
e29 = sp.Eq(m*x - 4, x + 2*m)
assert sp.expand((e29.lhs - e29.rhs) - ((m - 1)*x - (2*m + 4))) == 0
assert set(sp.solve(e29.subs(m, 3), x)) == {5} and sp.solve(e29.subs(m, 1), x) == []
good = {}
for mm in range(-100, 101):
    r = sp.solve(e29.subs(m, mm), x)
    if len(r) == 1 and r[0].is_integer:
        good[mm] = r[0]
assert good == {-5: 1, -2: 0, -1: -1, 0: -4, 2: 8, 3: 5, 4: 4, 7: 3}, good
boxed(r"x = 5"); boxed(r"m \in \{-5;\ -2;\ -1;\ 0;\ 2;\ 3;\ 4;\ 7\}")

# 030: x = 2 must be the ONLY root
e30 = sp.Eq(m*(x - m), 2*(x - 2))
assert sp.expand((e30.lhs - e30.rhs) - ((m - 2)*x - (m**2 - 4))) == 0
assert set(sp.solve(e30.subs(x, 2), m)) == {0, 2}
assert set(sp.solve(e30.subs(m, 0), x)) == {2} and e30.subs(m, 2) == sp.true  # m = 2: every x
boxed(r"m = 0")

# 031: telescoping sum
S31 = sum(R(1, n*(n + 2)) for n in range(1, 24, 2))
assert S31 == R(12, 25) and len(range(1, 24, 2)) == 12
assert sol((x - 1)*S31, (2*x + 18) / 25) == {3} and 2*S31 == R(24, 25)
boxed(r"x = 3")

assert TEX.count(r"\boxed{") == 51 + 1, TEX.count(r"\boxed{")  # answers + header comment
print("8-phuong-trinh-bac-nhat: all 31 problems verified OK")
