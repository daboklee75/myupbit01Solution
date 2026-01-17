# 대시보드 인증(로그인) 구현 계획

## 목표 (Goal)
Streamlit 대시보드(`app.py`)에 간단한 로그인 기능을 구현하여 접근을 제한합니다. 자격 증명(아이디/비번)은 기존 `.env` 파일에 안전하게 저장하여 관리합니다.

## 사용자 리뷰 필요 사항
> [!IMPORTANT]
> 이 방식은 AWS의 HTTPS 보안을 전제로 한 기본적인 인증 방식입니다. 별도의 데이터베이스나 복잡한 세션 관리는 사용하지 않지만, 개인용 대시보드로는 충분히 안전합니다.

## 변경 제안 (Proposed Changes)

### 설정 (Configuration)
#### [수정] [.env.template](file:///d:/03.%EA%B0%9C%EB%B0%9C%EC%9E%90%EB%A3%8C/myupbit01/.env.template)
- `WEB_USERNAME` (아이디) 및 `WEB_PASSWORD` (비밀번호) 항목 추가.

### 소스 코드 (Source Code)
#### [수정] [app.py](file:///d:/03.%EA%B0%9C%EB%B0%9C%EC%9E%90%EB%A3%8C/myupbit01/src/myupbit01/app.py)
1.  **`check_password()` 함수 추가**:
    - `st.session_state["password_correct"]` 값을 확인합니다.
    - 인증되지 않은 경우 로그인 폼(아이디/비번 입력창)을 렌더링합니다.
    - 입력된 값과 `.env`의 `WEB_USERNAME`, `WEB_PASSWORD`를 비교 검증합니다.
2.  **`main()` 함수에 통합**:
    - `main()` 함수 시작 부분에서 `check_password()`를 가장 먼저 호출합니다.
    - 인증 실패 시 (`False` 반환), 이후 코드 실행을 중단합니다 (`st.stop()`).
3.  **로그아웃 버튼 추가**:
    - 사이드바에 "로그아웃" 버튼을 추가하여 세션 상태를 초기화하고 화면을 새로고침합니다.

## 검증 계획 (Verification Plan)

### 수동 검증
1.  **설정**:
    - `.env` 파일에 테스트용 아이디/비번을 설정합니다 (예: `admin` / `1234`).
2.  **로그인 테스트**:
    - `streamlit run src/myupbit01/app.py` 명령어로 실행합니다.
    - 대시보드 내용이 가려지고 로그인 화면이 먼저 뜨는지 확인합니다.
    - 틀린 비밀번호 입력 -> 에러 메시지 확인.
    - 맞는 비밀번호 입력 -> 대시보드 진입 확인.
3.  **로그아웃 테스트**:
    - 사이드바의 "로그아웃" 버튼 클릭 -> 로그인 화면으로 돌아가는지 확인.
4.  **배포**:
    - AWS 서버에 배포 시 `.env` 파일을 수정하여 실제 사용할 비밀번호를 입력해야 합니다.
