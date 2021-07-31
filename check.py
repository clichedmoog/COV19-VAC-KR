# -*- coding: utf-8 -*-

import argparse
import datetime
import json
import os
import platform
import re
import sys
import time

from decimal import Decimal
from decimal import InvalidOperation
from urllib.parse import urlparse, parse_qs

import requests

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions


map_url = 'https://m.place.naver.com/rest/vaccine?vaccineFilter=used&bounds={bounds}'
list_url = 'https://api.place.naver.com/graphql'
item_url = 'https://v-search.nid.naver.com/reservation/standby?orgCd={cd}&sid={sid}'
progress_url = 'https://v-search.nid.naver.com/reservation/progress?key={key}&cd={vaccine_id}'
TIMEOUT = 5
session = requests.session()

vaccines_id_map = {
    'PF': {'id': 'VEN00013', 'name': '화이자'},
    'MO': {'id': 'VEN00014', 'name': '모더나'},
    'AZ': {'id': 'VEN00015', 'name': '아스트라제네카'},
    'JS': {'id': 'VEN00016', 'name': '얀센'},
}

# Colors from https://stackoverflow.com/a/54955094
class style:
    ENDC = '\033[0m'
    OK = '\033[94m'
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    ERROR = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Check agencies
def list_agencies(x1='126.8281358', y1='37.5507676', x2='126.8603223', y2='37.5872323'):
    try:
        x1 = Decimal(x1)
        y1 = Decimal(y1)
        x2 = Decimal(x2)
        y2 = Decimal(y2)
    except InvalidOperation as e:
        print(e)
        return []
    data = [
        {
            "operationName":"vaccineList",
            "variables":{
                "input":{
                    "keyword":"코로나백신위탁의료기관",
                    "x": f"{(x1 + x2) / 2}",
                    "y": f"{(y1 + y2) / 2}"
                },
                "businessesInput":{
                    "start":0,
                    "display":100,
                    "deviceType":"mobile",
                    "x": f"{(x1 + x2) / 2}",
                    "y": f"{(y1 + y2) / 2}",
                    "bounds": f"{x1};{y1};{x2};{y2}",
                    "sortingOrder":"distance"
                },
                "isNmap": False,
                "isBounds": False
            },
            "query":"query vaccineList($input: RestsInput, $businessesInput: RestsBusinessesInput, $isNmap: Boolean!, $isBounds: Boolean!) {\n rests(input: $input) {\n businesses(input: $businessesInput) {\n total\n vaccineLastSave\n isUpdateDelayed\n items {\n id\n name\n dbType\n phone\n virtualPhone\n hasBooking\n hasNPay\n bookingReviewCount\n description\n distance\n commonAddress\n roadAddress\n address\n imageUrl\n imageCount\n tags\n distance\n promotionTitle\n category\n routeUrl\n businessHours\n x\n y\n imageMarker @include(if: $isNmap) {\n marker\n markerSelected\n __typename\n }\n markerLabel @include(if: $isNmap) {\n text\n style\n __typename\n }\n isDelivery\n isTakeOut\n isPreOrder\n isTableOrder\n naverBookingCategory\n bookingDisplayName\n bookingBusinessId\n bookingVisitId\n bookingPickupId\n vaccineOpeningHour {\n isDayOff\n standardTime\n __typename\n }\n vaccineQuantity {\n totalQuantity\n totalQuantityStatus\n startTime\n endTime\n vaccineOrganizationCode\n list {\n quantity\n quantityStatus\n vaccineType\n __typename\n }\n __typename\n }\n __typename\n }\n optionsForMap @include(if: $isBounds) {\n maxZoom\n minZoom\n includeMyLocation\n maxIncludePoiCount\n center\n __typename\n }\n __typename\n }\n queryResult {\n keyword\n vaccineFilter\n categories\n region\n isBrandList\n filterBooking\n hasNearQuery\n isPublicMask\n __typename\n }\n __typename\n }\n}\n"
        }
    ]
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Safari/605.1.15',
        'Host': 'api.place.naver.com',
        'Referer': map_url.format(bounds=f'{x1}%3B{y1}%3B{x2}%3B{y2}'),
        'Content-Length': str(len(json.dumps(data)))
    }
    try:
        r = requests.post(list_url, headers=headers, json=data, timeout=TIMEOUT)
        items = r.json()[0]['data']['rests']['businesses']['items']
    # Request timeout
    except requests.exceptions.ReadTimeout:
        print(f'{style.WARNING}T{style.ENDC}', end=' ')
        return []
    # Did not not get correct response; Maybe not JSON or server error
    except (json.JSONDecodeError, TypeError):
        print(f'{style.ERROR}D{style.ENDC}', end=' ')
        return []
    # Response error; Maybe server error
    except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError):
        print(f'{style.ERROR}R{style.ENDC}', end=' ')
        return []
    # Display agencies count
    print(f'{len(items)}', end=' ')
    return items


