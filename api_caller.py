import time, copy
import yaml
import requests
import json

import pandas as pd
from collections import namedtuple
from datetime import datetime


class ApiCaller:
    def __init__(self, conf_path: str) -> None:
        if not conf_path.endswith(".yaml"):
            print('Conf file is not for yaml: ' + conf_path)  
            exit(1)
        
        with open(conf_path, encoding="UTF-8") as f:
            _cfg = yaml.load(f, Loader=yaml.FullLoader)

        # Token 얻기
        self.URL_BASE = "https://openapivts.koreainvestment.com:29443"
        token_path = "auth2/token"
        toek_url = f"{self.URL_BASE}/{token_path}"

        self.headers = {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            'User-Agent': _cfg['my_agent']
        }
        body = {
            "grant_type": "client_credentials",
            "app_key": _cfg["app_key"],
            "appsecret": _cfg["app_secret"]
        }

        res = requests.post(toek_url, headers=self.headers, data=json.dumps(body))
        if res.status_code != 200:
            print('Get Authentification token fail!\nYou have to restart your app!!!')
            exit(1)
        self.access_token = res.json()["access_token"]
        self.headers.update({"authorization": f"Bearer {self.access_token}"})

        self.BASE_PARAMS = {
            "CANO": "", # 계좌번호 앞 8자리
            "ACNT_PRDT_CD": "", # 계좌번호 뒤 2자리
        }

    def get_hashkey(self, datas) -> str:
        # HASHKEY 얻기
        hashkey_path = "uapi/hashkey"
        hashkey_url = f"{self.URL_BASE}/{hashkey_path}"

        res = requests.post(hashkey_url, headers=self.headers, data=json.dumps(datas))
        return res.json()["HASH"]

    def get_curr_price(self, market, iscd) -> None:
        path = "uapi/domestic-stock/v1/quotations/inquire-price"
        url = f"{self.URL_BASE}/{path}"

        headers = {"tr_id":"FHKST01010100"} # 현재가 시세 tr_id
        headers.update(self.headers)

        params = {
            "fid_cond_mrkt_div_code":"J", # 시장구분
            "fid_input_iscd":"005930" # 종목코드
        }
        res = APIResp(requests.get(url, headers=headers, data=params))

        if not res.isOK():
            res.printError()
            return
        return res.getBody().output['stock_prpr'] # 현재 시세

    def get_daily_price(self) -> None:
        path = "uapi/domestic-stock/v1/quotations/inquire-daily-price"
        url = f"{self.URL_BASE}/{path}"

        headers = {"tr_id":"FHKST01010400"} # 일자별 현재가 tr_id
        headers.update(self.headers)

        params = {
            "fid_cond_mrkt_div_code":"J", # 시장구분 T(ETF?) / J(주식) / C(선물?)
            "fid_input_iscd":"005930", # 종목코드
            "fid_org_adj_prc":"1", # 수정주
            "fid_period_div_code":"D" # 기간분류 D(Daily) W(Weakly) M(Monthly) Y
        }

        res = APIResp(requests.get(url, headers=headers, params=params))

        if not res.isOK():
            res.printError()
            return
        return res.getBody().output[0]['stck_clpr'] # 종가

    def get_balance(self):
        url = f"{self.URL_BASE}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
        tr_id = "TTTC8434R"

        params = {
            'CANO': getTREnv().my_acct, 
            'ACNT_PRDT_CD': '01', 
            'AFHR_FLPR_YN': 'N', 
            'FNCG_AMT_AUTO_RDPT_YN': 'N', 
            'FUND_STTL_ICLD_YN': 'N', 
            'INQR_DVSN': '01', 
            'OFL_YN': 'N', 
            'PRCS_DVSN': '01', 
            'UNPR_DVSN': '01', 
            'CTX_AREA_FK100': '', 
            'CTX_AREA_NK100': ''
            }
        

    def order_stock_buying(self, pdno: str, dvsn: str, qty: int, price: int) -> None:
        path = "uapi/domestic-stock/v1/trading/order-cash"
        url = f"{self.URL_BASE}/{path}"

        params = {
            "PDNO": pdno, # 종목 코드
            "ORD_DVSN": dvsn, # 주문 구분 00(지정가) 01(시장가)
            "ORD_QTY": str(qty), # 주문 수량
            "ORD_UNPR": str(price), # 주문 단가 : 시장가 주문일 경우 무의미
        }
        params.update(self.BASE_PARAMS)

        headers = {
            "tr_id":"VTTC0802U", # 매수 tr_id
            "custtype":"P",
            "hashkey" : self.get_hashkey(params)
        }
        headers.update(self.headers)

        res = APIResp(requests.get(url, headers=headers, params=params))
        if not res.isOK():
            res.printError()
            return

        self.ordered_stocks.add(res.getBody().output)

    def order_stock_selling(self, pdno: str, dvsn: str, qty: int, price: int):
        path = "uapi/domestic-stock/v1/trading/order-cash"
        url = f"{URL_BASE}/{path}"

        params = {
            "PDNO": pdno, # 종목 코드
            "ORD_DVSN": dvsn, # 주문 구분 00(지정가) 01(시장가)
            "ORD_QTY": str(qty), # 주문 수량
            "ORD_UNPR": str(price), # 주문 단가 : 시장가 주문일 경우 무의미
        }
        params.update(self.BASE_PARAMS)

        headers = {
            "tr_id":"VTTC0801U", # 매도 tr_id
            "custtype":"P",
            "hashkey" : self.get_hashkey(params)
        }
        headers.update(self.headers)

        res = APIResp(requests.get(url, headers=headers, params=params))
        if not res.isOK():
            res.printError()
            return

        self.ordered_stocks.add(res.getBody().output)

    def modify_stock_buying(self, odno, qty=0, price=0, all=False) -> None:
        path = "uapi/domestic-stock/v1/trading/order-rvsencl"
        url = f"{self.URL_BASE}/{path}"

        orgno = None
        for stock_info in self.ordered_stocks:
            if odno == stock_info["ODNO"]:
                orgno = stock_info["KRX_FWDG_ORD_ORGNO"]
                break
        
        if orgno is None:
            return;

        dvsn = "01" if price > 0 else "02"
        all = "Y" if all != False else "N"
        params ={
            "KRX_FWDG_ORD_ORGNO": orgno,
            "ORGN_ODNO":odno,
            "RVSE_CNCL_DVSN_CD": dvsn, # 01 : 정정, 02 : 취소
            "ORD_DVSN":"00",  # 주문 구분 00(지정가) 01(시장가)
            "ORD_QTY": str(qty), # 주문 수량
            "ORD_UNPR": str(price), # 주문 단가 : 시장가 주문일 경우 무의미
            "QTY_ALL_ORD_YN": all, # 전량 여부
        }
        params.update(self.BASE_PARAMS)

        headers = {
            "tr_id":"VTTC0803U", # 정정 및 취소 tr_id
            "custtype":"P",
            "hashkey" : self.get_hashkey(params)
        }
        headers.update(self.headers)
        res = APIResp(requests.get(url, headers=headers, params=params))
        if not res.isOK():
            res.printError()
            return

        self.ordered_stocks.add(res.getBody().output)



