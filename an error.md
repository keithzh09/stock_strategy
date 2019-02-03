 - 这两天运行代码时候除了遇到资金不足以购买100股的问题，又突然遇到个错误，错误看最后的图
 - 看错误一开始没看出什么东西，后来才看到最明显的第一行，没有获取到日期的问题
 - 看了源代码，转来转去，定位到QADealer.py文件
 - Broker.receive_order() --> self.market_data = market_data.to_json()[0] --> dealer.deal(order, market_data) --> dealer.market_date = market_data且res=dealer.backtest_dealer() --> self.trade_time = self.market_data.get('datetime', self.market_data.get('date', None))  
 - 但是我print后发现此时的self.market_data已经没有了date和code的信息，于是我重新回去之前deal()里的赋值，发现market_data已经变了，于是继续往前找，发现receive_order()时候，传入的market_data被判断成了DataFrame去处理，于是我又发现在receive_order一开始的market_data赋值的时候，就已经成为了一个DataFrame
 - 最终我发现，我不知道什么时候，手贱自己把传入格式用了to_pd()函数，擦
 - 但是我觉得这里可能作者也没考虑到这个问题，就是他代码里对传入参数是允许DataFrame格式，我那时可能也是想试试可不可行，但是我们如果从数据库得到的数据，转化成DataFrame后，date和code作为索引，转化成json格式不会保留，而且在所有的回测天数里，是不会报任何错误的，只有到了最后一步，风险分析的时候，没有每天的日期，就报错了。

![](https://i.imgur.com/DgZEhk2.png)