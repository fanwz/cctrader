#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/10/22 15:29
# @Author  : AMR
# @File    : okextrader.py
# @Software: PyCharm

from . import websocket
import time
import sys
import json
import hashlib
import zlib
import base64

from .OkcoinSpotAPI import OKCoinSpot
from .OkcoinFutureAPI import OKCoinFuture

import io
import os
from threading import Timer
from .header import jsonload, jsondump
import asyncio
import threading
import queue


class Debug(object):
    EN = False

    def __init__(self):
        pass


def pr_d(odata):
    if Debug.EN:
        print(odata)

def inflate(data):
    decompress = zlib.decompressobj(
            -zlib.MAX_WBITS  # see above
    )
    inflated = decompress.decompress(data)
    inflated += decompress.flush()
    return inflated


class MyQueue(object):
    myqueue = queue.Queue(maxsize=3)

    def __init__(self):
        pass

    @classmethod
    def put(cls, item, *kw):
        cls.myqueue.put(item, *kw)

    @classmethod
    def get(cls):
        item = cls.myqueue.get()
        return item


class MsgQueue(object):

    def __init__(self, maxsize=10):
        self.q = queue.Queue(maxsize=maxsize)

    def put(self, item, *kw):
        self.q.put(item, *kw)

    def get(self):
        item = self.q.get()
        return item

    def reset(self):
        self.q.queue.clear()


class OkConfig(object):
    def __init__(self, conffile):
        self.data = jsonload(conffile)


class OrderStatus(object):
    UNKNOWN = 0
    SENDING = 1
    ON_MARKET = 2
    TRADED = 3
    CANCELING = 4
    CANCELED = 5

    def __init__(self):
        pass


class TradeData(object):
    DATA_FILE = r'trade_data.json'
    trade_flag = 1
    all_orders = {}
    holds = {'long': {'num': 0, 'orders': []}, 'short': {'num': 0, 'orders': []}}

    def __init__(self):
        pass

    @classmethod
    def update_orders(cls, order, status):
        if order not in cls.all_orders:
            cls.all_orders[order] = {'status': status}
        else:
            cls.all_orders[order]['status'] = status

        if status == OrderStatus.CANCELED:
            del cls.all_orders[order]

    @classmethod
    def update_holds(cls, td_type, order_id, amount):
        if td_type == TradeApi.OPEN_LONG:
            cls.holds['long']['num'] += amount
            cls.holds['long']['orders'].append(order_id)
        elif td_type == TradeApi.OPEN_SHORT:
            cls.holds['short']['num'] += amount
            cls.holds['short']['orders'].append(order_id)
        elif td_type == TradeApi.CLOSE_LONG:
            cls.holds['long']['num'] -= amount
            cls.holds['long']['orders'].remove(order_id)
        elif td_type == TradeApi.CLOSE_SHORT:
            cls.holds['short']['num'] -= amount
            cls.holds['short']['orders'].remove(order_id)

    @classmethod
    def save_data(cls):
        td_data = {'all_orders': cls.all_orders, 'holds': cls.holds}
        jsondump(td_data, cls.DATA_FILE)

    @classmethod
    def load_data(cls):
        if os.path.exists(cls.DATA_FILE):
            try:
                j = jsonload(cls.DATA_FILE)
                cls.holds = j['holds']
                cls.all_orders = j['all_orders']
            except Exception as e:
                pr_d("load data error: {}".format(e))
                cls.all_orders = {}
                cls.holds = {'long': {'num': 0, 'orders': []}, 'short': {'num': 0, 'orders': []}}
            pr_d("all_orders: {}".format(cls.all_orders))
            pr_d("holds: {}".format(cls.holds))


