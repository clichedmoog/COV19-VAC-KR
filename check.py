import argparse
import datetime
import json
import os
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


map_url = 'https://m.place.naver.com/rest/vaccine?bounds={bounds}'
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
def check_agencies(x1='126.8281358', y1='37.5507676', x2='126.8603223', y2='37.5872323'):
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
                    "categories":["1004836"],
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
        'Content-Length': str(len(json.dumps(data)))
    }
    try:
        r = requests.post(list_url, headers=headers, json=data, timeout=TIMEOUT)
        items = r.json()[0]['data']['rests']['businesses']['items']
    except requests.exceptions.ReadTimeout:
        # Request timeout
        print(f'{style.WARNING}T{style.ENDC}', end=' ')
        return []
    except json.JSONDecodeError:
        # Did not not get correct response; Maybe not JSON or server error
        print(f'{style.ERROR}E{style.ENDC}', end=' ')
        return []
    except TypeError:
        # Did not not get correct response - Maybe with no result or server error
        print(f'{style.WARNING}E{style.ENDC}', end=' ')
        return []
    except requests.exceptions.ConnectionError:
        print(f'{style.ERROR}E{style.ENDC}', end=' ')
        return []
    found_items = []
    print(f'{len(items)}', end=' ')
    for item in items:
        v = item['vaccineQuantity']
        if v and v['totalQuantity'] != 0:
            found_items.append(item)

    return found_items


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
    print(f'{style.OK}백신이 유요한지 확인: {url} {style.ENDC}')
    r = session.get(url, headers=headers, allow_redirects=False)
    # Redirect many times until get last page
    while r.status_code == 301 or r.status_code == 302:
        url = r.headers['Location'].replace('http://', 'https://')
        r = session.get(url, headers=headers, allow_redirects=False)
    driver.get(r.url)
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
        print('신청 가능한 백신이 없습니다.')
        return None
    # Check the radio button disabled
    found = False
    for vaccine_id in vaccine_ids:
        if elem.find(id=vaccine_id):
            found = True
            break
    if not found:
        print('원하는 백신이 없습니다.')
        return None
    print(f'{style.OK}백신을 찾았습니다: {r.url} {style.ENDC}')
    if auto_progress:
        url = progress_url.format(**locals())
        print(f'{style.OK}신청 주소를 이용하여 자동 진행합니다: {url} ... {style.ENDC}')
        driver.get(url)
        time.sleep(3)   # Wait page loads
        elem = driver.find_element(By.CLASS_NAME, 'h_title')
        try:
            result_title = elem.get_attribute('textContent')
            print(f'Got title from page: {result_title}')
        except NoSuchElementException:
            print(f'{style.WARNING}실패? {style.ENDC}')
            return False
        if result_title == '당일 예약정보입니다.' or result_title.endswith('잔여백신 당일 예약이 완료되었습니다.'):
            print(f'{style.SUCCESS}성공 {style.ENDC}')
            driver.switch_to.window(driver.current_window_handle)
            os.system('say 신청 완료')
            return True
        elif result_title == '잔여백신 당일 예약이 실패되었습니다.':
            print(f'{style.WARNING}실패 {style.ENDC}')
            return False
        else:
            print(f'{style.WARNING}실패? {style.ENDC}')
            return False
    else:
        print(f'페이지를 여는 중: {r.url}')
        driver.get(r.url)
        driver.switch_to.window(driver.current_window_handle)
        os.system('say 페이지에서 진행해주세요.')
        return True


def prepare_naver_driver(naver_cookies):
        # Login into NAVER
    timeout = 10
    driver = webdriver.Chrome('./chromedriver')
    wait = WebDriverWait(driver, 10)
    driver.get('https://www.naver.com')
    WebDriverWait(driver, timeout).until(expected_conditions.url_changes('data;')) # Time to load
    time.sleep(1)
    driver.add_cookie({'name' : 'NNB', 'value' : naver_cookies.get('NNB'), 'path': '/', 'domain' : '.naver.com', 'secure': True})
    driver.add_cookie({'name' : 'NID_AUT', 'value' : naver_cookies.get('NID_AUT'), 'path': '/', 'domain' : '.naver.com'})
    driver.add_cookie({'name' : 'NID_JKL', 'value' : naver_cookies.get('NID_JKL'), 'path': '/', 'domain' : '.naver.com', 'secure': True})
    driver.add_cookie({'name' : 'NID_SES', 'value' : naver_cookies.get('NID_SES'), 'path': '/', 'domain' : '.naver.com'})
    driver.refresh()
    return driver