# Follow redirects and get progress url
def view_agency(cd, sid, naver_cookies, vaccine_ids, driver, auto_progress):
    headers = {
        'Accept': 'ext/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Safari/605.1.15',
        'Host': 'v-search.nid.naver.com',
    }
    session.cookies.set('NNB', naver_cookies.get('NNB'), path='/', domain='.naver.com', secure=True)
    session.cookies.set('NID_AUT', naver_cookies.get('NID_AUT'), path='/', domain='.naver.com')
    session.cookies.set('NID_JKL', naver_cookies.get('NID_AUT'), path='/', domain='.naver.com', secure=True)
    session.cookies.set('NID_SES', naver_cookies.get('NID_SES'), path='/', domain='.naver.com')
    url = item_url.format(**locals())
    print(f'{datetime.datetime.now():%H:%M:%S} {style.OK}백신이 유효한지 확인: {url} {style.ENDC}')
    r = session.get(url, headers=headers, allow_redirects=False)
    # Redirect many times until get last page
    while r.status_code == 301 or r.status_code == 302:
        url = r.headers['Location'].replace('http://', 'https://')
        r = session.get(url, headers=headers, allow_redirects=False)
    # Get key for auto progress
    o = urlparse(r.url)
    qs = parse_qs(o.query)
    key = qs['key'][0]
    # Find radio button using vaccine_id
    html = r.text
    soup = BeautifulSoup(html, 'html.parser')
    # Check vaccine out of stock
    elem = soup.find(id='info_item_exist')
    if len(elem.find('ul').find_all('li')) < 1:
        print(f'{datetime.datetime.now():%H:%M:%S} 신청 가능한 백신이 없습니다.')
        return None
    # Check the radio button disabled
    found = False
    for vaccine_id in vaccine_ids:
        if elem.find(id=vaccine_id):
            found = True
            break
    if not found:
        print('{datetime.datetime.now():%H:%M:%S} 원하는 백신이 없습니다.')
        return None
    print(f'{datetime.datetime.now():%H:%M:%S} {style.OK}백신을 찾았습니다: {r.url} {style.ENDC}')
    driver.get(r.url)
    driver.switch_to.window(driver.current_window_handle)
    if auto_progress:
        url = progress_url.format(**locals())
        print(f'{datetime.datetime.now():%H:%M:%S} {style.OK}신청 주소를 이용하여 자동 진행합니다: {url} ... {style.ENDC}')
        driver.get(url)
        time.sleep(3)   # Wait page loads
        elem = driver.find_element(By.CLASS_NAME, 'h_title')
        try:
            result_title = elem.get_attribute('textContent')
            print(f'Got title from page: {result_title}')
        except NoSuchElementException:
            print(f'{datetime.datetime.now():%H:%M:%S} {style.WARNING}실패? {style.ENDC}')
            return False
        if result_title == '당일 예약정보입니다.' or result_title.endswith('잔여백신 당일 예약이 완료되었습니다.'):
            print(f'{datetime.datetime.now():%H:%M:%S} {style.SUCCESS}성공 {style.ENDC}')
            driver.switch_to.window(driver.current_window_handle)
            return True
        elif result_title == '잔여백신 당일 예약이 실패되었습니다.':
            print(f'{datetime.datetime.now():%H:%M:%S} {style.WARNING}실패 {style.ENDC}')
            return False
        else:
            print(f'{datetime.datetime.now():%H:%M:%S} {style.WARNING}실패? {style.ENDC}')
            return False
    else:
        driver.switch_to.window(driver.current_window_handle)
        print(f'{datetime.datetime.now():%H:%M:%S} {style.SUCCESS}페이지에서 진행해주세요.{style.ENDC}')
        return True


