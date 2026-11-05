"""Prints your eBay business policy IDs (payment / return / postage) to put in .env.

  python ebay_policies.py
"""
from gearlister.ebay import EbayAuth, list_policies


def main():
    pol = list_policies(EbayAuth())
    for kind, key, env_name in (
        ("payment", "paymentPolicyId", "EBAY_PAYMENT_POLICY_ID"),
        ("return", "returnPolicyId", "EBAY_RETURN_POLICY_ID"),
        ("shipping", "fulfillmentPolicyId", "EBAY_SHIPPING_POLICY_ID"),
    ):
        print(f"\n{kind.upper()} policies  ->  {env_name}=")
        rows = pol[kind]
        if not rows:
            print("  (none - create one in Seller Hub > Account > Business policies)")
        for p in rows:
            print(f"  {p.get(key)}  {p.get('name')}")


if __name__ == "__main__":
    main()