# Check areas and view_agency when found vaccineQuantity
def check(area_list, vaccine_ids, naver_cookies, driver, auto_progress):
    for area in area_list:
        found_items = check_agencies(*area)
        if len(found_items) > 0:
            print(f'\n{style.OK}Found {len(found_items)} agencies {style.ENDC}')
        for item in found_items:
            name = item['name']
            v = item['vaccineQuantity']
            quantity = v['totalQuantity']
            print(f'확인중 - {name}, 백신 수 - {quantity} ... ', end=' ')
            result = view_agency(item['vaccineQuantity']['vaccineOrganizationCode'], item['id'], naver_cookies=naver_cookies, vaccine_ids=vaccine_ids, driver=driver, auto_progress=auto_progress)
            if result:
                return result


def main(areas, vaccines, naver_cookies, auto_progress):
    # Build floats from bounds; separator ";" urlencoded "%3B"
    area_list = [a.split('%3B') for a in areas]
    vaccine_ids = [vaccines_id_map[v]['id'] for v in vaccines]
    vaccine_names = [vaccines_id_map[v]['name'] for v in vaccines]

    # Login into NAVER
    driver = prepare_naver_driver(naver_cookies)
    driver.minimize_window()

    print(f'{vaccine_names} 백신, {style.BOLD}{len(area_list)}{style.ENDC} 구역을 모니터링합니다:')
    for area in area_list:
        print(map_url.format(bounds='%3B'.join(area)))
    if auto_progress:
        print(f'원하는 백신이 발견되면 자동으로 신청합니다.')
    sys.stdout.flush()
    result = None
    count = 1
    while not result:
        sys.stdout.flush()
        print(f'{count} : ', end='')
        if datetime.datetime.now().hour <= 8 or datetime.datetime.now().hour >= 18:
            print(f'백신 신청 시간이 아닙니다 - 10분 대기합니다.')
            time.sleep(600)
            continue
        else:
            start_time = time.perf_counter()
            result = check(area_list, vaccine_ids, naver_cookies, driver=driver, auto_progress=auto_progress)
            end_time = time.perf_counter()
            if result:
                print(f'{style.SUCCESS}{result}{style.ENDC}')
                input(f'사용자 입력을 기다립니다.')
            else:
                # Check every 1 sec
                wait_time = 1.0 - (end_time - start_time) if (end_time - start_time) < 1.0 else 0.0
                print(f'- 시간: {end_time - start_time:.2f}s, 대기: {wait_time:.2f}s')
                time.sleep(wait_time)
            count += 1


if __name__ == '__main__':
    # Execute only if run as a script
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--areas', nargs='+', 
        help='Areas: bounds from url',
        # 서초 ~ 강남 https://m.place.naver.com/rest/vaccine?vaccineFilter=used&x=126.9731665&y=37.5502763&bounds=126.9828187%3B37.4831649%3B127.0446168%3B37.5019267
        default='126.9558315%3B37.4745959%3B127.0656948%3B37.5153529')
    parser.add_argument('-v', '--vaccines', nargs='+', required=True, help='벡신 종류: AZ, JS, PF, MO')
    parser.add_argument('-NN', '--NNB', required=True, help='네이버 NNB 쿠키')
    parser.add_argument('-NA', '--NID_AUT', required=True, help='네이버 NID_AUT 쿠키')
    parser.add_argument('-NJ', '--NID_JKL', required=True, help='네이버 NID_JKL 쿠키')
    parser.add_argument('-NS', '--NID_SES', required=True, help='네이버 NID_SES 쿠키')
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
