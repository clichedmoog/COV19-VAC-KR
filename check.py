import argparse
import json
import random
import sys
import time

from decimal import Decimal
from urllib.parse import urlparse, parse_qs

import requests

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions


list_url = 'https://api.place.naver.com/graphql'
item_url = 'https://v-search.nid.naver.com/reservation/standby?orgCd={cd}&sid={sid}'
progress_url = 'https://v-search.nid.naver.com/reservation/progress?key={key}&cd={vaccine_id}'
TIMEOUT = 3
session = requests.session()

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
    x1 = Decimal(x1)
    y1 = Decimal(y1)
    x2 = Decimal(x2)
    y2 = Decimal(y2)
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
                    "x":"126.844229",
                    "y":"37.5690022",
                    "bounds": f"{x1};{y1};{x2};{y2}",
                    "sortingOrder":"distance"
                },
                "isNmap": False,
                "isBounds": False
            },
            "query":"query vaccineList($input: RestsInput, $businessesInput: RestsBusinessesInput, $isNmap: Boolean!, $isBounds: Boolean!) {\n  rests(input: $input) {\n    businesses(input: $businessesInput) {\n      total\n      vaccineLastSave\n      isUpdateDelayed\n      items {\n        id\n        name\n        dbType\n        phone\n        virtualPhone\n        hasBooking\n        hasNPay\n        bookingReviewCount\n        description\n        distance\n        commonAddress\n        roadAddress\n        address\n        imageUrl\n        imageCount\n        tags\n        distance\n        promotionTitle\n        category\n        routeUrl\n        businessHours\n        x\n        y\n        imageMarker @include(if: $isNmap) {\n          marker\n          markerSelected\n          __typename\n        }\n        markerLabel @include(if: $isNmap) {\n          text\n          style\n          __typename\n        }\n        isDelivery\n        isTakeOut\n        isPreOrder\n        isTableOrder\n        naverBookingCategory\n        bookingDisplayName\n        bookingBusinessId\n        bookingVisitId\n        bookingPickupId\n        vaccineQuantity {\n          quantity\n          quantityStatus\n          vaccineType\n          vaccineOrganizationCode\n          __typename\n        }\n        __typename\n      }\n      optionsForMap @include(if: $isBounds) {\n        maxZoom\n        minZoom\n        includeMyLocation\n        maxIncludePoiCount\n        center\n        __typename\n      }\n      __typename\n    }\n    queryResult {\n      keyword\n      vaccineFilter\n      categories\n      region\n      isBrandList\n      filterBooking\n      hasNearQuery\n      isPublicMask\n      __typename\n    }\n    __typename\n  }\n}\n"
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
    found_items = []
    print(f'{len(items)}', end=' ')
    for item in items:
        v = item['vaccineQuantity']
        if v and v['quantity'] != '0':
            found_items.append(item)
    
    return found_items


# Follow redirects and get progress url
def view_agency(cd, sid, naver_cookies, vaccine_id, driver, auto_progress=False):
    headers = {
        'Accept': 'ext/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Safari/605.1.15',
        'Host': 'v-search.nid.naver.com',
    }
    session.cookies.set('NNB', naver_cookies.get('NNB'), path='/', domain='.naver.com', secure=True)
    session.cookies.set('NID_AUT', naver_cookies.get('NID_AUT'), path='/', domain='.naver.com')
    session.cookies.set('NID_JKL', naver_cookies.get('NID_AUT'), path='/', domain='.naver.com', secure=True)
    session.cookies.set('NID_SES', naver_cookies.get('NID_SES'), path='/', domain='.naver.com')
    r = session.get(item_url.format(**locals()), headers=headers, allow_redirects=False)
    # Redirect many times until get last page
    while r.status_code == 301 or r.status_code == 302:
        url = r.headers['Location'].replace('http://', 'https://')
        r = session.get(url, headers=headers, allow_redirects=False)
    # Parse for after use
    o = urlparse(r.url)
    qs = parse_qs(o.query)
    key = qs['key'][0]
    # Find radio button using vaccine_id
    html = r.text
    soup = BeautifulSoup(html, 'html.parser')
    elem = soup.select(f'#{vaccine_id}')
    # Check the radio button disabled
    if elem[0].has_attr('disabled'):
        return None
    else:
        print(f'{style.OK}Found vaccine available: {r.url} {style.ENDC}')
        if auto_progress:
            url = progress_url.format(**locals())
            print(f'{style.OK}Progressing automatically using {url} ... {style.ENDC}', end='')
            open_naver_page(driver, url)
            elem = driver.find_element(By.CLASS_NAME, 'h_title')
            try:
                result_title = elem.get_attribute('textContent')
            except NoSuchElementException:
                print(f'{style.WARNING}Failed? {style.ENDC}')
                return False
            if result_title == '당일 예약정보입니다.':
                print(f'{style.SUCCESS}Successful {style.ENDC}')
                return True
            elif result_title == '잔여백신 당일 예약이 실패되었습니다.':
                print(f'{style.WARNING}Failed {style.ENDC}')
                return False
            else:
                print(f'{style.WARNING}Failed? {style.ENDC}')
                return False
        else:
            print(f'Will open page {r.url}')
            open_naver_page(driver, r.url)
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

