# 잔여 백신 자동 신청 스크립트
잔여 백신을 스크립트로 예약하는 것은 다른 사람의 기회를 박탈 하는 것이기도 하니 신중하게 사용 여부를 결정해주세요.

### 준비사항
네이버 인증서를 발급 받은 상태여야 합니다.
macOS, Google Chrome 이 설치 된 상태여야 하며, Google Chrome이 91버전이여야 합니다.
크롬 버전이 다른 경우 chromedriver를 아래 링크에서 알맞은 버전으로 다운로드 하여 넣어주세요.
https://chromedriver.chromium.org/downloads

### 사용법
1. 폴더를 정하여 압축을 풉니다.
2. 검색 할 구역을 지도 링크에서 검색 후 bounds 파라메터를 복사해서 커멘드에 넣습니다. (서초~강남은 이 과정을 건너 뛰어도 됩니다, 지역을 추가 할 때마다 확인 주기가 0.7초 단위로 증가합니다)
3. 브라우저를 열고 네이버에 로그인 후에 NNB, NID_SES, NID_AUT, NID_SES 쿠키를 복사해서 커맨드에 붙여넣습니다.
4. 백신 종류를 골라서 -v 파라메터에 붙여 넣습니다. 화이자는 PF, 모더나는 MO, 아스트라제네카는 AZ, 얀센은 JS 입니다.
5. 커맨드라인을 열고 해당 폴더로 이동합니다.
6. source venv/bin/activate를 실행합니다.
7. 2~4에서 작성한 자신의 커맨드를 실행합니다. 이 과정에서 확인되지 않은 개발자의 앱 승인이 필요하면 chromedriver를 승인해줍니다.
8. 새롭게 브라우저가 뜨고 자동으로 네이버에 로그인 된 상태가 됩니다. 로그인이 안되면 커맨드를 실행 중단하고 다시 실행해주세요.
9. 백신이 발견되면 열려있는 브라우저에서 자동으로 신청을 하고, 실패 하면 재시도, 성공하면 경우 대기합니다.

### 여러 지역을 검색하기, 화이자
python check.py \
-a "126.7992413%3B37.5587393%3B126.8355692%3B37.5783834" \
"126.8307895%3B37.5514289%3B126.8671173%3B37.5710749" \
-v PF \
-NN "자신의 NNB 쿠키 입력" \
-NA "자신의 NID_AUT 쿠키 입력" \
-NJ "자신의 NID_JKL 쿠키 입력" \
-NS "자신의 NID_SES 쿠키 입력"

### 서초 ~ 강남 지역을 검색하기, 화이자, 모더나 아스트라제네카, 얀센
python check.py \
-v PF MO AZ JS \
-NN "자신의 NNB 쿠키 입력" \
-NA "자신의 NID_AUT 쿠키 입력" \
-NJ "자신의 NID_JKL 쿠키 입력" \
-NS "자신의 NID_SES 쿠키 입력"

##### 지도 링크
-a 파라메터 생성을 이 링크를 사용해서 해주세요.
https://m.place.naver.com/rest/vaccine?vaccineFilter=used&x=126.9731665&y=37.5502763&bounds=126.94098%3B37.5125681%3B127.005353%3B37.5879655