class Algo(object):
    def __init__(self, debug=False):
        self.run_flag = True
        self.md = None
        self.td = None
        self.md_q = queue.Queue(maxsize=5)
        self.td_q = queue.Queue(maxsize=6)
        Debug.EN = debug

        self.__on_tick = None
        self.__on_trade = None

        # config load
        self.oc = OkConfig("okexconfig.json")
        pr_d(self.oc.data)

        # trade data load
        TradeData.load_data()

    def __trade_init(self):
        self.td = TradeApi(self.oc.data['td'])
        self.td_q = self.td_q

    def __md_init(self):
        host = self.oc.data["md"]["host"]
        self.md = MarketDataApi(host)
        self.md.md_q = self.md_q
        self.md.subscribe(self.oc.data["md"]["contract"])
        self.md_thread = threading.Thread(target=self.md.run, name='ws md thread')
        self.md.md_run_flag = True
        self.md_thread.start()

    def __polling(self):
        while self.polling_flag:
            self.on_tick()
            self.on_trade()
            self.on_misc()

    def __send_order(self, contract, contract_type, price, amount, type):
        # return
        order_id = self.td.send_order(contract, contract_type, price, amount, type)
        if order_id:
            pr_d("order_id = {}".format(order_id))
            s_order_id = str(order_id)
            TradeData.update_orders(s_order_id, OrderStatus.ON_MARKET)
            TradeData.update_holds(TradeApi.OPEN_LONG, s_order_id, float(amount))
            TradeData.save_data()

    def __cancel_order(self, contract, contract_type, order_id):
        cc_orders = self.td.cancel_order(contract, contract_type, order_id + ",")
        if cc_orders:
            for order in cc_orders:
                TradeData.update_orders(order, OrderStatus.CANCELED)
                TradeData.update_holds(TradeApi.CLOSE_LONG, order, 1)
                TradeData.save_data()

    def register(self, name):
        def func_wrapper(func):
            if name == 'on_tick':
                self.__on_tick = func
            elif name == 'on_trade':
                self.__on_trade = func
            else:
                raise Exception('no func register name: ' + str(name))
        return func_wrapper

    def on_tick(self):
        try:
            while not self.md_q.empty():
                pr_d("alog on_tick")
                item = self.md_q.get()
                pr_d(item)
                if self.__on_tick is not None:
                    self.__on_tick(self, item)
        except Exception as e:
            pr_d(e)
            self.md_q.queue.clear()

    def on_trade(self):
        try:
            while not self.td_q.empty():
                pr_d("alog on_trade")
                item = self.td_q.get()
                pr_d(item)
                self.__on_trade(self, item)
        except Exception as e:
            pr_d(e)
            self.td_q.queue.clear()

    def on_misc(self):
        pass

    def send_order(self, contract, contract_type, price, amount, type):
        if self.td is None:
            pr_d("no td to send order")
            return
        thread = threading.Thread(target=self.__send_order, args=(contract, contract_type, price, amount, type))
        thread.start()

    def cancel_order(self, contract, contract_type, order_id):
        if self.td is None:
            pr_d("no td to cancel order")
            return
        thread = threading.Thread(target=self.__cancel_order, args=(contract, contract_type, order_id))
        thread.start()


    def run(self):
        if self.__on_trade is not None:
            self.__trade_init()

            if len(TradeData.all_orders) > 0:
                for order, v in list(TradeData.all_orders.items()):
                    self.cancel_order("eos_usd", "this_week", order + ",")

        if self.__on_tick is not None:
            self.__md_init()

        pr_d('Algo Start!')
        self.algo_thread = threading.Thread(target=self.__polling, name='Algo Polling')
        self.polling_flag = True
        self.algo_thread.start()
        self.algo_thread.join()


class MarketDataApi(object):
    def __init__(self, host):
        pr_d('====MarketData api init start====')
        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(host,
                                         on_message=self.__on_msg,
                                         on_error=self.__on_err,
                                         on_close=self.__on_close)
        self.ws.on_open = self.__on_open
        self.contract_list = []

        self.on_tick = None
        self.td = None
        self.md_q = None

        self.md_run_flag = False

        pr_d('====MarketData api init start====')

    def __on_open(self, ws):
        pr_d("open")
        sub_dict = {'event': 'addChannel'}
        for contract in self.contract_list:
            sub_dict['channel'] = contract
            ws.send(str(sub_dict).encode(encoding='utf-8'))

    def __on_msg(self, ws, evt):
        data = inflate(evt)  # data decompress
        j = json.loads(data)
        pr_d("on msg:{}".format(j))
        if j[0]["channel"] in self.contract_list:
            # self.on_tick(self, j[0]["data"], self.td)
            if self.md_q is not None:
                try:
                    # self.md_q.put(j[0]["data"], True, 2)
                    self.md_q.put(j, True, 2)
                except Exception as e:
                    pr_d(e)
                    pr_d("algo md queue buffer full timeout!")
                    self.md_q.queue.clear()

    def __on_err(self, ws, evt):
        data = inflate(evt)  # data decompress
        pr_d("on err:{}".format(data))

    def __on_close(self, ws):
        pr_d("close!!!")

    def subscribe(self, contract):
        if isinstance(contract, list):
            for item in contract:
                self.contract_list.append(item)
        else:
            self.contract_list.append(contract)

    def run(self):
        while self.md_run_flag:
            pr_d("md_run_flag")
            try:
                self.ws.run_forever()
            except Exception as e:
                pr_d(e)


