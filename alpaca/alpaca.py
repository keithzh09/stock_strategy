# coding: utf-8
# @author: lin
# @date: 2018/11/9


import QUANTAXIS as QA
import datetime
import pandas as pd
import time
import matplotlib.pyplot as plt
import numpy as np

pd.set_option('max_colwidth', 5000)
pd.set_option('display.max_columns', 5000)
pd.set_option('display.max_rows', 5000)


class Alpaca:
    def __init__(self, start_time, stop_time, n_stock=10, stock_init_cash=1000000, n_days_before=1):
        self.Account = QA.QA_Account()  # 初始化账户
        self.Account.reset_assets(stock_init_cash)  # 初始化账户
        self.Account.account_cookie = 'alpaca'
        self.Broker = QA.QA_BacktestBroker()
        self.time_quantum_list = ['-12-31', '-09-30', '-06-30', '-03-31']
        self.start_time = start_time
        self.stop_time = stop_time
        self.n_days_before = n_days_before
        self.stock_pool = []
        self.data = None
        self.ind = None
        self.n_stock = n_stock
        self.get_stock_pool()

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

    def get_stock_pool(self):
        """
        选取哪些股票
        """
        stock_code_list = QA.QA_fetch_stock_list_adv().code.tolist()
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
                    self.stock_pool.append(stock_code)

    # 成交量因子
    def alpaca(self, data):
        data['yesterday_price'] = 0
        data['previous_n_price'] = 0
        data.reset_index(inplace=True)   # 重置后，索引以数字
        for index, row in data.iterrows():
            yes_index = index - 1
            pre_n_index = index - (self.n_days_before+1)
            if yes_index >= 0:
                data.loc[index, 'yesterday_price'] = data.loc[yes_index, 'close']
            if pre_n_index >= 0:
                data.loc[index, 'previous_n_price'] = data.loc[pre_n_index, 'close']
        data['yield_rate'] = 0
        data['yield_rate'] = data['yesterday_price'] / data['previous_n_price']
        data.set_index(['date', 'code'], inplace=True)
        return data

    def solve_data(self):
        self.data = QA.QA_fetch_stock_day_adv(self.stock_pool, self.start_time, self.stop_time)
        self.ind = self.data.add_func(self.alpaca)

    def run(self):
        self.solve_data()
        for items in self.data.panel_gen:
            today_time = items.index[0][0]
            one_day_data = self.ind.loc[today_time]      # 得到有包含因子的DataFrame
            one_day_data['date'] = items.index[0][0]
            one_day_data.reset_index(inplace=True)
            one_day_data.sort_values(by='yield_rate', axis=0, ascending=False, inplace=True)
            today_stock = list(one_day_data.iloc[0:self.n_stock]['code'])
            one_day_data.set_index(['date', 'code'], inplace=True)
            one_day_data = QA.QA_DataStruct_Stock_day(one_day_data)  # 转换格式，便于计算
            bought_stock_list = list(self.Account.hold.index)
            print("SELL:")
            for stock_code in bought_stock_list:
                # 如果直接在循环中对bought_stock_list操作，会跳过一些元素
                if stock_code not in today_stock:
                    try:
                        item = one_day_data.select_day(str(today_time)).select_code(stock_code)
                        order = self.Account.send_order(
                            code=stock_code,
                            time=today_time,
                            amount=self.Account.sell_available.get(stock_code, 0),
                            towards=QA.ORDER_DIRECTION.SELL,
                            price=0,
                            order_model=QA.ORDER_MODEL.MARKET,
                            amount_model=QA.AMOUNT_MODEL.BY_AMOUNT
                        )
                        self.Broker.receive_order(QA.QA_Event(order=order, market_data=item))
                        trade_mes = self.Broker.query_orders(self.Account.account_cookie, 'filled')
                        res = trade_mes.loc[order.account_cookie, order.realorder_id]
                        order.trade(res.trade_id, res.trade_price, res.trade_amount, res.trade_time)
                    except Exception as e:
                        print(e)
            print('BUY:')
            for stock_code in today_stock:
                try:
                    item = one_day_data.select_day(str(today_time)).select_code(stock_code)
                    order = self.Account.send_order(
                        code=stock_code,
                        time=today_time,
                        amount=1000,
                        towards=QA.ORDER_DIRECTION.BUY,
                        price=0,
                        order_model=QA.ORDER_MODEL.CLOSE,
                        amount_model=QA.AMOUNT_MODEL.BY_AMOUNT
                    )
                    self.Broker.receive_order(QA.QA_Event(order=order, market_data=item))
                    trade_mes = self.Broker.query_orders(self.Account.account_cookie, 'filled')
                    res = trade_mes.loc[order.account_cookie, order.realorder_id]
                    order.trade(res.trade_id, res.trade_price, res.trade_amount, res.trade_time)
                except Exception as e:
                    print(e)
            self.Account.settle()
        Risk = QA.QA_Risk(self.Account)
        print(Risk.message)
        # plt.show()
        Risk.assets.plot()  # 总资产
        plt.show()
        Risk.benchmark_assets.plot()  # 基准收益的资产
        plt.show()
        Risk.plot_assets_curve()  # 两个合起来的对比图
        plt.show()
        Risk.plot_dailyhold()  # 每只股票每天的买入量
        plt.show()


start = time.time()
sss = Alpaca('2017-01-01', '2018-01-01', 10)
stop = time.time()
print(stop - start)
print(len(sss.stock_pool))
sss.run()
stop2 = time.time()
print(stop2 - stop)

