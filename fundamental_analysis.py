def filter_fundamentals(fundamentals, roe_min, roce_min):
    """
    Checks if stock meets ROE and ROCE criteria and
    if FII/DII holdings increased in back-to-back 2 quarters.
    """
    if not fundamentals:
        return False, None

    # ROE/ROCE check
    roe = fundamentals.get('ROE', 0)
    roce = fundamentals.get('ROCE', 0)

    if roe < roe_min or roce < roce_min:
        return False, None

    # FII/DII check (back-to-back 2 quarters increase)
    fii = fundamentals.get('FII_Holdings', [])
    dii = fundamentals.get('DII_Holdings', [])

    fii_increased = False
    if len(fii) >= 3:
        # 3 quarters: [Q-2, Q-1, Q]
        # Increase from Q-2 to Q-1 AND from Q-1 to Q
        if fii[-1] > fii[-2] and fii[-2] > fii[-3]:
            fii_increased = True

    dii_increased = False
    if len(dii) >= 3:
        if dii[-1] > dii[-2] and dii[-2] > dii[-3]:
            dii_increased = True

    category = None
    if fii_increased and dii_increased:
        category = "both"
    elif fii_increased:
        category = "fii"
    elif dii_increased:
        category = "dii"

    if category:
        return True, category

    return False, None
