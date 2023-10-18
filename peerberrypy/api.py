import decimal
import functools

from peerberrypy.endpoints import ENDPOINTS
from peerberrypy.request_handler import RequestHandler
from peerberrypy.exceptions import InvalidCredentials, InvalidPeriodicity, InsufficientFunds, InvalidSort, \
    InvalidType, PeerberryException
from peerberrypy.constants import CONSTANTS
from peerberrypy.utils import Utils

from typing import Union, Optional, List
from datetime import date
import pandas as pd
import warnings
import pyotp
import math


class API:
    def __init__(
            self,
            email: Optional[str] = None,
            password: Optional[str] = None,
            tfa_secret: Optional[str] = None,
            access_token: Optional[str] = None,
    ):
        """
        Peerberry API wrapper with all relevant Peerberry functionalities.
        :param email: Account's email
        :param password: Account's password
        :param tfa_secret: Base32 secret used for two-factor authentication
        :param access_token: Access token used to authenticate to the API (Optional; Only pass the JWT for it to work!)
        (Only mandatory if account has two-factor authentication enabled)
        """

        self.email = email
        self._password = password
        self._tfa_secret = tfa_secret

        # Initialize HTTP session & authenticate to API
        self._session = RequestHandler()
        self.access_token = access_token

        if not access_token:
            if self.email is None:
                raise ValueError('Invalid email.')

            if self._password is None:
                raise ValueError('Invalid password.')

            if not self._tfa_secret:
                warnings.warn('Using two-factor authentication with your Peerberry account is highly recommended.')

        self.login()

    def get_profile(self) -> dict:
        """
        :return: Basic information, accounts & balance information
        """

        return Utils.parse_peerberry_items(self._session.request(url=ENDPOINTS.PROFILE_URI))

    def get_loyalty_tier(self) -> dict:
        """
        :return: Tier, extra return in percentage, the max amount and the minimum amount to be in the tier
        """

        response = self._session.request(
            url=ENDPOINTS.LOYALTY_URI,
        )

        # Remove all tiers with locked set to true
        unlocked_tiers = list(filter(lambda obj: obj['locked'] is False, response['items']))

        # Get the highest unlocked tier
        top_available_tier = unlocked_tiers[-1] if len(unlocked_tiers) > 0 else None

        return {
            'tier': top_available_tier['title'].rstrip() if top_available_tier else None,
            'extra_return': f'{top_available_tier["percent"]}%',
            'max_amount': top_available_tier['maxAmount'],
            'min_amount': top_available_tier['minAmount'],
        }

    def get_overview(self) -> dict:
        """
        :return: Available balance, total invested, total profit, current investments, net annual return, etc.
        """

        return Utils.parse_peerberry_items(
            self._session.request(
                url=ENDPOINTS.OVERVIEW_URI,
            )
        )

    def get_profit_overview(
            self,
            start_date: date,
            end_date: date,
            periodicity: str = 'day',
            raw: bool = False,
    ) -> Union[pd.DataFrame, list]:
        """
        :param start_date: Start date of profit data
        :param end_date: End date of profit data
        :param periodicity: Intervals to get profit data from (Daily, monthly or on a yearly basis)
        :param raw: Returns python list if True or pandas DataFrame if False (False by default)
        :return: Profit overview for portfolio on a daily, monthly or yearly basis
        """

        periodicities = CONSTANTS.PERIODICITIES

        if periodicity not in periodicities:
            raise InvalidPeriodicity(f'Periodicity must be one of the following: {", ".join(periodicities)}')

        profit_overview = self._session.request(
            url=f'{ENDPOINTS.PROFIT_OVERVIEW_URI}/{start_date}/{end_date}/{periodicity}',
        )

        return profit_overview if raw else pd.DataFrame(profit_overview)

    def get_investment_status(self) -> dict:
        """
        :return: Percentage of funds in current loans and late loans (In 1-15, 16-30, and 31-60 day intervals)
        """

        return Utils.parse_peerberry_items(self._session.request(url=ENDPOINTS.INVESTMENTS_STATUS_URI))

    def get_loans(
            self,
            quantity: int,
            start_page: int = 0,
            max_remaining_term: Optional[int] = None,
            min_remaining_term: Optional[int] = None,
            max_interest_rate: Optional[decimal.Decimal] = None,
            min_interest_rate: Optional[decimal.Decimal] = None,
            max_available_amount: Optional[decimal.Decimal] = None,
            min_available_amount: Optional[decimal.Decimal] = None,
            countries: Optional[List[str]] = None,
            originators: Optional[List[str]] = None,
            loan_types: Optional[List[str]] = None,
            sort: str = 'loan_amount',
            ascending_sort: bool = False,
            group_guarantee: Optional[bool] = None,
            exclude_invested_loans: Optional[bool] = None,
            raw: bool = False,
    ) -> Union[pd.DataFrame, List[dict]]:
        """
        :param quantity: Amount of loans to fetch
        :param start_page: Number of start page to start getting loans from
        :param max_remaining_term: Maximum remaining term to fetch loan
        :param min_remaining_term: Minimum remaining term to fetch loan
        :param max_interest_rate: Maximum interest rate to fetch loan
        :param min_interest_rate: Minimum interest rate to fetch loan
        :param max_available_amount: Maximum available investment amount to fetch loan
        :param min_available_amount: Minimum available investment amount to fetch loan
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
        argv = locals()
        if quantity <= 0:
            raise ValueError('You need to fetch at least 1 loan.')

        page_size = min(CONSTANTS.MAX_LOAN_PAGE_SIZE, quantity)

        argv.pop('quantity', None)
        argv.pop('start_page', None)
        do_get_loans_page = functools.partial(self.get_loans_page, **argv)

        loans = []

        max_page_size = CONSTANTS.MAX_LOAN_PAGE_SIZE
        total_pages = math.ceil(quantity / max_page_size)

        for page_num in range(total_pages):
            remaining_items = quantity - (page_num * max_page_size)
            page_size = min(remaining_items, max_page_size)
            loans_data = do_get_loans_page(page_num)['data']

            if len(loans_data) == 0:
                break

            # Extend current loan list with new loans
            loans.extend(loans_data)

        return loans if raw else pd.DataFrame(loans)

    def get_loans_page(
            self,
            page_num: int,
            quantity: int = CONSTANTS.MAX_LOAN_PAGE_SIZE,
            max_remaining_term: Optional[int] = None,
            min_remaining_term: Optional[int] = None,
            max_interest_rate: Optional[decimal.Decimal] = None,
            min_interest_rate: Optional[decimal.Decimal] = None,
            max_available_amount: Optional[decimal.Decimal] = None,
            min_available_amount: Optional[decimal.Decimal] = None,
            countries: Optional[List[str]] = None,
            originators: Optional[List[str]] = None,
            loan_types: Optional[List[str]] = None,
            sort: str = 'loan_id',
            ascending_sort: bool = False,
            group_guarantee: Optional[bool] = None,
            exclude_invested_loans: Optional[bool] = None,
    ) -> dict:
        """
        :param page_num: Number of start page to start getting loans from
        :param quantity: Number of loans to fetch
        :param max_remaining_term: Maximum remaining term to fetch loan
        :param min_remaining_term: Minimum remaining term to fetch loan
        :param max_interest_rate: Maximum interest rate to fetch loan
        :param min_interest_rate: Minimum interest rate to fetch loan
        :param max_available_amount: Maximum available investment amount to fetch loan
        :param min_available_amount: Minimum available investment amount to fetch loan
        :param countries: Filter loans by country of origin (Gets loans from all countries by default)
        :param originators: Filter loans by originator (Gets loans from all originators by default)
        :param loan_types: Filter loans by type (Short-term, long-term, real estate, leasing, and business)
        :param sort: Sort by loan attributes (By amount available for investment, interest rate, term, etc.)
        :param ascending_sort: Sort by ascending order (By default sorts in descending order)
        :param group_guarantee: Restrict loans to only those with a group guarantee
        :param exclude_invested_loans: Exclude loans that have been invested in previously
        :return: A single page of available loans for investment according to specified parameters
        """

        if quantity <= 0:
            raise ValueError('You need to fetch at least 1 loan.')

        if quantity > CONSTANTS.MAX_LOAN_PAGE_SIZE:
            raise ValueError(f'You can fetch at most {CONSTANTS.MAX_LOAN_PAGE_SIZE} loan.')

        if sort not in CONSTANTS.LOAN_SORT_TYPES:
            raise InvalidSort(f'Loans can only be sorted by: {", ".join(CONSTANTS.LOAN_SORT_TYPES)}')

        sort = CONSTANTS.LOAN_SORT_TYPES[sort]

        loan_params = {
            'sort': sort if ascending_sort else f'-{sort}',
            'pageSize': quantity,
            'offset': quantity * page_num,
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
            loan_params['groupGuarantee'] = int(group_guarantee)

        if exclude_invested_loans is not None:
            loan_params['hideInvested'] = int(exclude_invested_loans)

        # Add country filters to query parameters
        if countries:
            if not isinstance(countries, list):
                raise TypeError(
                    f'Countries argument must be a list of countries. '
                    f'Available countries: {list(CONSTANTS.get_countries())}'
                )

            for idx, country in enumerate(countries):
                loan_params[f'countryIds[{idx}]'] = CONSTANTS.get_country_iso(country)

        if originators:
            for idx, originator in enumerate(originators):
                id_ = CONSTANTS.get_originator(originator)

                if isinstance(id_, list):
                    for sub_id, originator_id in enumerate(id_):
                        loan_params[f'loanOriginators[{idx + sub_id}]'] = originator_id

                    continue

                loan_params[f'loanOriginators[{idx}]'] = id_

        # Add loan type filters to query parameters
        if loan_types:
            if not isinstance(loan_types, list):
                raise TypeError(
                    f'loan_types arguments must be a list of loan types. '
                    f'Available loan types: {list(CONSTANTS.LOAN_TYPES_ID)}'
                )

            for idx, type_ in enumerate(loan_types):
                loan_params[f'loanTermId[{idx}]'] = CONSTANTS.get_loan_type(type_)

        return self._session.request(
            url=ENDPOINTS.LOANS_URI,
            params=loan_params,
        )

    def get_loan_details(
            self,
            loan_id: int,
            raw: bool = False,
    ) -> dict:
        """
        :param loan_id: ID of loan to get details from
        :param raw: Returns python list of schedule_data if True or pandas DataFrame if False (False by default)
        :return: The borrower's data, the loan's data, and the repayment schedule
        """

        credit_data = self._session.request(
            url=f'{ENDPOINTS.LOANS_URI}/{loan_id}',
        )

        schedule_data = credit_data['schedule']['data']

        return {
            'borrower_data': credit_data.get('borrower'),
            'loan_data': credit_data.get('loan'),
            'originator': credit_data.get('originator'),
            'pledge': credit_data.get('pledge'),
            'schedule_data': schedule_data if raw else pd.DataFrame(schedule_data),
        }

    def get_agreement(self, loan_id: int, lang: str = 'en') -> bytes:
        """
        :param loan_id: ID of investment to get agreement of
        :param lang: Language to return agreement in (ISO code, by default "en" for english)
        :return: Loan agreement bytes (Only available upon purchase)
        """

        agreement_bytes = self._session.request(
            url=f'{ENDPOINTS.INVESTMENTS_AGREEMENT_URI}/{loan_id}/agreement?lang={lang}',
            output_type='bytes',
        )

        return agreement_bytes

    def purchase_loan(
            self,
            loan_id: int,
            amount: decimal.Decimal,
    ) -> dict:
        """
        :param loan_id: ID of loan to purchase
        :param amount: Amount to invest in loan (Amount denominated in €)
        :return: Object containing an order (not transaction) id
        """

        return self._session.request(
            url=f'{ENDPOINTS.LOANS_URI}/{loan_id}',
            method='POST',
            data={'amount': str(amount)},
            exception_type=InsufficientFunds,
        )

    def get_investments(
            self,
            quantity: int,
            start_page: int = 0,
            max_date_of_purchase: Optional[date] = None,
            min_date_of_purchase: Optional[date] = None,
            max_interest_rate: Optional[decimal.Decimal] = None,
            min_interest_rate: Optional[decimal.Decimal] = None,
            max_invested_amount: Optional[decimal.Decimal] = None,
            min_invested_amount: Optional[decimal.Decimal] = None,
            countries: Optional[List[str]] = None,
            loan_types: Optional[List[str]] = None,
            sort: str = 'loan_amount',
            ascending_sort: bool = False,
            current: bool = True,
            raw: bool = False,
    ) -> Union[pd.DataFrame, list]:
        """
        If you're going to fetch more than ~350 investments it's recommended to use the get_mass_investments function.
        It provides more details about the investments, but has fewer filters available.
        :param quantity: Amount of investments to fetch
        :param start_page: Number of start page to start getting loans from
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
        :param current: Fetch current or finished investments (Set to False to fetch finished investments)
        :param raw: Returns python list if True or pandas DataFrame if False (False by default)
        :return: All current or finished investments according to specified parameters
        """

        if quantity <= 0:
            raise ValueError('You need to fetch at least 1 investment.')

        sort_types = CONSTANTS.CURRENT_INVESTMENT_SORT_TYPES if current else CONSTANTS.FINISHED_INVESTMENT_SORT_TYPES

        if sort not in sort_types:
            raise InvalidSort(f'Loans can only be sorted by: {", ".join(sort_types)}')

        sort = sort_types[sort]

        investment_params = {
            'sort': sort if ascending_sort else f'-{sort}',
            'pageSize': quantity,
            'type': 'CURRENT' if current else 'FINISHED',
            'offset': quantity * start_page,
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
            if not isinstance(countries, list):
                raise TypeError(
                    f'Countries argument must be a list of countries. '
                    f'Available countries: {list(CONSTANTS.get_countries())}'
                )

            for idx, country in enumerate(countries):
                investment_params[f'countryIds[{idx}]'] = CONSTANTS.get_country_iso(country)

        # Add loan type filters to query parameters
        if loan_types:
            if not isinstance(loan_types, list):
                raise TypeError(
                    f'loan_types arguments must be a list of loan types. '
                    f'Available loan types: {list(CONSTANTS.LOAN_TYPES_ID)}'
                )

            for idx, type_ in enumerate(loan_types):
                investment_params[f'loanTermId[{idx}]'] = CONSTANTS.get_loan_type(type_)

        investments_data = self._session.request(
            url=ENDPOINTS.INVESTMENTS_URI,
            params=investment_params,
        )['data']

        return investments_data if raw else pd.DataFrame(investments_data)

    def get_mass_investments(
            self,
            quantity: int = 100000000000,
            sort: str = 'invested_amount',
            countries: Optional[List[str]] = None,
            ascending_sort: bool = False,
            current: bool = True,
            raw: bool = False,
    ) -> Union[pd.DataFrame, bytes]:
        """
        This function has a lot better performance than the get_investments function for larger quantities of
        investments and should be used when fetching more than ~350 investment and has more detailed loan attributes,
        but has fewer filters available.
        :param quantity: Amount of investments to fetch (If quantity is not specified it will fetch all investments)
        :param sort: Sort by loan attributes (By amount available for investment, interest rate, term, etc.)
        :param countries: Filter investments by country of origin (Gets investments from all countries by default)
        :param ascending_sort: Sort by ascending order (By default sorts in descending order)
        :param current: Fetch current investments or finished investments (Gets current investments by default)
        :param raw: Returns Excel bytes if True or pandas DataFrame if False (False by default)
        :return: All current or finished investments according to specified parameters
        """

        if quantity <= 0:
            raise ValueError('You need to fetch at least 1 investment.')

        if sort not in CONSTANTS.LOAN_EXPORT_SORT_TYPES:
            raise InvalidSort(f'Loans can only be sorted by: {", ".join(CONSTANTS.LOAN_EXPORT_SORT_TYPES)}')

        investment_params = {
            'type': 'CURRENT' if current else 'FINISHED',
            'lang': 'en',
        }

        # Add country filters to query parameters
        if countries:
            if not isinstance(countries, list):
                raise TypeError(
                    f'Countries argument must be a list of countries. '
                    f'Available countries: {list(CONSTANTS.get_countries())}'
                )

            for idx, country in enumerate(countries):
                investment_params[f'countryIds[{idx}]'] = CONSTANTS.get_country_iso(country)

        investments = self._session.request(
            url=f'{ENDPOINTS.INVESTMENTS_URI}/export',
            params=investment_params,
            output_type='bytes',
        )

        sort = CONSTANTS.LOAN_EXPORT_SORT_TYPES[sort]

        investment_data = pd.read_excel(
            io=investments,
            sheet_name=0,
        ).sort_values(by=sort, ascending=ascending_sort)[0:quantity]

        return investments if raw else investment_data

    def get_account_summary(
            self,
            start_date: date,
            end_date: date,
    ) -> dict:
        """
        :param start_date: Start date of account summary
        :param end_date: End date of account summary
        :return: Summary of transactions during the specified time period (Invested funds, interest payments, etc.)
        """

        account_params = {
            'startDate': start_date,
            'endDate': end_date,
        }

        summary_data = self._session.request(
            url=ENDPOINTS.ACCOUNT_SUMMARY_URI,
            params=account_params,
        )

        return {
            'balance_data': {
                'opening_balance': decimal.Decimal(summary_data.get('openingBalance') or 0),
                'opening_date': summary_data.get('openingDate'),
                'closing_balance': decimal.Decimal(summary_data.get('closingBalance') or 0),
                'closing_date': summary_data.get('closingDate'),
            },
            'cash_flow_data': {
                'principal_payments': decimal.Decimal(summary_data['operations'].get('PRINCIPAL') or 0),
                'interest_payments': decimal.Decimal(summary_data['operations'].get('INTEREST') or 0),
                'investment_payments': decimal.Decimal(summary_data['operations'].get('INVESTMENT') or 0),
                'deposits': decimal.Decimal(summary_data['operations'].get('DEPOSIT') or 0),
                'withdrawals': decimal.Decimal(summary_data['operations'].get('WITHDRAWAL') or 0),
            },
            'currency': summary_data.get('currency'),
        }

    def get_transactions(
            self,
            quantity: Optional[int] = None,
            start_page: int = 0,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            periodicity: Optional[str] = None,
            transaction_types: Optional[List[str]] = None,
            raw: bool = False,
    ) -> Union[pd.DataFrame, list]:
        """
        If you want the transactions' Excel bytes use the get_mass_transactions function.
        The get_transactions function should be used for any other use case since it is much faster.
        It provides more details about the transactions, but has fewer filters available and is slower.
        :param quantity: Amount of investments to fetch (If quantity is not specified it will fetch all investments)
        :param start_page Number of start page to start getting loans from
        :param start_date: Start date of transaction data
        :param end_date: End date of transaction data
        :param periodicity: Specific periodicity filter (today, this week, and this month)
        :param transaction_types: Types of transactions to fetch (By default gets all transaction types)
        :param raw: Returns python list if True or pandas DataFrame if False (False by default)
        :return: All transactions according to specified parameters
        """

        transactions_params = {
            'pageSize': quantity,
            'startDate': start_date,
            'endDate': end_date,
            'offset': quantity * start_page if quantity is not None and start_date is not None else None,
        }

        if transaction_types is not None:
            types_ = CONSTANTS.TRANSACTION_TYPES

            for idx, type_ in enumerate(transaction_types):
                if type_ not in types_:
                    raise InvalidType(f'You can only get the following types {", ".join(types_)}')

                type_id = types_[type_]

                transactions_params[f'transactionType[{idx}]'] = type_id

        if periodicity is not None:
            periodicities = CONSTANTS.TRANSACTION_PERIODICITIES

            if periodicity not in periodicities:
                raise InvalidPeriodicity(f'Periodicity must be one of the following: {", ".join(periodicities)}')

            transactions_params['periodicity'] = periodicity

        transactions_data = self._session.request(
            url=ENDPOINTS.CASH_FLOW_URI,
            params=transactions_params,
        )

        return transactions_data if raw else pd.DataFrame(transactions_data)

    def get_mass_transactions(
            self,
            quantity: int,
            start_date: Optional[date],
            end_date: Optional[date],
            transaction_types: Optional[List[str]] = None,
            periodicity: Optional[str] = None,
            sort: str = 'amount',
            ascending_sort: bool = False,
            raw: bool = False,
    ) -> Union[pd.DataFrame, bytes]:
        """
        This function has a lot worse performance than the get_transactions function and should only be used
        when trying to get the transactions' Excel bytes.
        :param quantity: Amount of investments to fetch (If quantity is not specified it will fetch all investments)
        :param sort: Sort by loan attributes (By amount available for investment, interest rate, term, etc.)
        :param ascending_sort: Sort by ascending order (By default sorts in descending order)
        :param start_date: Start date of transaction data
        :param end_date: End date of transaction data
        :param periodicity: Specific periodicity filter (today, this week, and this month)
        :param transaction_types: Types of transactions to fetch (By default gets all transaction types)
        :param raw: Returns Excel bytes if True or pandas DataFrame if False (False by default)
        :return: All transactions according to specified parameters
        """

        types_ = CONSTANTS.TRANSACTION_SORT_TYPES

        if sort not in types_:
            raise InvalidSort(f'You can only sort by the following attributes: {", ".join(types_)}')

        sort = CONSTANTS.TRANSACTION_SORT_TYPES[sort]

        transactions_params = {
            'startDate': start_date,
            'endDate': end_date,
            'lang': 'en',
        }

        if transaction_types is not None:
            types_ = CONSTANTS.TRANSACTION_TYPES

            for idx, type_ in enumerate(transaction_types):
                if type_ not in types_:
                    raise InvalidType(f'You can only get the following types {", ".join(types_)}')

                type_id = types_[type_]

                transactions_params[f'transactionType[{idx}]'] = type_id

        if periodicity is not None:
            periodicities = CONSTANTS.TRANSACTION_PERIODICITIES

            if periodicity not in periodicities:
                raise InvalidPeriodicity(f'Periodicity must be one of the following: {", ".join(periodicities)}')

            transactions_params['periodicity'] = periodicity

        transactions_data = self._session.request(
            url=f'{ENDPOINTS.CASH_FLOW_URI}/import',
            params=transactions_params,
            output_type='bytes',
        )

        parsed_transactions_data = pd.read_excel(
            io=transactions_data,
            sheet_name=0,
        ).sort_values(by=sort, ascending=ascending_sort)

        return transactions_data if raw else parsed_transactions_data[0:quantity]

    def login(self) -> str:
        """
        :return: Access token to authenticate to Peerberry API
        """

        if self.access_token:
            self._session.add_header({'Authorization': f'Bearer {self.access_token}'})

            try:
                self.get_overview()

            except PeerberryException:
                raise PeerberryException('Invalid access token.')

            return f'Bearer {self.access_token}'

        login_data = {
            'email': self.email,
            'password': self._password,
        }

        login_response = self._session.request(
            url=ENDPOINTS.LOGIN_URI,
            method='POST',
            data=login_data,
            exception_type=InvalidCredentials,
        )

        tfa_response_token = login_response.get('tfa_token')

        if self._tfa_secret is None:
            self.access_token = login_response.get('access_token')

            self._session.add_header({'Authorization': f'Bearer {self.access_token}'})

            return f'Bearer {self.access_token}'

        totp_data = {
            'code': pyotp.TOTP(self._tfa_secret).now(),
            'tfa_token': tfa_response_token,
        }

        totp_response = self._session.request(
            url=ENDPOINTS.TFA_URI,
            method='POST',
            data=totp_data,
        )

        self.access_token = totp_response.get('access_token')

        self._session.add_header({'Authorization': f'Bearer {self.access_token}'})

        # Set authorization header with JWT bearer token
        return f'Bearer {self.access_token}'

    def logout(self) -> str:
        """
        :return: Success message upon logging out.
        """

        self._session.request(
            url=ENDPOINTS.LOGOUT_URI,
        )

        # Remove revoked authorization header
        self._session.remove_header('Authorization')

        self.access_token = None

        return 'Successfully logged out.'

    @staticmethod
    def get_countries() -> dict:
        return CONSTANTS.get_countries()

    @staticmethod
    def get_originators() -> dict:
        return CONSTANTS.get_originators()
