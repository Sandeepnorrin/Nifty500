def get_holding_category(fii_holdings, dii_holdings):
    """
    Categorizes based on back-to-back 2 quarters increase.
    fii_holdings: list of holdings [Q-3, Q-2, Q-1, Q]

    Eligibility (for scan inclusion): Q > Q-1 > Q-2 (for either FII or DII)
    Category Label:
    - "Both" if both FII and DII increased in latest quarter (Q > Q-1).
    - "FII" if only FII increased in latest quarter.
    - "DII" if only DII increased in latest quarter.
    """
    fii_eligible = False
    if len(fii_holdings) >= 3:
        if fii_holdings[-1] > fii_holdings[-2] and fii_holdings[-2] > fii_holdings[-3]:
            fii_eligible = True

    dii_eligible = False
    if len(dii_holdings) >= 3:
        if dii_holdings[-1] > dii_holdings[-2] and dii_holdings[-2] > dii_holdings[-3]:
            dii_eligible = True

    if fii_eligible and dii_eligible:
        return "Both"
    elif fii_eligible:
        return "FII"
    elif dii_eligible:
        return "DII"

    return "None"

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

    if category != "None":
        return True, category.lower()

    return False, None
