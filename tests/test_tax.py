from apple_receipt_to_ynab.tax import allocate_proportional_milliunits


def test_allocate_tax_largest_remainder_reconciles_exactly() -> None:
    base = [10990, 2990]
    tax = 1120
    allocated = allocate_proportional_milliunits(base, tax)
    assert sum(allocated) == tax
    assert allocated == [880, 240]


def test_allocate_zero_tax() -> None:
    allocated = allocate_proportional_milliunits([1000, 2000, 3000], 0)
    assert allocated == [0, 0, 0]

