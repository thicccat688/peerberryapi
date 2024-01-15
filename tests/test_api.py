import unittest.mock
from decimal import Decimal
from peerberrypy.api import API

from datetime import date
import pandas as pd
import os


peerberry_client = API(
    email=os.getenv(key='PEERBERRY_EMAIL'),
    password=os.getenv(key='PEERBERRY_PASSWORD'),
    tfa_secret=os.getenv(key='PEERBERRY_TFA_SECRET'),
)

current_year = date.today().strftime('%Y')
next_year = (date.today() + pd.DateOffset(years=1)).strftime('%Y')


def test_profile():
    assert isinstance(peerberry_client.get_profile(), dict)


def test_loyalty():
    assert isinstance(peerberry_client.get_loyalty_tier(), dict)


def test_overview():
    assert isinstance(peerberry_client.get_overview(), dict)


def test_profit_overview():
    assert isinstance(
        peerberry_client.get_profit_overview(
            start_date=date(2022, 8, 21),
            end_date=date(2022, 9, 21),
            periodicity='day',
        ),
        pd.DataFrame,
    )


def test_investment_status():
    assert isinstance(peerberry_client.get_investment_status(), dict)


def test_loans():
    with unittest.mock.patch('peerberrypy.api.API.get_loans_page') as get_loans_page:
        get_loans_page.return_value = {
            'data': [() for _ in range(40)],
        }
        assert isinstance(peerberry_client.get_loans(1000), pd.DataFrame)
        assert get_loans_page.call_count == 1000/40


def test_loans_page():
    assert isinstance(
        peerberry_client.get_loans_page(
            page_num=0,
        ),
        dict,
    )


def test_loan_details():
    assert isinstance(peerberry_client.get_loan_details(loan_id=1), dict)


def test_loan_agreement():
    assert isinstance(peerberry_client.get_agreement(loan_id=39125759, lang='en'), bytes)


def test_investments():
    assert isinstance(
        peerberry_client.get_investments(
            quantity=40,
            current=True,
            max_interest_rate=Decimal(20),
            min_interest_rate=Decimal(10),
            countries=['Kazakhstan', 'Lithuania'],
        ),
        pd.DataFrame,
    )

    assert isinstance(
        peerberry_client.get_investments(
            quantity=40,
            current=False,
            max_interest_rate=Decimal(20),
            min_interest_rate=Decimal(10),
            countries=['Kazakhstan', 'Lithuania'],
        ),
        pd.DataFrame,
    )

    assert isinstance(peerberry_client.get_mass_investments(), pd.DataFrame)


def test_summary():
    assert isinstance(
        peerberry_client.get_account_summary(
            start_date=date(int(current_year), 1, 1),
            end_date=date(int(next_year), 1, 1),
        ),
        dict,
    )


def test_transactions():
    assert isinstance(
        peerberry_client.get_transactions(),
        pd.DataFrame,
    )


def test_mass_transactions():
    assert isinstance(
        peerberry_client.get_mass_transactions(
            quantity=1000,
            start_date=date(int(current_year), 1, 1),
            end_date=date(int(next_year), 1, 1),
        ),
        pd.DataFrame,
    )


def test_countries():
    assert isinstance(peerberry_client.get_countries(), dict)


def test_originators():
    assert isinstance(peerberry_client.get_originators(), dict)


def test_logout():
    assert isinstance(peerberry_client.logout(), str)
