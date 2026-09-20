from decimal import Decimal, getcontext


def approximate_pi(terms: int) -> Decimal:
    getcontext().prec = 50
    total = Decimal(0)
    sign = 1
    for n in range(terms):
        denom = 2 * n + 1
        term = Decimal(1) / Decimal(denom)
        total += term if sign > 0 else -term
        sign *= -1
    return total * 4


if __name__ == '__main__':
    result = approximate_pi(1_000_000)
    print(result)
