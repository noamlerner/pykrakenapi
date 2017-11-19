# This file is part of pykrakenapi.
#
# pykrakenapi is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pykrakenapi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser
# General Public LICENSE along with pykrakenapi. If not, see
# <http://www.gnu.org/licenses/lgpl-3.0.txt> and
# <http://www.gnu.org/licenses/gpl-3.0.txt>.

"""The core module of pykrakenapi.

This module contains the core class ``KrakenAPI``, implementing the methods
of the official KrakenAPI (https://www.kraken.com/help/api).

For further information type

>>> help(KrakenAPI)

"""

import datetime
from functools import wraps

import pandas as pd


def callratelimiter(query_type):
    def decorate_func(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            """Call rate limit counter.

            Implementation of a call rate limiter as a decorator. If the call
            rate limit is reached, api calls will be blocked.

            See https://support.kraken.com/hc/en-us/articles/206548367

            """

            self = args[0]

            # determine increment
            if query_type == 'ledger/trade history':
                incr = 2
            elif query_type == 'other':
                incr = 1

            # decrease api counter, update time of last query
            now = datetime.datetime.now()
            decr = int((now - self.time_of_last_query).seconds / self.factor)
            self.api_counter -= decr
            if self.api_counter < 0:
                self.api_counter = 0
            self.time_of_last_query = now

            # return api call
            if self.api_counter < self.limit:
                result = func(*args, **kwargs)
                self.api_counter += incr
                return result

            # block if limit exceeded
            else:
                print('api count limit exceeded, counter=', self.api_counter)
                return

        return wrapper
    return decorate_func


class KrakenAPIError(Exception):
    pass


class KrakenAPI(object):
    """A python implementation of the Kraken API.

    Implements the Kraken API methods using the low-level krakenex python
    package. See
    https://www.kraken.com/help/api
    and
    https://github.com/veox/python3-krakenex

    Parameters
    ----------
    api : krakenex.API
        An instance of the krakenex.API class. A reference to the input
        is created and accessible via ``KrakenAPI.api``.

    tier : int
        Your Kraken tier level, used to adjust the limit of the call rate to
        the Kraken API in order to prevent 15 minute temporary lockouts. See
        https://support.kraken.com/hc/en-us/articles/206548367.

    Attributes
    ----------
    api : krakenex.API
        See Parameters.

    """

    def __init__(self, api, tier=2):

        self.api = api

        # api call rate limiter
        self.time_of_last_query = datetime.datetime.now()
        self.api_counter = 0

        if tier == 2:
            self.limit = 15
            self.factor = 3  # down by 1 every three seconds

        elif tier == 3:
            self.limit = 20
            self.factor = 2  # down by 1 every two seconds

        elif tier == 4:
            self.limit = 20
            self.factor = 1  # down by 1 every one second

    @callratelimiter('other')
    def get_server_time(self):
        """Get server time.

        This is to aid in approximating the skew time between the server and
        client.

        Returns
        -------
        dt : pandas._libs.tslib.Timestamp
            The server's datetime.
        unixtime : int
            The unix timestamp.

        """

        # query
        res = self.api.query_public('Time')

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # extract results
        dt = pd.to_datetime(res['result']['rfc1123'])
        unixtime = res['result']['unixtime']

        return dt, unixtime

    @callratelimiter('other')
    def get_asset_info(self, info=None, aclass=None, asset=None):
        """Get asset info.

        Return a ``pd.DataFrame`` of asset names and their info.

        Parameters
        ----------
        info : ?, optional (default=None)
            Info to retrieve. If None (default), retrieve all info.

        aclass : str, optional (default=None)
            Asset class. If None (default), aclass='currency'.

        asset : str, optional (default=None)
            Comma delimited list of assets to get info on. If None (default),
            all for given asset class.

        Returns
        -------
        assets : pd.DataFrame
            index = asset name
            aclass = asset class
            altname = alternate name
            decimals = scaling decimal places for record keeping
            display_decimals = scaling decimal places for output display.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_public('Assets', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        assets = pd.DataFrame(res['result']).T

        return assets

    @callratelimiter('other')
    def get_tradable_asset_pairs(self, info=None, pair=None):
        """Get tradable asset pairs.

        Return a ``pd.DataFrame`` of pair names and their info.

        Parameters
        ----------
        info : str, optional (default=None)
            Info to retrieve. Can be one of {'leverage', 'fees', 'margin'}.
            If None (default), retrieve all info.

        pair : str, optional (default=None)
            Comma delimited list of asset pairs to get info on. If None
            (default), all.

        Returns
        -------
        pairs : pd.DataFrame
            index = pair name
            altname = alternate pair name
            aclass_base = asset class of base component
            base = asset id of base component
            aclass_quote = asset class of quote component
            quote = asset id of quote component
            lot = volume lot size
            pair_decimals = scaling decimal places for pair
            lot_decimals = scaling decimal places for volume
            lot_multiplier = amount to multiply lot volume by to get currency
                volume
            leverage_buy = array of leverage amounts available when buying
            leverage_sell = array of leverage amounts available when selling
            fees = fee schedule array in [volume, percent fee] tuples
            fees_maker = maker fee schedule array in [volume, percent fee]
                tuples (if on maker/taker)
            fee_volume_currency = volume discount currency
            margin_call = margin call level
            margin_stop = stop-out/liquidation margin level

        Notes
        -----
        If an asset pair is on a maker/taker fee schedule, the taker side is
        given in "fees" and maker side in "fees_maker". For pairs not on
        maker/taker, they will only be given in "fees".

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_public('AssetPairs', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        pairs = pd.DataFrame(res['result']).T

        return pairs

    @callratelimiter('other')
    def get_ticker_information(self, pair):
        """Get ticker information.

        Return a ``pd.DataFrame`` of pair names and their ticker info.

        Parameters
        ----------
        pair : str
            Comma delimited list of asset pairs to get info on.

        Returns
        -------
        ticker : pd.DataFrame
            index =  pair name
            a = ask array(<price>, <whole lot volume>, <lot volume>),
            b = bid array(<price>, <whole lot volume>, <lot volume>),
            c = last trade closed array(<price>, <lot volume>),
            v = volume array(<today>, <last 24 hours>),
            p = volume weighted average price array(<today>, <last 24 hours>),
            t = number of trades array(<today>, <last 24 hours>),
            l = low array(<today>, <last 24 hours>),
            h = high array(<today>, <last 24 hours>),
            o = today's opening price

        Notes
        -----
        Today's prices start at 00:00:00 UTC.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_public('Ticker', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        ticker = pd.DataFrame(res['result']).T

        return ticker

    @callratelimiter('other')
    def get_ohlc_data(self, pair, interval=1, since=None):
        """Get ohlc data for a given pair.

        Return a ``pd.DataFrame`` of the OHLC data for a given pair and time
        interval (minutes). Optionally, return data from ``since`` onwards
        (exclusive).

        Parameters
        ----------
        pair : str
            Asset pair to get OHLC data for.

        interval : int, optional (default=1)
            Time frame interval in minutes. Defaults to 1. One of
            {1, 5, 15, 30, 60, 240, 1440, 10080, 21600}.

        since : int, optional (default=None)
            Return committed OHLC data since given unixtime (exclusive). If
            None, retrieve from earliest time possible.

        Returns
        -------
        ohlc : pd.DataFrame
            index = pair name
            time (unixtime)
            dtime (UTC)
            open
            high
            low
            close
            vwap
            volume
            count

        last : int
            Unixtime to be used as since when polling for new, committed OHLC
            data.

        Notes
        -----
        The last entry in the OHLC array is for the current, not-yet-committed
        frame and will always be present, regardless of the value of "since".

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_public('OHLC', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        ohlc = pd.DataFrame(res['result'][pair])
        last = res['result']['last']

        # set time, column names
        ohlc.columns = [
            'time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'
        ]
        ohlc['dtime'] = pd.to_datetime(ohlc.time, unit='s')
        ohlc.sort_values('dtime', ascending=False, inplace=True)
        ohlc.set_index('dtime', inplace=True)

        # dtypes
        for col in ['open', 'high', 'low', 'close', 'vwap', 'volume']:
            ohlc.loc[:, col] = ohlc[col].astype(float)

        return ohlc, last

    @callratelimiter('other')
    def get_order_book(self, pair, count=100):
        """Get order book (market depth).

        Return a ``pd.DataFrame`` for both asks and bids for a given pair.

        Parameters
        ----------
        pair : str
            Asset pair to get market depth for.

        count : int, optional (default=100)
            Maximum number of asks/bids. Per default, get the latest 100
            bids and asks.

        Returns
        -------
        asks : pd.DataFrame
            The ask side table.
            index = datetime
            price
            volume
            time (unixtime)

        bids : pd.DataFrame
            The bid side table.
            index = datetime
            price
            volume
            time (unixtime)

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_public('Depth', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        asks = pd.DataFrame(res['result'][pair]['asks'])
        bids = pd.DataFrame(res['result'][pair]['bids'])

        # column names
        cols = ['price', 'volume', 'time']
        asks.columns = cols
        bids.columns = cols

        # set datetime
        asks['dtime'] = pd.to_datetime(asks.time, unit='s')
        bids['dtime'] = pd.to_datetime(bids.time, unit='s')

        # sort by time
        asks.sort_values('dtime', ascending=False, inplace=True)
        bids.sort_values('dtime', ascending=False, inplace=True)

        # set index
        asks.set_index('dtime', inplace=True)
        bids.set_index('dtime', inplace=True)

        return asks, bids

    @callratelimiter('ledger/trade history')
    def get_recent_trades(self, pair, since=None):
        """Get recent trades data.

        Return a ``pd.DataFrame`` of recent trade data for a given pair,
        optionally from ``since`` onwards (exclusive).

        Parameters
        ----------
        pair : str
            Asset pair to get trade data for.

        since : int, optional (default=None)
            Return trade data since given unixtime (exclusive). If
            None, retrieve from earliest time possible.

        Returns
        -------
        trades : pd.DataFrame
            Table containing recent trades for a given pair.
            index = datetime
            price
            volume
            time (unixtime)
            buy/sell
            market/limit
            miscellaneous

        last : int
            Unixtime to be used as since when polling for new trade data.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_public('Trades', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        trades = pd.DataFrame(res['result'][pair])
        trades.columns = [
            'price', 'volume', 'time', 'buy_sell', 'market_limit', 'misc'
        ]
        trades.buy_sell.replace('b', 'buy', inplace=True)
        trades.buy_sell.replace('s', 'sell', inplace=True)
        trades.market_limit.replace('l', 'limit', inplace=True)
        trades.market_limit.replace('m', 'market', inplace=True)

        # time
        trades['dtime'] = pd.to_datetime(trades.time, unit='s')
        trades.sort_values('dtime', ascending=False, inplace=True)
        trades.set_index('dtime', inplace=True)

        # last timestamp
        last = int(res['result']['last'])

        return trades, last

    @callratelimiter('other')
    def get_recent_spread_data(self, pair, since=None):
        """Get recent spread data.

        Return a ``pd.DataFrame`` of recent spread data for a given pair,
        optionally from ``since`` onwards (inclusive).

        Parameters
        ----------
        pair : str
            Asset pair to get spread data for.

        since : int, optional (default=None)
            Return spread data since given unixtime (inclusive). If
            None, retrieve from earliest time possible.

        Returns
        -------
        trades : pd.DataFrame
            Table containing recent spread for a given pair.
            index = datetime
            time (unixtime)
            bid
            ask
            spread (ask - bid)

        last : int
            Unixtime to be used as since when polling for new spread data.

        Notes
        -----
        ``since`` is inclusive so any returned data with the same time as the
        previous set should overwrite all of the previous set's entries at that
        time.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_public('Spread', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        spread = pd.DataFrame(res['result'][pair])
        spread.columns = ['time', 'bid', 'ask']

        # time
        spread['dtime'] = pd.to_datetime(spread.time, unit='s')
        spread.sort_values('dtime', ascending=False, inplace=True)
        spread.set_index('dtime', inplace=True)

        # spread
        spread.loc[:, 'bid'] = spread.bid.astype(float)
        spread.loc[:, 'ask'] = spread.ask.astype(float)
        spread['spread'] = spread.ask - spread.bid

        # last timestamp
        last = int(res['result']['last'])

        return spread, last

    @callratelimiter('other')
    def get_account_balance(self):
        """Get asset names and balance amount.

        Return a ``pd.DataFrame`` of asset names and their corresponding
        balance amounts.

        Returns
        -------
        balance : pd.DataFrame
            Table containing asset names and balance amount.
            index = asset name
            vol = balance amount

        """

        # query
        res = self.api.query_private('Balance')

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        balance = pd.DataFrame(index=['vol'], data=res['result']).T
        balance.loc[:, 'vol'] = balance.vol.astype(float)

        return balance

    @callratelimiter('ledger/trade history')
    def get_trade_balance(self, aclass='currency', asset='ZEUR'):
        """Get trade balance info.

        Return a ``pd.DataFrame`` of trade balance info.

        Parameters
        ----------
        aclass : str, optional (default='currency')
            Asset class.

        asset : str, optional (default='ZUSD')
            Base asset used to determine balance.

        Returns
        -------
        tradebalance : pd.DataFrame
            Table containing trade balance info.
            eb = equivalent balance (combined balance of all currencies)
            tb = trade balance (combined balance of all equity currencies)
            m = margin amount of open positions
            n = unrealized net profit/loss of open positions
            c = cost basis of open positions
            v = current floating valuation of open positions
            e = equity = trade balance + unrealized net profit/loss
            mf = free margin = equity - initial margin (maximum margin
                available to open new positions)
            ml = margin level = (equity / initial margin) * 100

        Notes
        -----
        Rates used for the floating valuation is the midpoint of the best bid
        and ask prices.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('TradeBalance', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        tradebalance = pd.DataFrame(index=[asset], data=res['result']).T
        tradebalance.loc[:, asset] = tradebalance[asset].astype(float)

        return tradebalance

    @callratelimiter('other')
    def get_open_orders(self, trades=False, userref=None):
        """UNTESTED!

        Get open orders info.

        Return a dictionary of open orders info.

        Parameters
        ----------
        trades : bool, optional (default=False)
            Whether or not to include trades in output.

        userref : int, optional (default=None)
            Restrict results to given user reference id.

        Returns
        -------
        tradebalance : dict
            refid = Referral order transaction id that created this order
            userref = user reference id
            status = status of order:
                pending = order pending book entry
                open = open order
                closed = closed order
                canceled = order canceled
                expired = order expired
            opentm = unix timestamp of when order was placed
            starttm = unix timestamp of order start time (or 0 if not set)
            expiretm = unix timestamp of order end time (or 0 if not set)
            descr = order description info
                pair = asset pair
                type = type of order (buy/sell)
                ordertype = order type (See Add standard order)
                price = primary price
                price2 = secondary price
                leverage = amount of leverage
                order = order description
                close = conditional close order description (if conditional
                    close set)
            vol = volume of order (base currency unless viqc set in oflags)
            vol_exec = volume executed (base currency unless viqc set in
                oflags)
            cost = total cost (quote currency unless unless viqc set in oflags)
            fee = total fee (quote currency)
            price = average price (quote currency unless viqc set in oflags)
            stopprice = stop price (quote currency, for trailing stops)
            limitprice = triggered limit price (quote currency, when limit
                based order type triggered)
            misc = comma delimited list of miscellaneous info
                stopped = triggered by stop price
                touched = triggered by touch price
                liquidated = liquidation
                partial = partial fill
            oflags = comma delimited list of order flags
                viqc = volume in quote currency
                fcib = prefer fee in base currency (default if selling)
                fciq = prefer fee in quote currency (default if buying)
                nompp = no market price protection
            trades = array of trade ids related to order (if trades info
                requested and data available)

        Notes
        -----
        Unless otherwise stated, costs, fees, prices, and volumes are in the
        asset pair's scale, not the currency's scale. For example, if the asset
        pair uses a lot size that has a scale of 8, the volume will use a scale
        of 8, even if the currency it represents only has a scale of 2.
        Similarly, if the asset pair's pricing scale is 5, the scale will
        remain as 5, even if the underlying currency has a scale of 8.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('OpenOrders', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        openorders = res['result']

        return openorders

    @callratelimiter('other')
    def get_closed_orders(self, trades=False, userref=None, start=None,
                          end=None, ofs=None, closetime=None):
        """Get closed orders info.

        Return a ``pd.DataFrame`` of closed orders info.

        Parameters
        ----------
        trades : bool, optional (default=False)
            Whether or not to include trades in output.

        userref : int, optional (default=None)
            Restrict results to given user reference id.

        start : int, optional (default=None)
            Starting unixtime or order tx id of results (exclusive).

        end : int, optional (default=None)
            Ending unixtime or order tx id of results (inclusive)-

        ofs : ?, optional (default=None)
            Result offset.

        closetime : str, optional (default=None)
            Which time to use, must be one of {'open', 'close', 'both'}. If
            None (default), closetime='both'.

        Returns
        -------
        closed : pd.DataFrame
            Array of order info.  See Get open orders.  Additional fields:
            closetm = unix timestamp of when order was closed
            reason = additional info on status (if any)

        count :
            Amount of available order info matching criteria.

        Notes
        -----
        Times given by order tx ids are more accurate than unix timestamps. If
        an order tx id is given for the time, the order's open time is used.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('ClosedOrders', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        closed = pd.DataFrame(res['result']['closed']).T
        descr = closed.descr.apply(pd.Series)
        descr.columns = ['descr_{}'.format(col) for col in descr.columns]
        del closed['descr']
        closed = pd.concat((closed, descr), axis=1)
        for col in ['closetm', 'expiretm', 'opentm', 'starttm']:
            closed.loc[:, col] = closed[col].astype(int)
        for col in ['cost', 'fee', 'price', 'vol', 'vol_exec', 'descr_price',
                    'descr_price2']:
            closed.loc[:, col] = closed[col].astype(float)

        # count
        count = res['result']['count']

        return closed, count

    @callratelimiter('other')
    def query_orders_info(self, txid, trades=False, userref=None):
        """Query orders info.

        Return a ``pd.DataFrame`` of orders info.

        Parameters
        ----------
        txid : str
            Comma delimited list of transaction ids to query info about
            (20 maximum).

        trades : bool, optional (default=False)
            Whether or not to include trades in output.

        userref : int, optional (default=None)
            Restrict results to given user reference id.

        Returns
        -------
        orders : pd.DataFrame
            order_txid = order info.  See get_open_orders/get_closed_orders.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('QueryOrders', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        orders = pd.DataFrame(res['result']).T
        descr = orders.descr.apply(pd.Series)
        descr.columns = ['descr_{}'.format(col) for col in descr.columns]
        del orders['descr']
        orders = pd.concat((orders, descr), axis=1)
        for col in ['closetm', 'expiretm', 'opentm', 'starttm']:
            orders.loc[:, col] = orders[col].astype(int)
        for col in ['cost', 'fee', 'price', 'vol', 'vol_exec', 'descr_price',
                    'descr_price2']:
            orders.loc[:, col] = orders[col].astype(float)

        return orders

    @callratelimiter('ledger/trade history')
    def get_trades_history(self, type='all', trades=False, start=None,
                           end=None, ofs=None):
        """Get trades history.

        Return a ``pd.DataFrame`` of the trade history.

        Parameters
        ----------
        type : str, optional (default='all')
            Type of trade, must be one of:
                'all' (default)    : all types (default)
                'any position'     : any position (open or closed)
                'closed position'  : positions that have been closed
                'closing position' : any trade closing all or part of a
                                     position
                'no position'      : non-positional trades

        trades : bool, optional (default=False)
            Whether or not to include trades related to position in output.

        start : int, optional (default=None)
            Starting unixtime or trade tx id of results (exclusive).

        end : int, optional (default=None)
            Ending unixtime or trade tx id of results (inclusive).

        ofs : ?, optional (default=None)
            Result offset.

        Returns
        -------
        trades : pd.DataFrame
            index = datetime
            txid = trade txid
            ordertxid = order responsible for execution of trade
            pair = asset pair
            time = unix timestamp of trade
            type = type of order (buy/sell)
            ordertype = order type
            price = average price order was executed at (quote currency)
            cost = total cost of order (quote currency)
            fee = total fee (quote currency)
            vol = volume (base currency)
            margin = initial margin (quote currency)
            misc = comma delimited list of miscellaneous info
                closing = trade closes all or part of a position

            If the trade opened a position, the following fields are also
            present in the trade info:

            posstatus = position status (open/closed)
            cprice = average price of closed portion of position (quote
                currency)
            ccost = total cost of closed portion of position (quote currency)
            cfee = total fee of closed portion of position (quote currency)
            cvol = total fee of closed portion of position (quote currency)
            cmargin = total margin freed in closed portion of position (quote
                currency)
            net = net profit/loss of closed portion of position (quote
                currency, quote currency scale)
            trades = list of closing trades for position (if available)

        count : int
            Amount of available trades info matching criteria.

        Notes
        -----
        Unless otherwise stated, costs, fees, prices, and volumes are in the
        asset pair's scale, not the currency's scale.

        Times given by trade tx ids are more accurate than unix timestamps.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('TradesHistory', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        trades = pd.DataFrame(res['result']['trades']).T
        trades.index.name = 'txid'
        trades.reset_index(inplace=True)

        # append datetime, sort by it
        trades['dtime'] = pd.to_datetime(trades.time, unit='s')
        trades.sort_values('dtime', ascending=False, inplace=True)
        trades.set_index('dtime', inplace=True)

        # set dtypes
        for col in ['cost', 'fee', 'margin', 'price', 'time', 'vol']:
            trades.loc[:, col] = trades[col].astype(float)

        # count
        count = res['result']['count']

        return trades, count

    @callratelimiter('ledger/trade history')
    def query_trades_info(self, txid, trades=False):
        """Query trades info.

        Return a ``pd.DataFrame`` of trades info.

        Parameters
        ----------
        txid : str
            Comma delimited list of transaction ids to query info about
            (20 maximum).

        trades : bool, optional (default=False)
            Whether or not to include trades related to position in output.

        Returns
        -------
        trades : pd.DataFrame
            See get_trades_history.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('QueryTrades', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        trades = pd.DataFrame(res['result']).T
        trades.index.name = 'txid'
        trades.reset_index(inplace=True)

        # append datetime, sort by it
        trades['dtime'] = pd.to_datetime(trades.time, unit='s')
        trades.sort_values('dtime', ascending=False, inplace=True)
        trades.set_index('dtime', inplace=True)

        # set dtypes
        for col in ['cost', 'fee', 'margin', 'price', 'time', 'vol']:
            trades.loc[:, col] = trades[col].astype(float)

        return trades

    @callratelimiter('other')
    def get_open_positions(self, txid=None, docalcs=False):
        """UNTESTED!

        Get open positins info.

        Return a ``pd.DataFrame`` of open positions info.

        Parameters
        ----------
        txid : str, optional (default=None)
            Comma delimited list of transaction ids to restrict output to.

        docalcs : bool, optional (default=False)
            Whether or not to include profit/loss calculations.

        Returns
        -------
        openpositions : pd.DataFrame
            txid =
            ordertxid = order responsible for execution of trade
            pair = asset pair
            time = unix timestamp of trade
            type = type of order used to open position (buy/sell)
            ordertype = order type used to open position
            cost = opening cost of position (quote currency unless viqc set in
                oflags)
            fee = opening fee of position (quote currency)
            vol = position volume (base currency unless viqc set in oflags)
            vol_closed = position volume closed (base currency unless viqc set
                in oflags)
            margin = initial margin (quote currency)
            value = current value of remaining position (if docalcs requested.
                quote currency)
            net = unrealized profit/loss of remaining position (if docalcs
                requested.  quote currency, quote currency scale)
            misc = comma delimited list of miscellaneous info
            oflags = comma delimited list of order flags
                viqc = volume in quote currency

        Notes
        -----
        Unless otherwise stated, costs, fees, prices, and volumes are in the
        asset pair's scale, not the currency's scale.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('OpenPositions', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        openpositions = res['result']

        return openpositions

    @callratelimiter('ledger/trade history')
    def get_ledgers_info(self, aclass=None, asset=None, type='all', start=None,
                         end=None, ofs=None):
        """Get ledgers info.

        Return a ``pd.DataFrame`` of ledgers info.

        Parameters
        ----------
        aclass : str, optional (default=None)
            Asset class. If None (default), aclass='currency'.

        asset : str, optional (default=None)
            Comma delimited list of assets to restrict output to. If None
            (default), all for given asset class.

        type : str, optional (default='all')
            Type of ledger to retrieve, must be one of {'all', 'deposit',
            'withdrawal', 'trade', 'margin'}

        start : int, optional (default=None)
            Starting unixtime or ledger id of results (exclusive).

        end : int, optional (default=None)
            Ending unixtime or ledger id of results (inclusive)

        ofs : ?, optional (default=None)
            Result offset.

        Returns
        -------
        ledger : pd.DataFrame
            ledger_id = ledger info
            refid = reference id
            time = unx timestamp of ledger
            type = type of ledger entry
            aclass = asset class
            asset = asset
            amount = transaction amount
            fee = transaction fee
            balance = resulting balance

        count : int
            Amount of available ledger info matching criteria.

        Notes
        -----
        Times given by ledger ids are more accurate than unix timestamps.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('Ledgers', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        ledgers = pd.DataFrame(res['result']['ledger']).T
        ledgers.index.name = 'ledger_id'
        ledgers.reset_index(inplace=True)

        # append datetime, sort by it
        ledgers['dtime'] = pd.to_datetime(ledgers.time, unit='s')
        ledgers.sort_values('dtime', ascending=False, inplace=True)
        ledgers.set_index('dtime', inplace=True)

        # dtypes
        for col in ['amount', 'balance', 'fee']:
            ledgers.loc[:, col] = ledgers[col].astype(float)
        ledgers.loc[:, 'time'] = ledgers.time.astype(int)

        # count
        count = res['result']['count']

        return ledgers, count

    @callratelimiter('ledger/trade history')
    def query_ledgers(self, id):
        """Query ledgers info.

        Return a ``pd.DataFrame`` of ledgers info.

        Parameters
        ----------
        id : int
            Comma delimited list of ledger ids to query info about
            (20 maximum).

        Returns
        -------
        ledgers : pd.DataFrame
            ledger_id = ledger info.  See get_ledgers_info.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('QueryLedgers', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        ledgers = pd.DataFrame(res['result']).T
        ledgers.index.name = 'ledger_id'
        ledgers.reset_index(inplace=True)

        # append datetime, sort by it
        ledgers['dtime'] = pd.to_datetime(ledgers.time, unit='s')
        ledgers.sort_values('dtime', ascending=False, inplace=True)
        ledgers.set_index('dtime', inplace=True)

        # dtypes
        for col in ['amount', 'balance', 'fee']:
            ledgers.loc[:, col] = ledgers[col].astype(float)
        ledgers.loc[:, 'time'] = ledgers.time.astype(int)

        return ledgers

    @callratelimiter('ledger/trade history')
    def get_trade_volume(self, pair=None, fee_info=True):
        """Get trade volume.

        Return a ``pd.DataFrame`` of trade volume.

        Parameters
        ----------
        pair : str, optional (default=None)
            Comma delimited list of asset pairs to get fee info on. If None
            (default), no fee info is provided.

        fee_info : bool, optional (default=True)
            Whether or not to include fee info in results.

        Returns
        -------
        currency : str
            Currency (ZUSD).

        volume : float
            Current discount volume.

        fees : pd.DataFrame
            Asset pairs and fee tier info (if requested)
                fee = current fee in percent
                minfee = minimum fee for pair (if not fixed fee)
                maxfee = maximum fee for pair (if not fixed fee)
                nextfee = next tier's fee for pair (if not fixed fee. nil if
                    at lowest fee tier)
                nextvolume = volume level of next tier (if not fixed fee. nil
                    if at lowest fee tier)
                tiervolume = volume level of current tier (if not fixed fee.
                    nil if at lowest fee tier)

        fees_maker : pd.DataFrame
            Asset pairs and maker fee tier info (if requested) for any pairs on
                    maker/taker schedule
                fee = current fee in percent
                minfee = minimum fee for pair (if not fixed fee)
                maxfee = maximum fee for pair (if not fixed fee)
                nextfee = next tier's fee for pair (if not fixed fee. nil if
                    at lowest fee tier)
                nextvolume = volume level of next tier (if not fixed fee. nil
                    if at lowest fee tier)
                tiervolume = volume level of current tier (if not fixed fee.
                    nil if at lowest fee tier)

        Notes
        -----
        If an asset pair is on a maker/taker fee schedule, the taker side is
        given in "fees" and maker side in "fees_maker". For pairs not on
        maker/taker, they will only be given in "fees".

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('TradeVolume', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        # create dataframe
        volume = float(res['result']['volume'])

        # fees
        try:
            fees = pd.DataFrame(res['result']['fees'])
            for col in fees.columns:
                fees.loc[:, col] = fees[col].astype(float)
        except KeyError:
            fees = None
        try:
            fees_maker = pd.DataFrame(res['result']['fees_maker'])
            for col in fees_maker.columns:
                fees_maker.loc[:, col] = fees_maker[col].astype(float)
        except KeyError:
            fees_maker = None

        # currency
        currency = res['result']['currency']

        return currency, volume, fees, fees_maker

    def add_standard_order(self, pair, type, ordertype, volume, price=None,
                           price2=None, leverage=None, oflags=None, starttm=0,
                           expiretm=0, userref=None, validate=True,
                           close_ordertype=None, close_price=None,
                           close_price2=None):
        """UNTESTED!

        Add a standard order.

        Add a standard order and return an order description info and an array
        of transaction ids for the order (if succesfull).

        Parameters
        ----------
        pair = asset pair
        type = type of order (buy/sell)
        ordertype = order type:
            market
            limit (price = limit price)
            stop-loss (price = stop loss price)
            take-profit (price = take profit price)
            stop-loss-profit (price = stop loss price, price2 = take profit
                price)
            stop-loss-profit-limit (price = stop loss price, price2 = take
                profit price)
            stop-loss-limit (price = stop loss trigger price, price2 =
                triggered limit price)
            take-profit-limit (price = take profit trigger price, price2 =
                triggered limit price)
            trailing-stop (price = trailing stop offset)
            trailing-stop-limit (price = trailing stop offset, price2 =
                triggered limit offset)
            stop-loss-and-limit (price = stop loss price, price2 = limit price)
            settle-position
        price = price (optional.  dependent upon ordertype)
        price2 = secondary price (optional.  dependent upon ordertype)
        volume = order volume in lots
        leverage = amount of leverage desired (optional.  default = none)
        oflags = comma delimited list of order flags (optional):
            viqc = volume in quote currency (not available for leveraged
                orders)
            fcib = prefer fee in base currency
            fciq = prefer fee in quote currency
            nompp = no market price protection
            post = post only order (available when ordertype = limit)
        starttm = scheduled start time (optional):
            0 = now (default)
            +<n> = schedule start time <n> seconds from now
            <n> = unix timestamp of start time
        expiretm = expiration time (optional):
            0 = no expiration (default)
            +<n> = expire <n> seconds from now
            <n> = unix timestamp of expiration time
        userref = user reference id.  32-bit signed number.  (optional)
        validate = validate inputs only.  do not submit order (optional)

        optional closing order to add to system when order gets filled:
            close[ordertype] = order type
            close[price] = price
            close[price2] = secondary price

        Returns
        -------
        descr = order description info
            order = order description
            close = conditional close order description (if conditional close
                set)
        txid = array of transaction ids for order (if order was added
            successfully)

        Errors
        ------
        Errors: errors include (but are not limited to):

        EGeneral:Invalid arguments
        EService:Unavailable
        ETrade:Invalid request
        EOrder:Cannot open position
        EOrder:Cannot open opposing position
        EOrder:Margin allowance exceeded
        EOrder:Margin level too low
        EOrder:Insufficient margin (exchange does not have sufficient funds to
            allow margin trading)
        EOrder:Insufficient funds (insufficient user funds)
        EOrder:Order minimum not met (volume too low)
        EOrder:Orders limit exceeded
        EOrder:Positions limit exceeded
        EOrder:Rate limit exceeded
        EOrder:Scheduled orders limit exceeded
        EOrder:Unknown position

        Notes
        -----
        See get_tradable_asset_pairs for specifications on asset pair prices,
        lots, and leverage.

        Prices can be preceded by +, -, or # to signify the price as a relative
        amount (with the exception of trailing stops, which are always
        relative). + adds the amount to the current offered price. - subtracts
        the amount from the current offered price. # will either add or
        subtract the amount to the current offered price, depending on the type
        and order type used. Relative prices can be suffixed with a % to
        signify the relative amount as a percentage of the offered price.

        For orders using leverage, 0 can be used for the volume to auto-fill
        the volume needed to close out your position.

        If you receive the error "EOrder:Trading agreement required", refer to
        your API key management page for further details.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # query
        res = self.api.query_private('AddOrder', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        return res['result']

    def cancel_open_order(self, txid):
        """UNTESTED!

        Cancel open order(s).

        Cancel open order with transaction id ``txid``.

        Parameters
        ----------
        txid : int
            Transaction id.

        Returns
        -------
        count : int
            Number of orders canceled.

        pending : bool
            If set, order(s) is/are pending cancellation.

        Notes
        -----
        txid may be a user reference id.

        """

        # create data dictionary
        data = {arg: value for arg, value in locals().items() if
                arg != 'self' and value is not None}

        # submit
        res = self.api.query_private('CancelOrder', data=data)

        # check for error
        if len(res['error']) > 0:
            raise KrakenAPIError(res['error'])

        return res['result']

    def datetime_to_unixtime(self, dt):
        """Return unixtime for a given datetime.

        Parameters
        ----------
        dt : datetime.datetime
            The datetime to convert to unixtime.

        Returns
        -------
        unixtime : int
            The unixtime corresponding to the given datetime.

        """

        delta_t = (dt - datetime.datetime(1970, 1, 1)).total_seconds()
        unixtime = int(delta_t)

        return unixtime

    def unixtime_to_datetime(self, unixtime):
        """Return datetime (UTC) for a given unixtime.

        Parameters
        ----------
        unixtime : int
            The unixtime to convert to datetime.

        Returns
        -------
        datetime : datetime.datetime
            The datetime (UTC) corresponding to the given unixtime.

        """

        dt = datetime.datetime(1970, 1, 1) + datetime.timedelta(0, unixtime)

        return dt