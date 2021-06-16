import json
import random
import sys
import time
import os

from decimal import Decimal
from urllib.parse import urlparse, parse_qs

import requests

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions


list_url = 'https://api.place.naver.com/graphql'
item_url = 'https://v-search.nid.naver.com/reservation/standby?orgCd={cd}&sid={sid}'
progress_url = 'https://v-search.nid.naver.com/reservation/progress?key={key}&cd={vaccine_id}'
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
    r = requests.post(list_url, headers=headers, json=data)
    try:
        items = r.json()[0]['data']['rests']['businesses']['items']
    except TypeError:
        print(f'\n{style.WARNING}Did not not get correct response from server {r.json()}')
        return []
    found_items = []
    print(f'{len(items)}', end=' ')
    for item in items:
        v = item['vaccineQuantity']
        if v and v.get('quantity') != '0':
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
        print(f'{style.OK}Found vaccine available: {r.url}')
        if auto_progress:
            url = progress_url.format(**locals())
            print(f'{style.OK}Progressing automatically using {url} ...', end='')
            driver = open_naver_page(driver, url)
            elem = driver.find_element(By.CLASS_NAME, 'h_title')
            result_title = elem.get_attribute('textContent')
            if result_title == '잔여백신 당일 예약이 실패되었습니다.':
                print(f'{style.WARNING}Failed')
                return False
            else:
                print(f'{style.SUCCESS}Successful')
                return True
        else:
            print(f'Will open page {r.url}')
            driver = open_naver_page(driver, r.url)
            return True

# Opens NAVER page with login using cookies
def open_naver_page(driver, url):
    driver.get(url)
    driver.switch_to.window(driver.current_window_handle)


# Check areas and view_agency when found vaccineQuantity
def check(area_list, vaccine_id, naver_cookies, driver, auto_progress):
    for area in area_list:
        found_items = check_agencies(*area)
        if len(found_items) > 0:
            print(f'\n{style.OK}Found {len(found_items)} agencies')
        for item in found_items:
            name = item.get('name')
            print(f'Checking {name} ...')
            result = view_agency(item['vaccineQuantity']['vaccineOrganizationCode'], item['id'], naver_cookies=naver_cookies, vaccine_id=vaccine_id, driver=driver, auto_progress=auto_progress)
            if result:
                return result
                
            

def main():
    # Areas to monitor: this is bounds param from NAVER map using links like https://m.place.naver.com/rest/vaccine?vaccineFilter=used&x=126.9731665&y=37.5502763&bounds=126.94098%3B37.5125681%3B127.005353%3B37.5879655
    areas = [
        '126.7992413%3B37.5587393%3B126.8355692%3B37.5783834',  # 공항
        '126.8307895%3B37.5514289%3B126.8671173%3B37.5710749',  # 가양
        '126.9828187%3B37.4831649%3B127.0446168%3B37.5019267'    # 서초~강남
    ]
    vaccine_id = 'VEN00015' # Vaccine code: 'VEN00015': AZ, 'VEN00016': Janssen
    naver_cookies = {       # To Log into NAVER: NNB, NID_AUT, NID_JKL, NID_SES cookies
        'NNB': 'AFQAQGVV37EGA',
        'NID_AUT': 'CLW9ByqiNqGEbrtG/tG79Qrv3FAtTEb9bTFfW+C8o4d8MmZohL08KYuEZWh/sFRs',
        'NID_JKL': '8V+/hO68WQfz3DYqgi3eHkt1zvDlouj7hdWvdWvm6hM=',
        'NID_SES': 'AAABkWYlwtTQDKBbPXGkITDMxjREq1U9CTJhdtiitAL/CDV5NDIJ4nGRcHcC7kI2H6ypeeQjvUBFF45owJdqjrnDyEXOCYQ08RKSTv9PfDVTrM3AzHLX96SMOjEM02CI0JgLQzy/5LAvO0SZ4+EOM/WptrL/Mcnw13JKtrH8A/gfcOdpRjHOFbGHD9/gZl1UkwUv6q1PIuCdwBPqNHlAh3ch6hND8pEgBqT9KFxVGNqL3V9XCh8rB/HC8JJL85YGgify24zC4dZx17v9j53seHnaEVVyjdv2Ag88drkhQULZfq1j9KIq/rbXcZPls9U1hf42WvrSWLbqdHc1fIDIiIuAF2CNrxiI+cwoMN/2c/yhlRnpi1tOHtQf7pPEn0YJ+K4dsFlYvxLNQ4IrybpaV7w+Js1Xdse4yqPMYxPM1DqcAxpMIgrFn68TgKY9Lf+ffOggkfgTlBO+esPH2doCKnHeJ4jycpr7ewE2JjdEBD6YtavLeDdmYuZkAcIViJRdz2OCu3a2KDT+JCH8WPDaqPd8L2NtwpYyGKltqRa2RBsnQ3lN',
    }

    # Build floats from bounds; separator ";" urlencoded "%3B"
    area_list = [a.split('%3B') for a in areas] 

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

    # System call
    os.system('')
    print(f'Monitoring {style.BOLD}{len(area_list)} areas{style.ENDC}')
    sys.stdout.flush()
    result = None
    while not result:
        sys.stdout.flush()
        result = check(area_list, vaccine_id, naver_cookies, driver=driver, auto_progress=False)
        if result:
            input(f'{style.SUCCESS}Waiting for user input')
        else:
            wait_time = 0.3 + random.random()
            print(f'{wait_time: .2f}s wait')
            time.sleep(wait_time) # Check every 0.3 ~ 1.3 sec



if __name__ == '__main__':
    # Execute only if run as a script
    main()
