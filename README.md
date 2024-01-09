## Peerberrypy

The peerberrypy package is a Python API wrapper for the Peerberry platform.
Peerberry currently has no API documentation and some endpoints could be simplified/optimized, which is one of the main goals of this project.

Peerberry platform: https://peerberry.com/

## Requirements 

Python 3.8+

Main dependencies:
- cloudscraper for accessing the API without getting blocked by CF anti-DDOS,

Optional dependencies:
- pandas for the large data handling,
- openpyxl for parsing spreadsheets supplied by Peerberry,
- pyotp for handling two-factor authentication.

## Installation

```bash
pip install peerberrypy
```

Replace with `peerberrypy[pandas]` to install pandas and openpyxl, `peerberrypy[otp]` to install pyotp, or `peerberrypy[pandas,otp]` to install all.

## Usage

```python
from peerberrypy import API


# Authenticate to the API client
api_client = API(
  email='YOUR EMAIL HERE',
  password='YOUR PASSWORD HERE',
  tfa_secret='YOUR BASE32 TFA SECRET HERE',  # This is only required if you have two-factor authentication enabled on your account
)

# Gets investor profile data
print(api_client.get_profile())

# Gets 100 of loans that are from the "Smart Pozyczka PL" originator
print(api_client.get_loans(quantity=100, originators=['Smart Pozyczka PL']))

# Gets 100 of your current investments from Kazakhstan and Lithuania
print(api_client.get_investments(quantity=100, current=True, countries=['Kazakhstan', 'Lithuania'])
```

## API functions

<pre>
Investor/portfolio data functions:
  get_profile -> Gets investor profile.
  get_loyalty_tier -> Gets loyalty tier, tier requirements, and the tier's benefits.
  get_overview -> Gets portfolio overview (Balance, total invested, total profit, net annual return, etc.).
  get_profit_overview -> Gets portfolio's profit on a daily, monthly or yearly basis (Data used in your profile's profit chart).
  get_investment_status -> Gets percentage of funds in different investment statuses (Current, late by 1-15 days, 16-30 days, and 31-60 days).
  get_overview_originators -> Gets originators overview for portfolio.
  get_overview_investment_types -> Gets investment types overview for portfolio.
  get_overview_countries -> Gets country overview for portfolio.
 
Marketplace/loan data functions:
  get_loans & get_loans_page -> Gets loans available for investment in the Peerberry marketplace according to the filters you specify. get_loans_page also returns metadata.
  get_loan_details -> Gets available information about the loan, the borrower, and the loan's payments schedule.
  purchase_loan -> Invests in a loan with the amount you specify.

Investment data functions:
  get_investments -> Gets current or finished investments in accordance to the filters you specify (It's recommended to use the get_mass_investments function when fetching more than ~350 investments at once).
  get_mass_investments -> Gets current or finished investments either as an Excel or as a Pandas DataFrame in accordance with the filters you specify (It's recommended to use this function when fetching more than ~350 investments at once).
  get_account_summary -> Gets account's transaction summary (Invested funds, principal payments, interest payments, deposits, etc.).

Transaction data functions:
  get_transactions -> Gets transactions as a Pandas DataFrame in accordance with the filters you specify.
  get_mass_transactions -> Gets transactions either as an Excel or as a Pandas DataFrame.
  
Authentication functions:
  login -> Logs in to Peerberry's API and assigns your session an access token. Use is not recommended as it's done automatically when initializing API instance.
  logout -> Logs out of Peerberry and revokes your access token. Recommended to use after you finish all your operations.

Note:
The authentication logic is executed automatically upon initializing the API instance, only logout needs to be done manually.
The login is executed automatically upon initializing the API instance, only logout needs to be done manually (Login is still possible to do manually, but not recommended).
</pre>

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.
Please make sure to update tests as appropriate.

## License
[MIT](https://choosealicense.com/licenses/mit/)
