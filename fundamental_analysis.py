def get_holding_category(fii_holdings, dii_holdings):
    """
    Categorizes based on back-to-back 2 quarters increase.
    fii_holdings: list of holdings [Q-3, Q-2, Q-1, Q]
    """
    fii_increased = False
    if len(fii_holdings) >= 3:
        # Increase from Q-2 to Q-1 AND from Q-1 to Q
        if fii_holdings[-1] > fii_holdings[-2] and fii_holdings[-2] > fii_holdings[-3]:
            fii_increased = True

    dii_increased = False
    if len(dii_holdings) >= 3:
        if dii_holdings[-1] > dii_holdings[-2] and dii_holdings[-2] > dii_holdings[-3]:
            dii_increased = True

    if fii_increased and dii_increased:
        return "Both"
    elif fii_increased:
        return "FII"
    elif dii_increased:
        return "DII"
    return "All"

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

    category = get_holding_category(
        fundamentals.get('FII_Holdings', []),
        fundamentals.get('DII_Holdings', [])
    )

    if category != "All":
        return True, category.lower()

    return False, None