def prepare_naver_driver(naver_cookies):
    timeout = 10
    driver_path = 'chromedriver.exe' if platform.system() == 'Windows' else f'./chromedriver_{platform.machine()}'
    driver = webdriver.Chrome(driver_path)
    driver.set_window_size(640, 1136)   # Mobile size
    wait = WebDriverWait(driver, 10)
    driver.get('https://v-search.nid.naver.com/reservation/me')
    WebDriverWait(driver, timeout).until(expected_conditions.url_changes('data;')) # Time to load
    time.sleep(1)
    if naver_cookies.get('NID_SES'):
        # Login into NAVER
        driver.add_cookie({'name' : 'NNB', 'value' : naver_cookies.get('NNB'), 'path': '/', 'domain' : '.naver.com', 'secure': True})
        driver.add_cookie({'name' : 'NID_AUT', 'value' : naver_cookies.get('NID_AUT'), 'path': '/', 'domain' : '.naver.com'})
        driver.add_cookie({'name' : 'NID_JKL', 'value' : naver_cookies.get('NID_JKL'), 'path': '/', 'domain' : '.naver.com', 'secure': True})
        driver.add_cookie({'name' : 'NID_SES', 'value' : naver_cookies.get('NID_SES'), 'path': '/', 'domain' : '.naver.com'})
    else:
        # Request login into NAVER
        driver.get('https://nid.naver.com/nidlogin.login?svctype=262144')
        while not driver.get_cookie('NID_SES'):
            naver_cookies['NNB'] = driver.get_cookie('NNB')
            naver_cookies['NID_AUT'] = driver.get_cookie('NID_AUT')
            naver_cookies['NID_JKL'] = driver.get_cookie('NID_JKL')
            naver_cookies['NID_SES'] = driver.get_cookie('NID_SES')
            input('네이버 로그인 후 리턴 키를 눌러주세요')
        print(f'{datetime.datetime.now():%H:%M:%S} {style.OK}로그인이 확인되었습니다.{style.ENDC}')
    driver.refresh()
    driver.get('https://v-search.nid.naver.com/reservation/me')
    return driver


# Show map and get area bounds
def input_area(driver):
    driver.get(map_url.format(bounds=''))
    while not re.search(r'bounds\=(.+)&*', driver.current_url):
        input('확인할 지역으로 이동 후 "현 지도에서 검색" 클릭 후 리턴 키를 눌러주세요')
    matches = re.search(r'bounds\=(.+)&*', driver.current_url)
    print(f'{datetime.datetime.now():%H:%M:%S} {style.OK}지역이 확인되었습니다.{style.ENDC}')
    return matches.group(1)


def input_vaccine():
    vaccine_id = None
    while not vaccine_id in vaccines_id_map.keys():
        for k, v in vaccines_id_map.items():
            print(f'{k}: {v["name"]}')
        vaccine_id = input('원하는 백신을 입력해주세요: ')
    print(f'{datetime.datetime.now():%H:%M:%S} {style.OK}백신 종류가 확인되었습니다.{style.ENDC}')
    return vaccine_id