class TradeApi(object):

    LEVER_RATE = ["10", "0"]
    OPEN_LONG = "1"
    OPEN_SHORT = "2"
    CLOSE_LONG = "3"
    CLOSE_SHORT = "4"

    def __init__(self, tdconf):
        pr_d('====trade api init start====')
        self.spot_host = tdconf['spot']['host']
        self.future_host = tdconf['future']['host']
        self.spot_enable = tdconf['spot']['enable']
        self.future_enable = tdconf['future']['enable']
        self.apikey = tdconf['auth']['api_key']
        self.secretkey = tdconf['auth']['secret_key']
        self.lever_rate = tdconf['future']['lever_rate']
        ordertypes = tdconf['ordertypes']
        self.ordertype_list = [x.split("|") for x in ordertypes]
        self.order_info_bak = {}
        for type in ordertypes:
            self.order_info_bak[type] = None
        self.msg_cnt = 0
        self.update_orders = None
        self.td_q = None

        if self.lever_rate not in TradeApi.LEVER_RATE:
            self.lever_rate = TradeApi.LEVER_RATE[0] # default 10x

        # 现货API
        self.okcoinSpot = OKCoinSpot(self.spot_host, self.apikey, self.secretkey)
        # 期货API
        self.okcoinFuture = OKCoinFuture(self.future_host, self.apikey, self.secretkey)

        self.orderinfo_thread = threading.Thread(target=self.get_orderinfo_task, name='orderinfo_thread')
        self.orderinfo_run_flag = True
        self.orderinfo_thread.start()
        pr_d('====trade api init end====')

    def __get_orderinfo(self, contract, contract_type):
        # pr_d(contract, contract_type)
        resp = self.okcoinFuture.future_orderinfo(contract, contract_type, "-", "1", "1", "50")
        # pr_d(resp)
        j = json.loads(resp)
        pr_d("order_info:{}".format(j))
        if j['result'] and self.td_q:
            # pr_d("111111")
            # pr_d(self.order_info_bak[contract + "|" + contract_type])
            # pr_d(j['orders'])
            # pr_d(222222)
            if self.order_info_bak[contract + "|" + contract_type] != j['orders']:
                pr_d("======put new td data=======")
                try:
                    self.td_q.put(j['orders'], False)
                    self.order_info_bak[contract + "|" + contract_type] = j['orders']
                    pr_d("update td data")
                except Exception as e:
                    pr_d(e)
                    pr_d("td queue is full")
                    self.td_q.queue.clear()

    def get_orderinfo_task(self):
        while self.orderinfo_run_flag:
            try:
                time.sleep(1)
                # for order in list(TradeData.all_orders.keys()):
                thread_pool = []
                for ordertype in self.ordertype_list:
                    thread = threading.Thread(target=self.__get_orderinfo, args=(ordertype[0], ordertype[1]), )
                    thread_pool.append(thread)
                    thread.start()
            except Exception as e:
                pr_d(e)

    # okex api trade contract include symbol and type
    def send_order(self, contract, contract_type, price, amount, type, match="0"):
        pr_d(contract, contract_type, price, amount, type, self.lever_rate)
        resp = self.okcoinFuture.future_trade(contract, contract_type, price, amount, type, match, self.lever_rate)
        pr_d(resp)
        j = json.loads(resp)
        if j['result']:
            return j['order_id']
        else:
            return None

    def cancel_order(self, contract, contract_type, order_id):
        resp = self.okcoinFuture.future_cancel(contract, contract_type, order_id)
        pr_d(resp)
        j = json.loads(resp)
        if j['success'] != "":
            return j['success'].split(",")
        else:
            return None

#
# algo = Algo()
#
# @algo.register('on_tick')
# def on_tick(algo, md):
#     pr_d("my on tick")
#     pr_d(md)
#     bid5 = md["bids"][-1][0]
#     pr_d("bid5={}".format(bid5))
#     # algo.send_order("eos_usd", "this_week", str(bid5 - 1.0), "1", TradeApi.OPEN_LONG)
#
# @algo.register('on_trade')
# def on_trade(algo, order):
#     pr_d('my on trade')
#     pr_d(order)
#
# if __name__ == "__main__":
#     # myalgo = Algo()
#     algo.run()
#
#     pr_d('end!!!\n')
#     pr_d('end!!!\n')