class APIResp:
    def __init__(self, resp):
        self._rescode = resp.status_code
        self._resp = resp
        self._header = self._setHeader()
        self._body = self._setBody()
        self._err_code = self._body.rt_cd
        self._err_message = self._body.msg1

    def getResCode(self):
        return self._rescode

    def _setHeader(self):
        fld = dict()
        for x in self._resp.headers.keys():
            if x.islower():
                fld[x] = self._resp.headers.get(x)
        _th_ =  namedtuple('header', fld.keys())

        return _th_(**fld)

    def _setBody(self):
        _tb_ = namedtuple('body', self._resp.json().keys())

        return  _tb_(**self._resp.json())

    def getHeader(self):
        return self._header

    def getBody(self):
        return self._body

    def getResponse(self):
        return self._resp

    def isOK(self):
        try:
            if self.getResCode() != 200:
                return False
            if self.getBody().rt_cd != '0':
                return False
        except:
            return False
        return True

    def getErrorCode(self):
        return self._err_code

    def getErrorMessage(self):
        return self._err_message

    def printAll(self):
        #print(self._resp.headers)
        print("<Header>")
        for x in self.getHeader()._fields:
            print(f'\t-{x}: {getattr(self.getHeader(), x)}')
        print("<Body>")
        for x in self.getBody()._fields:        
            print(f'\t-{x}: {getattr(self.getBody(), x)}')

    def printError(self):
        print('-------------------------------\nError in response: ', self.getResCode())
        print(self.getBody().rt_cd, self.getErrorCode(), self.getErrorMessage())
        print('-------------------------------')   

# end of class APIResp