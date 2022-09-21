from peerberry.endpoints import ENDPOINTS
from peerberry.request_handler import RequestHandler
from peerberry.exceptions import InvalidCredentials, InvalidPeriodicity, InsufficientFunds, InvalidSort
from peerberry.constants import CONSTANTS
from datetime import date
from typing import Union
import pandas as pd
import pyotp
import math


class API:
    def __init__(
            self,
            email: str,
            password: str,
            tfa_secret: str = None,
    ):
        """
        Peerberry API to execute all desired Peerberry functionalities via API calls
        :param email: Email account was created with
        :param password: Password account was created with
        :param tfa_secret: Base32 secret used for two-factor authentication (Only mandatory if account has 2fa enabled)
        """

        self.email = email
        self.__password = password
        self.__tfa_secret = tfa_secret

        # Initialize API session, authenticate & get access token
        self.__session = RequestHandler()
        self.__session.add_header({'Authorization': self.__get_access_token()})

    def get_profile(self) -> dict:
        """
        :return: Basic information, accounts & balance information
        """

        return self.__session.request(
            url=ENDPOINTS.PROFILE_URI,
        )

    def get_loyalty_tier(self) -> dict:
        """
        :return: Tier, extra return in percentage, the max amount and the minimum amount to be in the tier
        """

        response = self.__session.request(
            url=ENDPOINTS.LOYALTY_URI,
        )

        # Remove all tiers with locked set to true
        unlocked_tiers = list(filter(lambda obj: obj['locked'] is False, response['items']))

        # Get the highest unlocked tier
        top_available_tier = unlocked_tiers[-1]

        return {
            'tier': top_available_tier['title'].rstrip(),
            'extra_return': top_available_tier['percent'],
            'max_amount': top_available_tier['maxAmount'],
            'min_amount': top_available_tier['minAmount'],
        }

    def get_overview(self) -> dict:
        """
        :return: Available balance, total invested, total profit, current investments, net annual return, etc.
        """

        return self.__session.request(
            url=ENDPOINTS.OVERVIEW_URI,
        )

    def get_profit_overview(
            self,
            start_date: date,
            finish_date: date,
            periodicity: str = 'day',
            raw: bool = False,
    ) -> Union[pd.DataFrame, list]:
        """
        :param start_date: First date of profit data
        :param finish_date: Final date of profit data
        :param periodicity: Intervals to get profit data from (Daily, monthly or on a yearly basis)
        :param raw: Returns python list if True or pandas DataFrame if False (False by default)
        :return: Profit overview for portfolio on a daily, monthly or yearly basis
        """

        periodicites = CONSTANTS.PERIODICITIES

        if periodicity not in periodicites:
            raise InvalidPeriodicity(f'Periodicity must be one of the following: {", ".join(periodicites)}')

        profit_overview = self.__session.request(
            url=f'{ENDPOINTS.PROFIT_OVERVIEW_URI}/{start_date}/{finish_date}/{periodicity}',
        )

        return profit_overview if raw else pd.DataFrame(profit_overview)

    def get_investment_status(self) -> dict:
        """
        :return: Percentage of funds in current loans and late loans (In 1-15, 16-30, and 31-60 day intervals)
        """

        return self.__session.request(
            url=ENDPOINTS.INVESTMENTS_STATUS_URI,
        )

    def get_loans(
            self,
            quantity: int,
            max_remaining_term: int = None,
            min_remaining_term: int = None,
            max_interest_rate: float = None,
            min_interest_rate: float = None,
            max_available_amount: float = None,
            min_available_amount: float = None,
            countries: list = None,
            originators: list = None,
            loan_types: list = None,
            sort: str = 'loan_amount',
            ascending_sort: bool = False,
            group_guarantee: bool = True,
            exclude_invested_loans: bool = True,
            raw: bool = False,
    ) -> Union[pd.DataFrame, list]:
        """
        :param quantity: Amount of loans to fetch
        :param max_remaining_term: Set maximum remaining term to fetch loan
        :param min_remaining_term: Set minimum remaining term to fetch loan
        :param max_interest_rate: Set maximum interest rate to fetch loan
        :param min_interest_rate: Set minimum interest rate to fetch loan
        :param max_available_amount: Set maximum available investment amount to fetch loan
        :param min_available_amount: Set minimum available investment amount to fetch loan
        :param countries: Filter loans by country of origin (Gets loans from all countries by default)
        :param originators: Filter loans by originator (Gets loans from all originators by default)
        :param loan_types: Filter loans by type (Short-term, long-term, real estate, leasing, and business)
        :param sort: Sort by loan attributes (By amount available for investment, interest rate, term, etc.)
        :param ascending_sort: Sort by ascending order (By default sorts in descending order)
        :param group_guarantee: Restrict loans to only those with a group guarantee
        :param exclude_invested_loans: Exclude loans that have been invested in previously
        :param raw: Returns python list if True or pandas DataFrame if False (False by default)
        :return: All available loans for investment according to specified parameters
        """

        if quantity <= 0:
            raise ValueError('You need to fetch at least 1 loan.')

        if sort not in CONSTANTS.LOAN_SORT_TYPES:
            raise InvalidSort(f'Loans can only be sorted by: {", ".join(CONSTANTS.LOAN_SORT_TYPES)}')

        loan_params = {
            'sort': sort if ascending_sort else f'-{sort}',
            'pageSize': 40 if quantity > 40 else quantity,
            'offset': 0,
        }

        if max_remaining_term is not None:
            loan_params['maxRemainingTerm'] = max_remaining_term

        if min_remaining_term is not None:
            loan_params['minRemainingTerm'] = min_remaining_term

        if max_interest_rate is not None:
            loan_params['maxInterestRate'] = max_interest_rate

        if min_interest_rate is not None:
            loan_params['minInterestRate'] = min_interest_rate

        if max_available_amount is not None:
            loan_params['maxRemainingAmount'] = max_available_amount

        if min_available_amount is not None:
            loan_params['minRemainingAmount'] = min_available_amount

        if group_guarantee is not None:
            loan_params['groupGuarantee'] = 1

        if exclude_invested_loans is not None:
            loan_params['hideInvested'] = 1

        # Add country filters to query parameters
        if countries:
            for idx, country in enumerate(countries):
                loan_params[f'countryIds[{idx}]'] = CONSTANTS.COUNTRIES_ID[country]

        if originators:
            for idx, originator in enumerate(originators):
                id_ = CONSTANTS.get_originators()[originator]

                if isinstance(id_, list):
                    for sub_id, originator_id in enumerate(id_):
                        loan_params[f'loanOriginators[{idx+sub_id}]'] = originator_id

                    continue

                loan_params[f'loanOriginators[{idx}]'] = id_

        # Add loan type filters to query parameters
        if loan_types:
            for idx, type_ in enumerate(loan_types):
                loan_params[f'loanTermId[{idx}]'] = CONSTANTS.LOAN_SORT_TYPES[type_]

        loans = []

        for _ in range(math.ceil(quantity / 40)):
            loans_data = self.__session.request(
                url=ENDPOINTS.LOANS_URI,
                params=loan_params,
            )['data']

            # Extend current loan list with new loans
            loans.extend(loans_data)

            loan_params['offset'] += 40

        return loans if raw else pd.DataFrame(loans)

    def get_loan_details(
            self,
            loan_id: int,
            raw: bool = False,
    ) -> dict:
        """
        :param loan_id: ID of loan to get details of
        :param raw: Returns python list if True or pandas DataFrame if False (False by default)
        :return: The borrower's data, the loan's data, and the repayment schedule
        """

        credit_data = self.__session.request(
            url=f'{ENDPOINTS.LOANS_URI}/{loan_id}',
        )

        schedule_data = credit_data['schedule']['data']

        return {
            'borrower_data': credit_data.get('borrower'),
            'loan_data': credit_data.get('loan'),
            'schedule_data': schedule_data if raw else pd.DataFrame(schedule_data),
        }

    def purchase_loan(
            self,
            loan_id: int,
            amount: int,
    ) -> str:
        """
        :param loan_id: ID of loan to purchase
        :param amount: Amount to invest in loan (Amount denominated in €)
        :return: Success message upon purchasing loan
        """

        self.__session.request(
            url=f'{ENDPOINTS.LOANS_URI}/{loan_id}',
            method='POST',
            data={'amount': str(amount)},
            exception_type=InsufficientFunds,
        )

        return f'Successfully invested €{amount} in loan {loan_id}.'

    def get_investments(
            self,
            quantity: int,
            max_date_of_purchase: int = None,
            min_date_of_purchase: int = None,
            max_interest_rate: float = None,
            min_interest_rate: float = None,
            max_invested_amount: float = None,
            min_invested_amount: float = None,
            countries: list = None,
            loan_types: list = None,
            sort: str = 'loan_amount',
            ascending_sort: bool = False,
            current: bool = True,
            raw: bool = False,
    ) -> Union[pd.DataFrame, list]:
        """
        Note:
        If you're going to get a lot of investments at once, it's recommended to use the get_mass_investments
        function, it'll import the data as an Excel and convert it to a pandas DataFrame or as a python list
        :param quantity: Amount of investments to fetch
        :param max_date_of_purchase: Set maximum date of purchase to fetch loan
        :param min_date_of_purchase: Set minimum date of purchase to fetch loan
        :param max_interest_rate: Set maximum interest rate to fetch loan
        :param min_interest_rate: Set minimum interest rate to fetch loan
        :param max_invested_amount: Set maximum invested amount to fetch loan
        :param min_invested_amount: Set minimum invested amount to fetch loan
        :param countries: Filter investments by country of origin (Gets investments from all countries by default)
        :param loan_types: Filter investments by type (Short-term, long-term, real estate, leasing, and business)
        :param sort: Sort by loan attributes (By amount available for investment, interest rate, term, etc.)
        :param ascending_sort: Sort by ascending order (By default sorts in descending order)
        :param current: Fetch current investments or finished investments (Gets current investments by default)
        :param raw: Returns python list if True or pandas DataFrame if False (False by default)
        :return: All available investments for investment according to specified parameters
        """

        if quantity <= 0:
            raise ValueError('You need to fetch at least 1 investment.')

        if sort not in CONSTANTS.LOAN_SORT_TYPES:
            raise InvalidSort(f'Loans can only be sorted by: {", ".join(CONSTANTS.LOAN_SORT_TYPES)}')

        investment_params = {
            'sort': sort if ascending_sort else f'-{sort}',
            'pageSize': 40 if quantity > 40 else quantity,
            'type': 'CURRENT' if current else 'FINISHED',
            'offset': 0,
        }

        if max_date_of_purchase is not None:
            investment_params['maxDateOfPurchase'] = max_date_of_purchase

        if min_date_of_purchase is not None:
            investment_params['minDateOfPurchase'] = min_date_of_purchase

        if max_interest_rate is not None:
            investment_params['maxInterestRate'] = max_interest_rate

        if min_interest_rate is not None:
            investment_params['minInterestRate'] = min_interest_rate

        if max_invested_amount is not None:
            investment_params['maxAmount'] = max_invested_amount

        if min_invested_amount is not None:
            investment_params['minAmount'] = min_invested_amount

        if countries:
            for idx, country in enumerate(countries):
                investment_params[f'countryIds[{idx}]'] = CONSTANTS.COUNTRIES_ID[country]

        # Add loan type filters to query parameters
        if loan_types:
            for idx, type_ in enumerate(loan_types):
                investment_params[f'loanTermId[{idx}]'] = CONSTANTS.LOAN_SORT_TYPES[type_]

        investments_data = self.__session.request(
            url=ENDPOINTS.INVESTMENTS_URI,
            params=investment_params,
        )['data']

        return investments_data if raw else pd.DataFrame(investments_data)

    def get_mass_investments(
            self,
            quantity: int,
            sort: str = 'loan_amount',
            ascending_sort: bool = False,
            current: bool = True,
    ) -> Union[pd.DataFrame, list]:
        """
        :param quantity:
        :param sort: Sort by loan attributes (By amount available for investment, interest rate, term, etc.)
        :param ascending_sort: Sort by ascending order (By default sorts in descending order)
        :param current:
        :return:
        """
        investment_params = {
            'type': 'CURRENT' if current else 'FINISHED',
            'lang': 'en',
        }

        investments = self.__session.request(
            url=f'{ENDPOINTS.INVESTMENTS_URI}/export',
            params=investment_params,
            output='bytes',
        )

        # investment_data = pd.read_excel(
        #     io=investments,
        #     sheet_name='My investments' if current else 'Finished investments',
        # ).sort_values(by=sort.value, ascending=ascending_sort).to_dict('records')

    def __get_access_token(self) -> str:
        login_data = {
            'email': self.email,
            'password': self.__password,
        }

        login_response = self.__session.request(
            url=ENDPOINTS.LOGIN_URI,
            method='POST',
            data=login_data,
            exception_type=InvalidCredentials,
        )

        tfa_response_token = login_response.get('tfa_token')

        if self.__tfa_secret is None:
            return f'Bearer {tfa_response_token}'

        totp_data = {
            'code': pyotp.TOTP(self.__tfa_secret).now(),
            'tfa_token': tfa_response_token,
        }

        totp_response = self.__session.request(
            url=ENDPOINTS.TFA_URI,
            method='POST',
            data=totp_data,
        )

        access_token = totp_response.get('access_token')

        # Set authorization header with JWT bearer token
        return f'Bearer {access_token}'


client = API(
    email='marcoperestrello@gmail.com',
    password='%kPevYbI6faQ0165pc24',
    tfa_secret='34KHNWOD326XBCEQIKRZ7HMDOY6WUY5A',
)

print(client.get_loans(quantity=100, originators=['Litelektra']))