# Check areas and view_agency when found vaccineQuantity
def check(area_list, vaccine_ids, naver_cookies, driver, auto_progress):
    for area in area_list:
        agencies = list_agencies(*area)
        agencies_found = []
        for agency in agencies:
            v = agency['vaccineQuantity']
            if v and v['totalQuantity'] != 0:
                agencies_found.append(agency)
        if len(agencies_found) > 0:
            print(f'\n{style.OK}백신을 보유한 {len(agencies_found)}개의 접종 기관 발견{style.ENDC}')
        for agency in agencies_found:
            name = agency['name']
            v = agency['vaccineQuantity']
            quantity = v['totalQuantity']
            print(f'{datetime.datetime.now():%H:%M:%S} 확인중 - {name}, 백신 수 - {quantity} ... ')
            result = view_agency(agency['vaccineQuantity']['vaccineOrganizationCode'], agency['id'], naver_cookies=naver_cookies, vaccine_ids=vaccine_ids, driver=driver, auto_progress=auto_progress)
            if result:
                return result


def main(areas, vaccines, naver_cookies, auto_progress):
    # Login into NAVER
    driver = prepare_naver_driver(naver_cookies)

    if not areas:
        areas = [input_area(driver)]

    if not vaccines:
        vaccines = [input_vaccine()]

    # Build floats from bounds; separator ";" urlencoded "%3B"
    area_list = [a.split('%3B') for a in areas]
    vaccine_ids = [vaccines_id_map[v]['id'] for v in vaccines]
    vaccine_names = [vaccines_id_map[v]['name'] for v in vaccines]

    print(f'{datetime.datetime.now():%H:%M:%S} {style.OK}{vaccine_names} 백신, 다음과 같은 {len(area_list)}개의 구역을 모니터링합니다:{style.ENDC}')
    for area in area_list:
        print(map_url.format(bounds='%3B'.join(area)))
    if auto_progress:
        print(f'{style.OK}원하는 백신이 발견되면 자동으로 신청합니다.{style.ENDC}')

    driver.minimize_window()
    sys.stdout.flush()
    result = None
    count = 0
    # Check every 0.7 * area count sec
    interval = len(areas) * 0.7
    while not result:
        sys.stdout.flush()
        print(f'{datetime.datetime.now():%H:%M:%S} {count:05d} : ', end='')
        if datetime.datetime.now().hour <= 8 or datetime.datetime.now().hour >= 1:
            print(f'백신 신청 시간이 아님 - 10분 대기')
            time.sleep(600)
            continue
        else:
            count += 1
            # Masture time for check and decide wait time
            start_time = time.perf_counter()
            result = check(area_list, vaccine_ids, naver_cookies, driver=driver, auto_progress=auto_progress)
            end_time = time.perf_counter()
            if result:
                print(f'{style.SUCCESS}{result}{style.ENDC}')
                input(f'사용자 입력을 기다립니다.')
            else:
                # Fill wait time using excute time
                wait_time = interval - (end_time - start_time) if (end_time - start_time) < interval else 0.0
                print(f'- 시간: {end_time - start_time:.2f}s, 대기: {wait_time:.2f}s')
                time.sleep(wait_time)


if __name__ == '__main__':
    # Execute only if run as a script
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--areas', nargs='+', help='지도로 부터 얻은 bounds 파라메터')
    parser.add_argument('-v', '--vaccines', nargs='+', help='벡신 종류: AZ, JS, PF, MO')
    parser.add_argument('-NN', '--NNB', help='네이버 NNB 쿠키')
    parser.add_argument('-NA', '--NID_AUT', help='네이버 NID_AUT 쿠키')
    parser.add_argument('-NJ', '--NID_JKL', help='네이버 NID_JKL 쿠키')
    parser.add_argument('-NS', '--NID_SES', help='네이버 NID_SES 쿠키')
    parser.add_argument('-c', '--check_only', action='store_true', default=False, help='수동으로 신청')
    args = parser.parse_args()
    naver_cookies = {
        'NNB': args.NNB,
        'NID_AUT': args.NID_AUT,
        'NID_JKL': args.NID_JKL,
        'NID_SES': args.NID_SES,
    }
    auto_progress = not args.check_only
    main(areas=args.areas, vaccines=args.vaccines, naver_cookies=naver_cookies, auto_progress=auto_progress)
