"""One-off: connect your eBay seller account (OAuth). Saves .ebay_token.json.

  python ebay_auth.py                     # step 1: prints the sign-in link
  python ebay_auth.py "<redirected URL>"  # step 2: paste the URL eBay lands on after Agree
"""
import sys

from gearlister.ebay import EbayAuth


def main():
    auth = EbayAuth()
    if len(sys.argv) > 1:
        pasted = " ".join(sys.argv[1:]).strip()
    else:
        print("1. Open this URL in your browser and sign in to the eBay account you sell from:\n")
        print(auth.consent_url())
        print("\n2. After you click Agree, eBay redirects to its accept page.")
        print("   Copy the whole URL from the address bar and run:\n")
        print('   python ebay_auth.py "<that URL>"')
        try:
            pasted = input("\nOr paste it here: ").strip()
        except (EOFError, OSError):
            return
        if not pasted:
            return
    code = pasted
    if "code=" in pasted:
        code = pasted.split("code=", 1)[1].split("&", 1)[0]
    tok = auth.exchange_code(code)
    print(f"\nConnected. Access token valid {tok.get('expires_in')}s, refresh token saved "
          f"(valid ~18 months). You can now run ebay_policies.py and list_ebay.py.")


if __name__ == "__main__":
    main()
