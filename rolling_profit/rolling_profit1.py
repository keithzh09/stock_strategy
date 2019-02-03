# coding: utf-8
# @author: lin
# @date: 2018/11/14

import QUANTAXIS as QA
import pandas as pd
import time
import matplotlib.pyplot as plt

pd.set_option('max_colwidth', 5000)
pd.set_option('display.max_columns', 5000)
pd.set_option('display.max_rows', 5000)


class RollingProfitStrategy:
    def __init__(self, start_time, stop_time, n=20, ascending=False, stock_init_cash=1000000):
        self.Account = QA.QA_Account()  # 初始化账户
        self.Account.reset_assets(stock_init_cash)  # 初始化账户
        self.Broker = QA.QA_BacktestBroker()
        self.time_quantum_list = ['-12-31', '-09-30', '-06-30', '-03-31']
        self.start_time = start_time
        self.stop_time = stop_time
        self.stock_pool = []
        self.cash_n = 5
        self.bought_price = {}  # 入场的价格
        self.last_price = {}  # 上一天的价格
        self.init_cash = {}  # 入场的现金分配
        self.bought_stock = {}  # 每种股票是否已入场, boolean
        self.init_strategy(n, ascending)

    def init_strategy(self, n, ascending):
        self.get_stock_pool_price(n, ascending)  # 获取股票和初始价格
        for stock_code in self.stock_pool:
            self.init_cash[stock_code] = [1 for i in range(self.cash_n)]  # 五等分
            self.bought_stock[stock_code] = False

    def get_financial_time(self):
        """
        得到此日期前一个财务数据的日期
        :return:
        """
        year = self.start_time[0:4]
        while (True):
            for day in self.time_quantum_list:
                the_financial_time = year + day
                if the_financial_time <= self.start_time:
                    return the_financial_time
            year = str(int(year) - 1)

    def get_assets_eps(self, stock_code, the_financial_time):
        """
        得到高级财务数据
        :param stock_code:
        :param the_financial_time: 离开始时间最近的财务数据的时间
        :return:
        """
        financial_report = QA.QA_fetch_financial_report(stock_code, the_financial_time)
        if financial_report is not None:
            return financial_report.iloc[0]['totalAssets'], financial_report.iloc[0]['EPS']
        return None, None

    def get_stock_pool_price(self, n, ascending):
        """
        选取哪些股票
        :param n: n只
        :param ascending: True则资产最少的前n，False则最多前n
        :return:
        """
        stock_code_list = QA.QA_fetch_stock_list_adv().code.tolist()
        stock_dict = {'stock': [], 'totalAssets': [], 'price': []}
        the_financial_time = self.get_financial_time()
        for stock_code in stock_code_list:
            # print(stock_code)
            assets, EPS = self.get_assets_eps(stock_code, the_financial_time)
            if assets is not None and EPS != 0:
                data = QA.QA_fetch_stock_day_adv(stock_code, self.start_time, self.stop_time)
                if data is None:
                    continue
                price = data.to_pd().iloc[0]['close']
                if 0 < price / EPS < 20:  # 满足条件才添加进行排序
                    # print(price / EPS)
                    stock_dict['stock'].append(stock_code)
                    stock_dict['totalAssets'].append(assets)
                    stock_dict['price'].append(price)
        data = pd.DataFrame(stock_dict)
        data.dropna(inplace=True)
        data.sort_values(by='totalAssets', ascending=ascending, axis=0, inplace=True)
        # print(data.iloc[:20])
        # data.reset_index(inplace=True, drop=True)
        self.stock_pool = list(data['stock'].iloc[:n])  # 前十行，若是用loc，则是查找索引
        price_list = list(data['price'].iloc[:n])
        for i in range(n):
            self.bought_price[self.stock_pool[i]] = price_list[i]
            self.last_price[self.stock_pool[i]] = price_list[i]
        print(self.stock_pool)

    def get_pre_month_date(self, date):
        # 得到一个月前的1日的日期，为了得到某天前十个交易日的数据
        date = date[:10]
        times = date.split('-')
        times = [int(i) for i in times]
        times[1] -= 1
        if times[1] == 0:
            times[0] -= 1
            times[1] = 12
        times[2] = 1
        return '%d-%02d-%02d' % (times[0], times[1], times[2])

    def is_decrease(self, data):
        # 是否连续五日下跌，此时当start_time为交易日时，第五天为start_time，若是用于实际数据中，我有点疑惑是否用reality_time数据或是前五个交易日
        close_data = list(data['close'].iloc[-5:])
        if len(close_data) < 5:
            return False
        if close_data[0] > close_data[1] > close_data[2] > close_data[3] > close_data[4]:  # 五日连续下跌
            print(close_data)
            return False
        return True

    def is_increase(self, data):
        close_data = list(data['close'].iloc[-10:])
        if len(close_data) < 10:
            return False
        mean_5_close = sum(close_data[5:10]) / 5
        mean_10_close = sum(close_data[:10]) / 10
        if (close_data[-1] - mean_5_close) / mean_5_close > 0.2 or \
                (close_data[-1] - mean_10_close) / mean_10_close > 0.2:  # 价格大于五日均线或者是十日均线 20%，则返回True
            print(close_data)
            return False
        return True

    def if_buy(self, stock_code, date):  # 若是连续五日下跌或者昨日价格大于五日或十日均线20%则不进行操作
        pre_month_date = self.get_pre_month_date(date)
        data = QA.QA_fetch_stock_day_adv(stock_code, pre_month_date, date)
        data = data.to_qfq()  # 前复权
        if self.is_decrease(data) or self.is_increase(data):
            return True
        return False

    def run(self):
        """
        每个股票初始五等分，可以进场则进场，每个股票盈亏单独算，当止损或者止盈时，股票池中所有未入场的股票现金均分一下
        也可每天均分一次，这样就把止损和止盈的情况包括进去了。
        :return:
        """

        self.Account.account_cookie = 'rolling_profit'
        # 每天均分一下现金
        data = QA.QA_fetch_stock_day_adv(self.stock_pool, self.start_time, self.stop_time).to_qfq()
        # print(data)
        for items in data.panel_gen:  # 每一天
            # 股票池中所有未入场的股票现金均分一下
            n_percent = 0
            for stock_code in self.stock_pool:
                n_percent += sum(self.init_cash[stock_code])
            if n_percent == 0:
                n_money = 0
            else:
                n_money = self.Account.cash_available / n_percent

            print(n_money)

            for item in items.security_gen:
                close_price = item.close[0]
                date = str(item.date[0])[:10]
                stock_code = item.code[0]
                # item = item.to_pd()
                # item.reset_index(inplace=True)
                if not self.bought_stock[stock_code]:  # 股票未入场的情况
                    if self.if_buy(stock_code, date):  # 若是可以买
                        if n_money >= close_price*100:
                            order = self.Account.send_order(
                                code=stock_code,
                                time=date,
                                money=n_money,
                                towards=QA.ORDER_DIRECTION.BUY,
                                price=close_price,
                                order_model=QA.ORDER_MODEL.CLOSE,
                                amount_model=QA.AMOUNT_MODEL.BY_MONEY
                            )
                            self.Broker.receive_order(QA.QA_Event(order=order, market_data=item))
                            trade_mes = self.Broker.query_orders(self.Account.account_cookie, 'filled')
                            res = trade_mes.loc[order.account_cookie, order.realorder_id]
                            order.trade(res.trade_id, res.trade_price, res.trade_amount, res.trade_time)  # date 应为res.trade_time的
                            self.init_cash[stock_code][0] = 0
                            self.bought_stock[stock_code] = True
                            self.bought_price[stock_code] = close_price  # 入场价格
                            self.last_price[stock_code] = close_price  # 最新价格
                else:  # 股票已经入场，一种是止盈或止亏，一种是继续买入
                    if (close_price - self.bought_price[stock_code]) / close_price > 0.15 \
                            or (close_price - self.bought_price[stock_code]) / close_price < -0.05:
                        # 止盈止亏
                        order = self.Account.send_order(
                            code=stock_code,
                            time=date,
                            amount=self.Account.sell_available.get(stock_code, 0),
                            towards=QA.ORDER_DIRECTION.SELL,
                            price=0,
                            order_model=QA.ORDER_MODEL.CLOSE,
                            amount_model=QA.AMOUNT_MODEL.BY_AMOUNT
                        )
                        self.Broker.receive_order(QA.QA_Event(order=order, market_data=item))
                        trade_mes = self.Broker.query_orders(self.Account.account_cookie, 'filled')
                        res = trade_mes.loc[order.account_cookie, order.realorder_id]
                        order.trade(res.trade_id, res.trade_price, res.trade_amount, res.trade_time)

                        self.bought_stock[stock_code] = False
                        self.init_cash[stock_code] = [1 for i in range(self.cash_n)]
                    else:
                        if (close_price - self.last_price[stock_code]) / close_price >= 0.01:  # 日涨1%(今日比昨日涨1%，才算)
                            for i in range(self.cash_n):
                                if self.init_cash[stock_code][i] == 1:
                                    if n_money >= close_price * 100:
                                        order = self.Account.send_order(
                                            code=stock_code,
                                            time=date,
                                            money=n_money,
                                            towards=QA.ORDER_DIRECTION.BUY,
                                            price=close_price,
                                            order_model=QA.ORDER_MODEL.CLOSE,
                                            amount_model=QA.AMOUNT_MODEL.BY_MONEY
                                        )
                                        self.Broker.receive_order(QA.QA_Event(order=order, market_data=item))
                                        trade_mes = self.Broker.query_orders(self.Account.account_cookie, 'filled')
                                        res = trade_mes.loc[order.account_cookie, order.realorder_id]
                                        order.trade(res.trade_id, res.trade_price, res.trade_amount, res.trade_time)

                                        self.init_cash[stock_code][i] = 0
                            self.last_price[stock_code] = close_price
            self.Account.settle()
        Risk = QA.QA_Risk(self.Account)
        Risk.assets.plot()  # 总资产
        plt.show()
        Risk.benchmark_assets.plot()  # 基准收益的资产
        plt.show()
        Risk.plot_assets_curve()  # 两个合起来的对比图
        plt.show()
        Risk.plot_dailyhold()  # 每只股票每天的买入量
        plt.show()


start = time.time()
one = RollingProfitStrategy('2016-01-01', '2018-05-01', ascending=False, stock_init_cash=1000000)
stop = time.time()
print(stop - start)
print(one.stock_pool)
one.run()
stoo = time.time()
print(stoo - stop)


# init_cash = {}
# init_price = {}
# for stock_code in stock_pool:
#     init_cash[stock_code] = 10000
#     init_price[stock_code] = 0    # 15%止盈