# Opens NAVER page with login using cookies
def open_naver_page(driver, url):
    driver.get(url)
    driver.switch_to.window(driver.current_window_handle)
    

# Check areas and view_agency when found vaccineQuantity
def check(area_list, vaccine_id, naver_cookies, driver, auto_progress):
    for area in area_list:
        found_items = check_agencies(*area)
        if len(found_items) > 0:
            print(f'\n{style.OK}Found {len(found_items)} agencies {style.ENDC}')
        for item in found_items:
            name = item['name']
            v = item['vaccineQuantity']
            quantity = v['quantity']
            print(f'Checking {name}({quantity}) ... ', end=' ')
            result = view_agency(item['vaccineQuantity']['vaccineOrganizationCode'], item['id'], naver_cookies=naver_cookies, vaccine_id=vaccine_id, driver=driver, auto_progress=auto_progress)
            if result:
                print(f'{style.SUCCESS}Found!{style.ENDC}')
                return result
            else:
                print(f'{style.SUCCESS}Not found{style.ENDC}')
                
            

def main(areas, vaccine, naver_cookies):
    vaccines = {
        'AZ': 'VEN00015',
        'JS': 'VEN00016'
    }
    # Build floats from bounds; separator ";" urlencoded "%3B"
    area_list = [a.split('%3B') for a in areas] 
    vaccine_id = vaccines[vaccine]

    # Login into NAVER
    driver = prepare_naver_driver(naver_cookies)

    print(f'Monitoring {style.BOLD}{len(area_list)}{style.ENDC} areas for {vaccine_id}')
    sys.stdout.flush()
    result = None
    while not result:
        sys.stdout.flush()
        start_time = time.perf_counter()
        result = check(area_list, vaccine_id, naver_cookies, driver=driver, auto_progress=True)
        end_time = time.perf_counter()
        if result:
            print(f'{style.SUCCESS}{result}{style.ENDC}')
            input(f'Waiting for user input')
        else:
            wait_time = 0.3 + random.random() / 3.0
            print(f'- took: {end_time - start_time:.2f}s, wait: {wait_time:.2f}s')
            time.sleep(wait_time) # Check every 0.3 ~ 0.93 sec


if __name__ == '__main__':
    # Execute only if run as a script
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--areas', nargs='+', 
        help='Areas: bounds from url',
        # 서초 ~ 강남 https://m.place.naver.com/rest/vaccine?vaccineFilter=used&x=126.9731665&y=37.5502763&bounds=126.9828187%3B37.4831649%3B127.0446168%3B37.5019267
        default='126.9828187%3B37.4831649%3B127.0446168%3B37.5019267')
    parser.add_argument('-v', '--vaccine', required=True, help='Vaccine code: AZ, JS')
    parser.add_argument('-NN', '--NNB', required=True, help='NAVER NNB cookie')
    parser.add_argument('-NA', '--NID_AUT', required=True, help='NAVER NID_AUT cookie')
    parser.add_argument('-NJ', '--NID_JKL', required=True, help='NAVER NID_JKL cookie')
    parser.add_argument('-NS', '--NID_SES', required=True, help='NAVER NID_SES cookie')
    args = parser.parse_args()
    naver_cookies = { 
        'NNB': args.NNB,
        'NID_AUT': args.NID_AUT,
        'NID_JKL': args.NID_JKL,
        'NID_SES': args.NID_SES,
    }
    main(args.areas, args.vaccine, naver_cookies=naver_cookies)
